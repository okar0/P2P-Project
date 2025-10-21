from dataclasses import dataclass
from pathlib import Path
from typing import Union
import math

@dataclass
class CommonCfg:
    NumberOfPreferredNeighbors: int
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
        for i, line in enumerate(f, 1):
            if _is_comment_or_blank(line): 
                continue   
            try:
                k, v = _kv(line)
            except ValueError:
                raise ValueError(f"{path}:{i}: expected 'Key Value', got {line!r}")
            d[k] = v
    try:
        cfg = CommonCfg(
            NumberOfPreferredNeighbors=int(d["NumberOfPreferredNeighbors"]),
            UnchokingInterval=int(d["UnchokingInterval"]),
            OptimisticUnchokingInterval=int(d["OptimisticUnchokingInterval"]),
            FileName=d["FileName"],
            FileSize=int(d["FileSize"]),
            PieceSize=int(d["PieceSize"]),
        )
    except KeyError as e:
        raise ValueError(f"{path}: missing key {e.args[0]!r}")
    except ValueError as e:
        raise ValueError(f"{path}: invalid numeric value: {e}")
    _validate_common(cfg, path)
    return cfg

def _validate_common(c: CommonCfg, path: Union[str, Path]) -> None:
    if c.FileSize <= 0 or c.PieceSize <= 0:
        raise ValueError(f"{path}: FileSize and PieceSize must be > 0")
    if c.PieceSize > c.FileSize:
        raise ValueError(f"{path}: PieceSize cannot exceed FileSize")
    
    def load_peers(path: Union[str, Path]) -> list[PeerInfo]:

        peers: list[PeerInfo] = []
        path = Path(path)
        with path.open("r", encoding="utf-8") as f:
            for i, line in enumerate(f, 1):
                if _is_comment_or_blank(line):
                    continue
                parts = line.split()
                if len(parts) != 4:
                    raise ValueError(f"{path}:{i}: expected 'id host port has_file'")
                pid, host, port, has = parts
                peers.append(PeerInfo(
                    peer_id=int(pid),
                    host=host,
                    port=int(port),
                    has_file=(has == "1")
                ))
        return peers