import sys
from pathlib import Path
from p2p.config import load_common, load_peers
from p2p.logger import PeerLogger

def main():
    if len(sys.argv) != 2:
        print("Usage: python -m src.peerProcess <peerID>")
        sys.exit(1)
    my_id = int(sys.argv[1])

    common = load_common("Common.cfg")
    peers  = load_peers("PeerInfo.cfg")
    me = next(p for p in peers if p.peer_id == my_id)

    Path(f"peer_{my_id}").mkdir(exist_ok=True)
    log = PeerLogger(my_id) if 'PeerLogger' in globals() else None
    if log: log.log(f"Peer {my_id} starting on {me.host}:{me.port} | file={common.FileName}")

    print("OK:", common, f"{len(peers)} peers")

if __name__ == "__main__":
    main()
