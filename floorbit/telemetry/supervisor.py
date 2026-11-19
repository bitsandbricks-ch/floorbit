"""Telegraf run by the agent itself (docs/agent.md, "Telegraf"): the agent image carries the
binary, so there is no sidecar to forget, and the agent reads what Telegraf says about each device.

Started on its config, restarted when it stops (waiting longer each time, up to a minute), told
to reload with SIGHUP when the config changes, stopped with the plugin.
"""
import collections
import contextlib
import os
import shutil
import signal
import subprocess
import threading
import time

BINARY_ENV = 'FLOORBIT_TELEGRAF_BIN'
MAX_WAIT = 60
KEPT_LINES = 20


def binary():
    """Telegraf's path, or None when this machine has none (an older agent image, a test)."""
    configured = os.environ.get(BINARY_ENV)
    if configured:
        return configured if os.path.isfile(configured) and os.access(configured, os.X_OK) else None
    return shutil.which('telegraf')


class Telegraf:
    def __init__(self, path, conf, on_line, log, stopping):
        self.path, self.conf = path, conf
        self.on_line, self.log, self.stopping = on_line, log, stopping
        self.proc = None
        self.started_at = None
        self.exits = 0
        self.last_exit = None          # (when, code, last lines)
        self.lines = collections.deque(maxlen=KEPT_LINES)
        self._lock = threading.Lock()

    def running(self):
        return self.proc is not None and self.proc.poll() is None

    def start(self):
        threading.Thread(target=self._keep_running, name='telemetry-telegraf', daemon=True).start()

    def _keep_running(self):
        wait = 2
        while not self.stopping.is_set():
            try:
                with self._lock:
                    self.proc = subprocess.Popen(
                        [self.path, '--config', self.conf], stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                        text=True, errors='replace', start_new_session=True)
                    self.started_at = time.time()
                self.log(f'Telegraf started (pid {self.proc.pid})')
            except OSError as exc:
                self.log(f'cannot start Telegraf ({self.path}): {exc}')
                self.last_exit = (time.time(), None, [str(exc)])
                self.stopping.wait(MAX_WAIT)
                continue
            for line in self.proc.stdout:
                line = line.rstrip()
                self.lines.append(line)
                try:
                    self.on_line(line)
                except Exception as exc:  # noqa: BLE001  # one odd line must not stop the reader
                    self.log(f'could not read a Telegraf line: {exc}')
            code = self.proc.wait()
            if self.stopping.is_set():
                return
            self.exits += 1
            self.last_exit = (time.time(), code, list(self.lines)[-5:])
            ran = time.time() - (self.started_at or time.time())
            wait = 2 if ran > 300 else min(wait * 2, MAX_WAIT)
            last = next((x for x in reversed(self.lines) if ' E! ' in x), self.lines[-1] if self.lines else '')
            self.log(f'Telegraf stopped (exit code {code}), starting it again in {wait} s: {last}')
            self.stopping.wait(wait)

    def reload(self):
        """The config changed: Telegraf reads it again without dropping its listeners."""
        with self._lock:
            if self.running():
                with contextlib.suppress(OSError):
                    self.proc.send_signal(signal.SIGHUP)
                    self.log('Telegraf reads its config again (the devices changed)')

    def stop(self):
        with self._lock:
            proc = self.proc
        if proc is not None and proc.poll() is None:
            proc.terminate()
            try:
                proc.wait(10)
            except subprocess.TimeoutExpired:
                proc.kill()
            self.log('Telegraf stopped (the plugin stops)')
