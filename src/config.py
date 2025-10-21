from dataclasses import dataclass
from pathlib import Path

@dataclass
class CommonCfg:
    NumberofPreferredNeighbors: int
    UnchokingInterval: int
    OptimisticUnchokingInterval: int
    FileName: str
    FileSize: int
    PieceSize: int

def _kv(line: str):
    k, v = line.strip().split(maxsplit=1)
    return k, v

def load_common(path: str | Path) -> CommonCfg:
    d ={}
    with open(path, "r", encoding = "utf-8") as f:
        for line in f:
            if not line.strip(): continue
            k, v = _kv(line)
            d[k] = v
    return CommonCfg(
        NumberofPreferedNeighbors=int(d["NumberofPreferredNeighbors"]), 
        UnchokingInterval=int(d["UnchokingInterval"]),
        OptimisticUnchokingInterval=int(d["OptimisticUnchokingInterval"]),
            FileName=d["FileName"],
            FileSize=int(d["FileSize"]),
            PieceSize=int(d["PieceSize"]),
    )