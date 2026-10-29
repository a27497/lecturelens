"""Run harness tests with process/network guards: no service, database or Provider traffic."""

import socket
import sys
import unittest
from pathlib import Path


def guard(event, args):
    if event in {"socket.connect", "socket.bind"} and args[0].family in {
        socket.AF_INET,
        socket.AF_INET6,
    }:
        raise RuntimeError("P11-A tests prohibit IP sockets")
    if event == "socket.getaddrinfo":
        raise RuntimeError("P11-A tests prohibit DNS")
    if event == "subprocess.Popen":
        command = args[1]
        if (
            not isinstance(command, (list, tuple))
            or Path(command[0]).name != "git"
            or command[1] not in {"show", "rev-parse", "status", "diff", "ls-files"}
        ):
            raise RuntimeError("P11-A tests permit only read-only Git subprocesses")


if __name__ == "__main__":
    sys.addaudithook(guard)
    suite = unittest.defaultTestLoader.discover(
        str(Path(__file__).parent), pattern="test_*.py"
    )
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    print(
        "P11_A_BOUNDARY: IP sockets/DNS/service subprocesses forbidden; actual business load=0; real Provider calls=0"
    )
    raise SystemExit(not result.wasSuccessful())
