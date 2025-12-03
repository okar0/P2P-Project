import sys
import socket
import threading
import time
from pathlib import Path

from p2p.config import load_common, load_peers
from p2p.logger import PeerLogger
from p2p.handshake import create_handshake, read_handshake
from p2p.storage import Storage, FileMeta
from p2p.peer import Peer
from p2p.connection import Connection
from p2p.scheduler import Scheduler
from p2p.messages import make_bitfield


class PeerConnection:
    def __init__(self, peer_id, sock, is_initiator):
        self.peer_id = peer_id
        self.sock = sock
        self.is_initiator = is_initiator
        self.am_choking = True
        self.am_interested = False
        self.peer_choking = True
        self.peer_interested = False
        self.bitfield = None
        self.download_rate = 0
        self.bytes_downloaded = 0
        self.lock = threading.Lock()

    def send_message(self, msg_bytes):
        try:
            self.sock.sendall(msg_bytes)
            return True
        except Exception as e:
            print(f"Error sending to peer {self.peer_id}: {e}")
            return False

    def recv_exact(self, n):
        data = b''
        while len(data) < n:
            chunk = self.sock.recv(n - len(data))
            if not chunk:
                raise ConnectionError("Connection closed")
            data += chunk
        return data


class PeerProcess:
    def __init__(self, my_id: int, workdir: Path = None):
        self.my_id = my_id
        self.workdir = workdir or Path(".")

        self.common = load_common(self.workdir / "Common.cfg")
        self.all_peers = load_peers(self.workdir / "PeerInfo.cfg")
        self.me = next(p for p in self.all_peers if p.peer_id == my_id)

        self.logger = PeerLogger(my_id)

        self.meta = FileMeta(
            file_name=self.common.FileName,
            file_size=self.common.FileSize,
            piece_size=self.common.PieceSize,
        )

        self.storage = Storage(
            workdir=self.workdir,
            peer_id=my_id,
            meta=self.meta,
            has_complete_file=self.me.has_file,
            create_dirs=True,
        )

        if self.me.has_file:
            src = self.workdir / self.common.FileName
            if src.exists() and not self.storage.data_path.exists():
                self.storage.data_path.write_bytes(src.read_bytes())

        self.peer = Peer(
            common=self.common,
            all_peers=self.all_peers,
            me=self.me,
            storage=self.storage,
            logger=self.logger,
        )

        self.scheduler = Scheduler(
            peer=self.peer,
            unchoking_interval=self.common.UnchokingInterval,
            optimistic_interval=self.common.OptimisticUnchokingInterval,
            num_preferred=self.common.NumberOfPreferredNeighbors,
        )

        self.server_socket = None
        self.running = True

        self.logger.log(
            f"Peer {my_id} initialized: {self.meta.num_pieces} pieces, "
            f"{len(self.all_peers)} total peers"
        )

    def start(self):
        server_thread = threading.Thread(target=self.run_server, daemon=True)
        server_thread.start()

        time.sleep(1)

        earlier_peers = [p for p in self.all_peers if p.peer_id < self.my_id]
        for peer_info in earlier_peers:
            self.connect_to_peer(peer_info)

        time.sleep(2)
        self.scheduler.start()

        completion_time = None
        shutdown_delay = 10
        had_any_neighbor = False  # <-- new flag

        try:
            while self.running:
                time.sleep(2)

                # track if we've ever had at least one neighbor
                if self.peer.neighbors:
                    had_any_neighbor = True

                # only start shutdown timer if:
                # 1) we are complete AND 2) we've had at least one neighbor
                if self.peer.is_complete() and had_any_neighbor:

                    # NEW shutdown trigger: check if ALL peers have the complete file
                    if self.check_all_peers_complete():

                        if completion_time is None:
                            completion_time = time.time()
                            self.logger.log(
                                f"Peer {self.my_id} detected all peers complete. "
                                f"Waiting {shutdown_delay}s before shutdown..."
                            )

                        elapsed = time.time() - completion_time
                        if elapsed > shutdown_delay:
                            self.logger.log("All peers have completed the download. Shutting down.")
                            print(f"\n[Peer {self.my_id}] All done! Shutting down...")
                            break

                    else:
                        # If not all peers are complete, reset timer
                        completion_time = None


        except KeyboardInterrupt:
            print(f"\n[Peer {self.my_id}] Interrupted by user")
        finally:
            self.shutdown()

    def check_all_peers_complete(self):
        if not self.peer.is_complete():
            return False

        for neighbor in self.peer.neighbors.values():
            if neighbor.bitfield is None:
                return False

            for i in range(self.meta.num_pieces):
                if not self.peer._bit_is_set(neighbor.bitfield, i):
                    return False

        connected_peer_ids = set(self.peer.neighbors.keys())
        all_peer_ids = {p.peer_id for p in self.all_peers if p.peer_id != self.my_id}

        if connected_peer_ids != all_peer_ids:
            return False

        return True

    def run_server(self):
        self.server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.server_socket.bind((self.me.host, self.me.port))
        self.server_socket.listen(10)

        self.logger.log(f"Listening on {self.me.host}:{self.me.port}")
        print(f"[Peer {self.my_id}] Listening on {self.me.host}:{self.me.port}")

        while self.running:
            try:
                self.server_socket.settimeout(1.0)
                try:
                    client_sock, addr = self.server_socket.accept()
                except socket.timeout:
                    continue

                thread = threading.Thread(
                    target=self.handle_incoming_connection,
                    args=(client_sock,),
                    daemon=True
                )
                thread.start()

            except Exception as e:
                if self.running:
                    self.logger.log(f"Server error: {e}")

    def handle_incoming_connection(self, client_sock):
        try:
            handshake_data = client_sock.recv(32)
            if len(handshake_data) != 32:
                client_sock.close()
                return

            remote_peer_id = read_handshake(handshake_data)

            self.logger.log(f"Peer {self.my_id} is connected from Peer {remote_peer_id}.")

            my_handshake = create_handshake(self.my_id)
            client_sock.sendall(my_handshake)

            conn = Connection(
                host=self.me.host,
                port=self.me.port,
                peer_id=remote_peer_id,
                sock=client_sock
            )

            self.peer.register_connection(remote_peer_id, conn)

            if self.storage.count_have() > 0:
                bitfield_msg = make_bitfield(self.storage.raw_bitfield())
                conn.send(bitfield_msg)

            self.handle_peer_messages(conn)

        except Exception as e:
            self.logger.log(f"Error handling incoming connection: {e}")
            try:
                client_sock.close()
            except:
                pass

    def connect_to_peer(self, peer_info):
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.connect((peer_info.host, peer_info.port))

            self.logger.log(f"Peer {self.my_id} makes a connection to Peer {peer_info.peer_id}.")

            my_handshake = create_handshake(self.my_id)
            sock.sendall(my_handshake)

            handshake_data = sock.recv(32)
            if len(handshake_data) != 32:
                sock.close()
                return

            remote_peer_id = read_handshake(handshake_data)

            if remote_peer_id != peer_info.peer_id:
                self.logger.log(
                    f"Handshake mismatch: expected {peer_info.peer_id}, got {remote_peer_id}"
                )
                sock.close()
                return

            conn = Connection(
                host=peer_info.host,
                port=peer_info.port,
                peer_id=remote_peer_id,
                sock=sock
            )

            self.peer.register_connection(remote_peer_id, conn)

            if self.storage.count_have() > 0:
                bitfield_msg = make_bitfield(self.storage.raw_bitfield())
                conn.send(bitfield_msg)

            thread = threading.Thread(
                target=self.handle_peer_messages,
                args=(conn,),
                daemon=True
            )
            thread.start()

        except Exception as e:
            self.logger.log(f"Failed to connect to peer {peer_info.peer_id}: {e}")

    def handle_peer_messages(self, conn: Connection):
        try:
            while self.running:
                msg = conn.receive()
                if msg is None:
                    break

                self.peer.on_message(conn, msg)

        except Exception as e:
            self.logger.log(f"Connection error with peer {conn.peer_id}: {e}")
        finally:
            try:
                conn.close()
            except:
                pass

            if conn.peer_id in self.peer.neighbors:
                del self.peer.neighbors[conn.peer_id]

    def shutdown(self):
        self.running = False

        try:
            self.scheduler.stop()
        except:
            pass

        for neighbor in list(self.peer.neighbors.values()):
            try:
                neighbor.connection.close()
            except:
                pass

        if self.server_socket:
            try:
                self.server_socket.close()
            except:
                pass

        self.logger.log(f"Peer {self.my_id} shut down gracefully")
        print(f"[Peer {self.my_id}] Shutdown complete")

        time.sleep(0.5)


def main():
    if len(sys.argv) != 2:
        print("Usage: python -m peerProcess <peerID>")
        sys.exit(1)

    my_id = int(sys.argv[1])

    peer_process = PeerProcess(my_id)
    peer_process.start()


if __name__ == "__main__":
    main()