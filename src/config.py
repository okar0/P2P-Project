from dataclasses import dataclass
from pathlib import Path
from typing import Union
import math

@dataclass
class CommonCfg:
    NumberofPreferredNeighbors: int
    UnchokingInterval: int
    OptimisticUnchokingInterval: int
    FileName: str
    FileSize: int
    PieceSize: int

@dataclass
class PeerInfo:
    peer_id: int
    host: str
    port: int
    has_file: bool

def _is_comment_or_blank(line: str) -> bool:
    s = line.strip()
    return not s or s.startswith("#")

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