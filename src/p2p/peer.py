from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from p2p.config import CommonCfg, PeerInfo, load_common, load_peers
from p2p.storage import Storage, FileMeta
from p2p.logger import PeerLogger
from p2p.messages import (
    Message,
    make_choke,
    make_unchoke,
    make_interested,
    make_not_interested,
    make_request,
    make_have,
    make_piece,
)
from p2p.connection import Connection


@dataclass
class NeighborState:
    peer_id: int
    connection: Connection
    bitfield: Optional[bytes] = None  # remote's bitfield
    am_choking: bool = True           # I am choking them
    peer_choking_me: bool = True      # they are choking me
    am_interested: bool = False       # I am interested in them
    peer_interested_me: bool = False  # they are interested in me
    download_bytes_window: int = 0    # bytes downloaded from them in last interval


class Peer:
    """
    Core peer logic. All network I/O is done in Connection objects which call:

        peer.on_message(connection, message)

    Scheduler calls:

        peer.set_preferred_neighbors([...])
        peer.set_optimistic_unchoke(peer_id)
        stats = peer.get_and_reset_download_stats()
    """

    def __init__(
        self,
        common: CommonCfg,
        all_peers: List[PeerInfo],
        me: PeerInfo,
        storage: Storage,
        logger: Optional[PeerLogger] = None,
    ) -> None:
        self.common = common
        self.all_peers = all_peers
        self.me = me
        self.storage = storage
        self.logger = logger or PeerLogger(me.peer_id)

        # peer_id -> NeighborState
        self.neighbors: Dict[int, NeighborState] = {}

        # optimistic unchoke tracking
        self.optimistic_unchoke_peer_id: Optional[int] = None

    # Registration / wiring

    def register_connection(self, remote_peer_id: int, conn: Connection) -> None:
        """
        Called by the networking layer once a TCP connection + handshake is done.
        """
        self.neighbors[remote_peer_id] = NeighborState(
            peer_id=remote_peer_id,
            connection=conn,
        )
        self.logger.log(f"TCP connection established with Peer {remote_peer_id}")

    # Message entry point (used by Connection.read loop)

    def on_message(self, conn: Connection, msg: Message) -> None:
        remote_id = conn.peer_id
        neighbor = self.neighbors.get(remote_id)
        if neighbor is None:
            # Unknown peer, ignore.
            return

        mtype = msg.message_type

        if mtype == Message.CHOKE:
            self._handle_choke(neighbor)
        elif mtype == Message.UNCHOKE:
            self._handle_unchoke(neighbor)
        elif mtype == Message.INTERESTED:
            self._handle_interested(neighbor)
        elif mtype == Message.NOT_INTERESTED:
            self._handle_not_interested(neighbor)
        elif mtype == Message.HAVE:
            self._handle_have(neighbor, msg)
        elif mtype == Message.BITFIELD:
            self._handle_bitfield(neighbor, msg)
        elif mtype == Message.REQUEST:
            self._handle_request(neighbor, msg)
        elif mtype == Message.PIECE:
            self._handle_piece(neighbor, msg)
        else:
            # Unknown / unsupported message type
            self.logger.log(f"Peer {self.me.peer_id}: unknown message type {mtype} from {remote_id}")

    # Individual handlers

    def _handle_choke(self, neighbor: NeighborState) -> None:
        neighbor.peer_choking_me = True
        self.logger.log(f"Peer {self.me.peer_id} is choked by Peer {neighbor.peer_id}")

    def _handle_unchoke(self, neighbor: NeighborState) -> None:
        neighbor.peer_choking_me = False
        self.logger.log(f"Peer {self.me.peer_id} is unchoked by Peer {neighbor.peer_id}")
        # Now that we are unchoked, try to request a piece
        self._request_next_piece(neighbor)

    def _handle_interested(self, neighbor: NeighborState) -> None:
        neighbor.peer_interested_me = True
        self.logger.log(f"Peer {neighbor.peer_id} is interested in Peer {self.me.peer_id}")

    def _handle_not_interested(self, neighbor: NeighborState) -> None:
        neighbor.peer_interested_me = False
        self.logger.log(f"Peer {neighbor.peer_id} is not interested in Peer {self.me.peer_id}")

    def _handle_have(self, neighbor: NeighborState, msg: Message) -> None:
        import struct

        if len(msg.payload) != 4:
            return
        (piece_index,) = struct.unpack("!I", msg.payload)
        self.logger.log(f"Peer {neighbor.peer_id} sent HAVE for piece {piece_index}")

        # Update remote bitfield (lazy: we don't decode fully, just track bytes if needed)
        if neighbor.bitfield is not None:
            neighbor.bitfield = self._set_bit_in_bytes(neighbor.bitfield, piece_index)

        # Decide if we should be interested
        if not self.storage.has_piece(piece_index) and not neighbor.am_interested:
            neighbor.am_interested = True
            neighbor.connection.send(make_interested())
            self.logger.log(f"Peer {self.me.peer_id} sent INTERESTED to Peer {neighbor.peer_id}")

    def _handle_bitfield(self, neighbor: NeighborState, msg: Message) -> None:
        neighbor.bitfield = msg.payload
        self.logger.log(f"Peer {self.me.peer_id} received BITFIELD from Peer {neighbor.peer_id}")

        # Determine if we are interested in them
        if self._has_something_we_want(neighbor):
            if not neighbor.am_interested:
                neighbor.am_interested = True
                neighbor.connection.send(make_interested())
                self.logger.log(f"Peer {self.me.peer_id} sent INTERESTED to Peer {neighbor.peer_id}")
        else:
            if neighbor.am_interested:
                neighbor.am_interested = False
                neighbor.connection.send(make_not_interested())
                self.logger.log(f"Peer {self.me.peer_id} sent NOT_INTERESTED to Peer {neighbor.peer_id}")

    def _handle_request(self, neighbor: NeighborState, msg: Message) -> None:
        import struct

        if len(msg.payload) != 4:
            return
        (piece_index,) = struct.unpack("!I", msg.payload)

        # If we are choking them, ignore
        if neighbor.am_choking:
            return

        # If we have that piece, send it
        if self.storage.has_piece(piece_index):
            data = self.storage.read_piece(piece_index)
            neighbor.connection.send(make_piece(piece_index, data))
            self.logger.log(
                f"Peer {self.me.peer_id} uploads piece {piece_index} to Peer {neighbor.peer_id}"
            )

    def _handle_piece(self, neighbor: NeighborState, msg: Message) -> None:
        import struct

        if len(msg.payload) < 4:
            return
        (piece_index,) = struct.unpack("!I", msg.payload[:4])
        piece_data = msg.payload[4:]

        # Write piece to local storage
        self.storage.write_piece(piece_index, piece_data)
        neighbor.download_bytes_window += len(piece_data)

        # Compute percentage complete (rough)
        have_count = self.storage.count_have()
        total = self.storage.meta.num_pieces
        percent = (have_count / total) * 100.0 if total else 0.0

        self.logger.log(
            f"Peer {self.me.peer_id} has downloaded piece {piece_index} from Peer {neighbor.peer_id}. "
            f"Now has {have_count}/{total} pieces ({percent:.2f}%)."
        )

        # Tell everyone we now have this piece
        self.broadcast_have(piece_index)

        # If we are not complete, request another piece from same peer
        if not self.is_complete():
            self._request_next_piece(neighbor)
        else:
            self.logger.log(f"Peer {self.me.peer_id} has downloaded the complete file.")

    # Piece selection / requesting

    def _request_next_piece(self, neighbor: NeighborState) -> None:
        # Cannot request if they are choking us or we don't know their bitfield
        if neighbor.peer_choking_me or neighbor.bitfield is None:
            return

        piece_index = self._choose_piece_to_request(neighbor)
        if piece_index is None:
            # Nothing to request from this neighbor
            if neighbor.am_interested:
                neighbor.am_interested = False
                neighbor.connection.send(make_not_interested())
                self.logger.log(
                    f"Peer {self.me.peer_id} sent NOT_INTERESTED to Peer {neighbor.peer_id} (no useful pieces)."
                )
            return

        neighbor.connection.send(make_request(piece_index))
        self.logger.log(
            f"Peer {self.me.peer_id} sent REQUEST for piece {piece_index} to Peer {neighbor.peer_id}"
        )

    def _choose_piece_to_request(self, neighbor: NeighborState) -> Optional[int]:
        """
        Very simple rarest-first-ish: scan all pieces, return first that:
        - neighbor has
        - we do not have
        """
        if neighbor.bitfield is None:
            return None

        num_pieces = self.storage.meta.num_pieces
        for idx in range(num_pieces):
            if self._bit_is_set(neighbor.bitfield, idx) and not self.storage.has_piece(idx):
                return idx
        return None

    # Scheduler hooks


    def set_preferred_neighbors(self, preferred_peer_ids: List[int]) -> None:
        """
        Called by Scheduler: these peers should be unchoked (besides the optimistic one).
        Others should be choked.
        """
        preferred_set = set(preferred_peer_ids)
        for pid, neighbor in self.neighbors.items():
            should_unchoke = (pid in preferred_set) or (pid == self.optimistic_unchoke_peer_id)
            if should_unchoke and neighbor.am_choking:
                neighbor.am_choking = False
                neighbor.connection.send(make_unchoke())
                self.logger.log(
                    f"Peer {self.me.peer_id} UNCHOKES Peer {pid} (preferred/optimistic)."
                )
            elif not should_unchoke and not neighbor.am_choking:
                neighbor.am_choking = True
                neighbor.connection.send(make_choke())
                self.logger.log(
                    f"Peer {self.me.peer_id} CHOKES Peer {pid} (not preferred)."
                )

    def set_optimistic_unchoke(self, peer_id: Optional[int]) -> None:
        """
        Called by Scheduler every OptimisticUnchokingInterval.
        """
        self.optimistic_unchoke_peer_id = peer_id
        # Re-apply choke decisions so this peer gets unchoked if in neighbors
        self.set_preferred_neighbors(
            [p for p in self.neighbors if not self.neighbors[p].am_choking]
        )

    def get_and_reset_download_stats(self) -> Dict[int, int]:
        """
        Called by Scheduler once per UnchokingInterval.
        Returns {peer_id: bytes_downloaded_in_window} and resets the counters.
        """
        stats: Dict[int, int] = {}
        for pid, neighbor in self.neighbors.items():
            stats[pid] = neighbor.download_bytes_window
            neighbor.download_bytes_window = 0
        return stats

    # Helpers

    def broadcast_have(self, piece_index: int) -> None:
        payload = make_have(piece_index)
        for pid, neighbor in self.neighbors.items():
            neighbor.connection.send(payload)
        self.logger.log(
            f"Peer {self.me.peer_id} broadcasted HAVE for piece {piece_index} to all neighbors."
        )

    def is_complete(self) -> bool:
        return self.storage.count_have() == self.storage.meta.num_pieces

    def _has_something_we_want(self, neighbor: NeighborState) -> bool:
        if neighbor.bitfield is None:
            return False
        for idx in range(self.storage.meta.num_pieces):
            if self._bit_is_set(neighbor.bitfield, idx) and not self.storage.has_piece(idx):
                return True
        return False

    @staticmethod
    def _bit_is_set(bits: bytes, idx: int) -> bool:
        byte_index, bit_index = divmod(idx, 8)
        if byte_index >= len(bits):
            return False
        mask = 1 << (7 - bit_index)
        return (bits[byte_index] & mask) != 0

    @staticmethod
    def _set_bit_in_bytes(bits: bytes, idx: int) -> bytes:
        b = bytearray(bits)
        byte_index, bit_index = divmod(idx, 8)
        if byte_index >= len(b):
            return bits
        mask = 1 << (7 - bit_index)
        b[byte_index] |= mask
        return bytes(b)




def init_runtime(me_id: int, workdir: Optional[Path] = None) -> Tuple[CommonCfg, List[PeerInfo], PeerInfo, Storage]:
    """
    Helper that loads Common/PeerInfo, constructs Storage, and returns them.
    Used by peerProcess.py at startup.
    """
    workdir = workdir or Path(".").resolve()
    common = load_common(workdir / "Common.cfg")
    peers = load_peers(workdir / "PeerInfo.cfg")

    try:
        me = next(p for p in peers if p.peer_id == me_id)
    except StopIteration:
        raise SystemExit(f"PeerID {me_id} not found in PeerInfo.cfg")

    meta = FileMeta(
        file_name=common.FileName,
        file_size=common.FileSize,
        piece_size=common.PieceSize,
    )
    storage = Storage(
        workdir=workdir,
        peer_id=me_id,
        meta=meta,
        has_complete_file=me.has_file,
    )
    return common, peers, me, storage
