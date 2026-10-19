"""A Run-scoped connection lease; execution state still comes from PostgreSQL."""

import threading
from contextlib import contextmanager
from contextvars import ContextVar

from .store import RunStopped

execution_connection = ContextVar("study_execution_connection", default=None)


class RunConnection:
    def __init__(self, factory):
        self.factory = factory
        self.connection = None
        self.lock = threading.RLock()
        self.closed = False

    @contextmanager
    def borrow(self):
        # LangGraph propagates context into node threads. Serialize transactions,
        # rather than letting two callers share one transaction on this connection.
        with self.lock:
            if self.closed:
                raise RunStopped()
            if self.connection is None or self.connection.closed or self.connection.broken:
                self.connection = self.factory()
            try:
                # Autocommit outside this block leaves no transaction or row lock
                # across model/tool I/O. Each existing store operation commits alone.
                with self.connection.transaction():
                    yield self.connection
            finally:
                if self.connection.broken:
                    self.connection.close()
                    self.connection = None

    def close(self):
        with self.lock:
            self.closed = True
            if self.connection is not None:
                self.connection.close()
