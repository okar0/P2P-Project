from dataclasses import dataclass
from pathlib import Path

@dataclass
class CommonCfg:
    NumberofPreferedNeighbors: int
    UnchokingInterval: int
    OptimisticUnchokingInterval: int
    FileName: str
    FileSize: str
    PieceSize: int

def _kv(line: str):
    k, v = line.strip().split(maxsplit=1)
    return k, v