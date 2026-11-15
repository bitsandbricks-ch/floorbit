"""NetFlow and IPFIX through the local agent (issue #2). See docs/agent.md, "Traffic".

The agent runs the same flow collector as a Floorbit of your own (floorbit/flows), on
``FLOORBIT_AGENT_FLOWS_PORT``, and sends only its summary on: hall, area and service totals and the
per-seat volume and mix, the same aggregates the Traffic page shows. The flow records themselves,
with addresses and ports, stay on the agent (``FLOWS_DIR``, for ``FLOWS_RETENTION_DAYS``).

To count per seat it needs the seats' addresses: it asks the hosted Floorbit for them every minute.
"""
import socket
import threading

from ..flows.collector import Collector

READ_TIMEOUT = 1.0


class FlowsRelay:
    def __init__(self, agent, port, bind='0.0.0.0', collector=None, log=print):
        self.agent = agent
        self.port = port
        self.bind = bind
        self.log = log
        self.collector = collector or Collector(log=log)
        self.collector.publish = self._publish
        self.sent = 0
        self._failing = False
        self._stop = threading.Event()
        self._sock = None

    def seats(self):
        """For the collector's seat refresh: ({ip: seat}, {seat: area}) from the hosted Floorbit."""
        body = self.agent.flow_seats()
        return body.get('seat_of') or {}, body.get('area_of') or {}

    def _publish(self, snapshot):
        try:
            self.agent.send_flows(snapshot)
            self.sent += 1
            if self._failing:
                self.log('[agent] the traffic summary is getting through again')
            self._failing = False
            return True
        except Exception as exc:  # noqa: BLE001  # the next summary is newer anyway: nothing to keep
            if not self._failing:
                self.log(f'[agent] could not send the traffic summary: {exc}')
            self._failing = True
            return False

    def tick(self, now=None):
        self.collector.housekeeping(now=now, refresh_seats=self.seats)

    def _serve(self):
        while not self._stop.is_set():
            try:
                data, (addr, _port) = self._sock.recvfrom(65535)
                if self.collector.enabled():
                    self.collector.receive(data, addr)
            except TimeoutError:
                pass
            except OSError:
                if self._stop.is_set():
                    return
                raise
            self.tick()

    def start(self):
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            sock.bind((self.bind, self.port))
        except OSError:
            sock.close()
            raise
        sock.settimeout(READ_TIMEOUT)
        self._sock = sock
        threading.Thread(target=self._serve, name='agent-flows', daemon=True).start()
        self.log(f'[agent] listening for NetFlow and IPFIX on UDP {sock.getsockname()[1]}')
        return sock.getsockname()[1]

    def stop(self):
        self._stop.set()
        if self._sock is not None:
            self._sock.close()
            self._sock = None
