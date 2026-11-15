"""Syslog through the local agent (issue #2). See docs/agent.md, "Syslog".

A hosted Floorbit can't take syslog from the event network: the switches' UDP datagrams would have
to cross the internet, unencrypted and unauthenticated. So the agent listens instead
(``FLOORBIT_AGENT_SYSLOG_PORT``, off when unset) and sends the lines on over its HTTPS connection,
in batches, with the address each came from and when it arrived. The hosted side checks those
senders against its allow-list as if they had sent there (floorbit/syslog.py, ``relay``).

While the hosted Floorbit can't be reached, lines wait in memory, up to ``BACKLOG``; past that the
newest are dropped and counted, so a flood can't eat the machine's memory.
"""
import socketserver
import threading
import time
from collections import deque

MAX_LINE = 2048          # as floorbit/syslog.py
BACKLOG = 20_000
BATCH = 2000             # the hosted side takes at most this many per post
EVERY = 2.0              # seconds between sends while lines come in


class TurnedOff(RuntimeError):
    """The hosted Floorbit has syslog turned off: buffering won't help."""


class Relay:
    def __init__(self, send, port, bind='0.0.0.0', backlog=BACKLOG, log=print):
        """``send(lines, dropped)`` posts one batch; it raises on failure."""
        self.send = send
        self.port = port
        self.bind = bind
        self.backlog = backlog
        self.log = log
        self.lines = deque()
        self.dropped = 0
        self.sent = 0
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._server = None
        self._failing = False

    def receive(self, raw, sender, now=None):
        if isinstance(raw, bytes):
            raw = raw.decode('utf-8', 'replace')
        raw = raw.strip('\x00\r\n ')[:MAX_LINE]
        if not raw:
            return
        with self._lock:
            # The newest go, not the oldest: what came first explains what came after.
            if len(self.lines) >= self.backlog:
                self.dropped += 1
                return
            self.lines.append({'raw': raw, 'from': sender, 'at': time.time() if now is None else now})

    def flush_once(self):
        """Send what waits, a batch at a time. Returns how many went; raises when a send fails
        (the lines stay for the next try)."""
        total = 0
        while True:
            with self._lock:
                batch = [self.lines[i] for i in range(min(BATCH, len(self.lines)))]
                dropped = self.dropped
            if not batch:
                return total
            try:
                self.send(batch, dropped)
            except TurnedOff:
                # Keeping them would only fill the backlog: the hosted side won't take them.
                with self._lock:
                    for _ in batch:
                        self.lines.popleft()
                raise
            with self._lock:
                # Only this thread takes from the left, so these are the lines just sent.
                for _ in batch:
                    self.lines.popleft()
            self.sent += len(batch)
            total += len(batch)

    def _flushing(self):
        while not self._stop.wait(EVERY):
            try:
                self.flush_once()
                if self._failing:
                    self.log(f'[agent] syslog is getting through again ({len(self.lines)} lines waiting)')
                self._failing = False
            except Exception as exc:  # noqa: BLE001  # keep the lines, try again next round
                if not self._failing:
                    self.log(f'[agent] could not send syslog: {exc}; keeping up to {self.backlog} lines')
                self._failing = True

    def start(self):
        relay = self

        class Udp(socketserver.BaseRequestHandler):
            def handle(self):
                relay.receive(self.request[0], self.client_address[0])

        self._server = socketserver.ThreadingUDPServer((self.bind, self.port), Udp)
        threading.Thread(target=self._server.serve_forever, name='agent-syslog', daemon=True).start()
        threading.Thread(target=self._flushing, name='agent-syslog-send', daemon=True).start()
        self.log(f'[agent] listening for syslog on UDP {self._server.server_address[1]}')
        return self._server.server_address[1]

    def stop(self, flush=True):
        self._stop.set()
        if self._server is not None:
            self._server.shutdown()
            self._server.server_close()
            self._server = None
        if flush and self.lines:
            # On the way out (docker stop): one last try, so a restart doesn't lose the backlog.
            try:
                self.flush_once()
            except Exception as exc:  # noqa: BLE001
                self.log(f'[agent] {len(self.lines)} syslog lines could not be sent before stopping: {exc}')
