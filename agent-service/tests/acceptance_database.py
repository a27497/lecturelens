"""Expose only the explicitly supplied test PG on a ledger-compatible loopback port.

CI's existing PG listens on 5432. This test-only forwarder preserves the ledger's
20000..32767 rule without changing production validation or the CI workflow.
"""

import os
import random
import select
import socket
import socketserver
import threading
from contextlib import contextmanager

from psycopg.conninfo import conninfo_to_dict, make_conninfo


@contextmanager
def ledger_database():
    dsn = os.environ["AGENT_TEST_DATABASE_URL"]
    config = conninfo_to_dict(dsn)
    if (
        config.get("host") != "127.0.0.1"
        or config.get("hostaddr") not in (None, "127.0.0.1")
        or config.get("service")
        or config.get("dbname") != "lecturelens_agent_test"
    ):
        raise ValueError("Explicit isolated test PG required")
    port = int(config["port"])
    if 20000 <= port < 32768:
        yield make_conninfo(dsn, hostaddr="127.0.0.1")
        return
    if port != 5432:
        raise ValueError("Only the existing CI test port may be forwarded")
    connect_upstream = socket.create_connection

    class Handler(socketserver.BaseRequestHandler):
        def handle(self):
            with connect_upstream(("127.0.0.1", port), timeout=5) as upstream:
                peers = (self.request, upstream)
                while not stop.is_set():
                    ready, _, _ = select.select(peers, [], [], 0.1)
                    for source in ready:
                        data = source.recv(65536)
                        if not data:
                            return
                        (upstream if source is self.request else self.request).sendall(data)

    class Server(socketserver.ThreadingTCPServer):
        daemon_threads = True

    stop = threading.Event()
    for _ in range(50):
        try:
            server = Server(("127.0.0.1", random.randrange(20000, 32768)), Handler)
            break
        except OSError:
            continue
    else:
        raise RuntimeError("No free isolated forwarding port")
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield make_conninfo(dsn, hostaddr="127.0.0.1", port=server.server_address[1])
    finally:
        stop.set()
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)
