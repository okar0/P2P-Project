from pathlib import Path
from src.config import load_common, load_peers
from src.storage import Storage, FileMeta

def init_runtime(me_id: int):
    workdir = Path(".").resolve()
    # load configs from project root
    common = load_common(workdir / "Common.cfg")
    rows = load_peers(workdir / "PeerInfo.cfg")

    # find my row
    try:
        me_row = next(r for r in rows if r.peer_id == me_id)
    except StopIteration:
        raise SystemExit(f"PeerID {me_id} not found in PeerInfo.cfg")

    # build storage (file I/O + local bitfield)
    meta = FileMeta(
        file_name=common.FileName,
        file_size=common.FileSize,
        piece_size=common.PieceSize,
    )
    storage = Storage(
        workdir=workdir,            # keep Common.cfg/PeerInfo.cfg here
        peer_id=me_id,              # creates peer_<id>/ sub folder
        meta=meta,
        has_complete_file=me_row.has_file,
    )

    return common, rows, me_row, storage
