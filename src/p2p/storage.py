from __future__ import annotations
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class FileMeta:
    """
    math helpers, describes target file and how its split into pieces
    """
    file_name: str
    file_size: int # bytes
    piece_size: int # bytes

    @property
    def num_pieces(self) -> int:
        # total num piece -> ceiling(file_size / piece_size)
        return (self.file_size + self.piece_size - 1) // self.piece_size

    def piece_len(self, indx: int) -> int:
        # exact length in bytes
        if not (0 <= indx < self.num_pieces):
            raise IndexError(f"piece index out of range: {indx}")
        start = indx * self.piece_size
        end = min(start + self.piece_size, self.file_size)
        return end - start
        # last piece is possibly shorter

class Storage:
    """
    owns on disk file for one peer, peer's local bitfield
    """
    def __init__(
        self,
        workdir: Path,
        peer_id: int,
        meta: FileMeta,
        has_complete_file: bool,
        create_dirs: bool = True,
    ):
        self.meta = meta # keep file description handy

        # each peer write into its own sub folder
        self.peer_dir = workdir / f"peer_{peer_id}"
        self.peer_dir.mkdir(parents=True, exist_ok=True) if create_dirs else None

        # full path top the actual shared file
        self.data_path = self.peer_dir / meta.file_name

        # one bit per piece, big-endian within each byte
        nbits = meta.num_pieces
        self.bitfield = bytearray((nbits + 7) // 8)

        if has_complete_file:
            # mark all bits 1 (present)
            for i in range(meta.num_pieces):
                self._set_bit(i, True)

        else:
            # empty file if missing
            self._ensure_target_file(meta.file_size)

    def has_piece(self, idx: int) -> bool: # return true if we have piece, else false
        byte, bit = divmod(idx, 8)
        mask = 1 << (7 - bit)
        return (self.bitfield[byte] & mask) != 0

    def mark_have(self, idx: int) -> None: # mark as present in local bitfield
        self._set_bit(idx, True)

    def count_have(self) -> int: # count pieces
        # Count set bits
        return sum(bin(b).count("1") for b in self.bitfield)

    def raw_bitfield(self) -> bytes: # return bitfield as raw bytes
        return bytes(self.bitfield)

    def read_piece(self, idx: int) -> bytes: # read exact bytes
        plen = self.meta.piece_len(idx)
        with open(self.data_path, "rb") as f:
            f.seek(idx * self.meta.piece_size)
            data = f.read(plen)
            if len(data) != plen:
                # file might be incomplete/corrupt locally.
                raise IOError(f"short read for piece {idx}: expected {plen}, got {len(data)}")
            return data

    def write_piece(self, idx: int, content: bytes) -> None: # write bytes for piece to disk
        expected = self.meta.piece_len(idx)
        if len(content) != expected:
            raise ValueError(
                f"wrong size for piece {idx}: expected {expected}, got {len(content)}"
            )
        # ensure container file exists & sized
        self._ensure_target_file(self.meta.file_size)

        with open(self.data_path, "r+b") as f:
            f.seek(idx * self.meta.piece_size)
            f.write(content)

        self.mark_have(idx)

    """
        Helpers 
    """

    def _ensure_target_file(self, target_size: int) -> None: # make sure filename exists and is target size bytes
        if not self.data_path.exists():
            # create empty file
            with open(self.data_path, "wb") as _:
                pass
        # grow file if smaller than target
        current = self.data_path.stat().st_size
        if current < target_size:
            # extend by seeking to last byte and writing one zero.
            with open(self.data_path, "r+b") as f:
                f.seek(target_size - 1)
                f.write(b"\x00")

    def _set_bit(self, idx: int, val: bool) -> None: # set/ clear bit for piece
        if not (0 <= idx < self.meta.num_pieces):
            raise IndexError(f"piece index out of range: {idx}")
        byte, bit = divmod(idx, 8)
        mask = 1 << (7 - bit)
        if val:
            self.bitfield[byte] |= mask
        else:
            self.bitfield[byte] &= ~mask