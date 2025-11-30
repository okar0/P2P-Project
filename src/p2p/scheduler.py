import random
import threading
import time
from typing import List, Optional

from p2p.peer import Peer


class Scheduler:
    """
    Handles peer unchoking / choking decisions.
    Calls peer.set_preferred_neighbors() and peer.set_optimistic_unchoke().
    """

    def __init__(
        self,
        peer: Peer,
        unchoking_interval: float,
        optimistic_interval: float,
        num_preferred: int,
    ):
        self.peer = peer
        self.unchoking_interval = unchoking_interval
        self.optimistic_interval = optimistic_interval
        self.num_preferred = num_preferred

        self._stop_event = threading.Event()
        self._lock = threading.Lock()

        self._thread = threading.Thread(target=self._run_loop, daemon=True)

    def start(self):
        self._thread.start()

    def stop(self):
        self._stop_event.set()
        self._thread.join()

    def _run_loop(self):
        last_optimistic = time.time()
        while not self._stop_event.is_set():
            time.sleep(self.unchoking_interval)

            with self._lock:
                self._do_regular_unchoking()

                # Optimistic unchoke check
                now = time.time()
                if now - last_optimistic >= self.optimistic_interval:
                    self._do_optimistic_unchoke()
                    last_optimistic = now

    def _do_regular_unchoking(self):
        """
        Select top N neighbors by download rate (or random if simple) as preferred neighbors.
        """
        stats = self.peer.get_and_reset_download_stats()

        # Sort neighbors by downloaded bytes in last interval, descending
        sorted_peers = sorted(stats.items(), key=lambda x: x[1], reverse=True)
        preferred = [pid for pid, _ in sorted_peers[: self.num_preferred]]

        self.peer.set_preferred_neighbors(preferred)

    def _do_optimistic_unchoke(self):
        """
        Randomly select one choked neighbor to optimistically unchoke.
        """
        choked_peers = [
            pid for pid, neighbor in self.peer.neighbors.items() if neighbor.am_choking
        ]
        if choked_peers:
            optimistic = random.choice(choked_peers)
            self.peer.set_optimistic_unchoke(optimistic)
        else:
            self.peer.set_optimistic_unchoke(None)
