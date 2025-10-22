# P2P-Project

Minimal P2P file sharing project for the **P2PFILESHARINGPROJ** spec.  
Currently includes config parsing (`Common.cfg`, `PeerInfo.cfg`), basic logging, and the `peerProcess` entrypoint.

## Repo Layout
P2P-Project/
- .gitignore
- Common.cfg
- PeerInfo.cfg
- peer_1001/  peer_1002/  peer_1003/   (created at runtime)
- src/
  - peerProcess.py
  - p2p/
    - __init__.py
    - config.py
    - bitfield.py
    - connection.py
    - handshake.py
    - logger.py
    - messages.py
    - peer.py
    - scheduler.py
    - storage.py

> **Note:** Keep `Common.cfg` and `PeerInfo.cfg` in the **repo root** (same folder as `.git/`).

## Prerequisites
- Python 3.10+
- Windows (cmd/PowerShell) or macOS/Linux shell

## How to Run Basic Test
The quick test is starting a peer connection using real configs.

**Windows — Command Prompt (cmd.exe)**
cd C:\path\to\P2P-Project
set PYTHONPATH=src
python -m peerProcess 1001

markdown
Copy code

markdown
Copy code

You should see parsed config output and a new `peer_1001/` directory.  
If the logger is wired, you’ll also see `log_peer_1001.log`.

### Run Multiple Peers (separate terminals)
Terminal 1
cd C:\path\to\P2P-Project
set PYTHONPATH=src
python -m peerProcess 1001

Terminal 2
cd C:\path\to\P2P-Project
set PYTHONPATH=src
python -m peerProcess 1002

Terminal 3
cd C:\path\to\P2P-Project
set PYTHONPATH=src
python -m peerProcess 1003

pgsql
Copy code

## Troubleshooting
- **ModuleNotFoundError: No module named 'p2p'**  
  Ensure `src/p2p/__init__.py` exists and `PYTHONPATH=src` is set. Run from the **repo root**.

- **FileNotFoundError: 'Common.cfg'**  
  Make sure `Common.cfg` and `PeerInfo.cfg` are in the repo root.  
  Alternatively, make paths robust in `src/peerProcess.py`:
  ```python
  from pathlib import Path
  ROOT = Path(__file__).resolve().parents[1]
  common = load_common(ROOT / "Common.cfg")
  peers  = load_peers(ROOT / "PeerInfo.cfg")
