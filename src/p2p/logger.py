from pathlib import Path
from datetime import datetime

class PeerLogger:
    def __init__(self, peer_id: int):
        self.path = Path(f"log_peer_{peer_id}.log")
    def log(self, msg: str):
        ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        self.path.write_text("", encoding="utf-8") if not self.path.exists() else None
        with self.path.open("a", encoding="utf-8") as f:
            f.write(f"[{ts}] {msg}\n")

# Tiny helper that writes timestamped log messages to the spec-required log file.