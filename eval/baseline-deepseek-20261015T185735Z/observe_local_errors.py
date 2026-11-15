"""Passive local-LLM response-only observer. No requests/credentials or pcaps saved."""

import json
import struct
import subprocess
import sys

from support import append, redact, utc


def exact(stream, n):
    data = bytearray()
    while len(data) < n:
        chunk = stream.read(n - len(data))
        if not chunk:
            return None
        data.extend(chunk)
    return bytes(data)


def main():
    capture = subprocess.Popen(
        [
            "sudo",
            "-n",
            "tcpdump",
            "-i",
            "lo",
            "-n",
            "-s",
            "0",
            "-U",
            "-w",
            "-",
            "tcp src port 8091 and src host 127.0.0.1",
        ],
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
    )
    header = exact(capture.stdout, 24)
    if not header:
        raise RuntimeError("Response-only packet observer unavailable")
    endian = "<" if header[:4] == b"\xd4\xc3\xb2\xa1" else ">"
    network = struct.unpack(endian + "I", header[20:24])[0]
    states = {}
    print(
        json.dumps(
            {
                "observer": "started",
                "link_type": network,
                "filter": "server responses only; no request direction; no raw capture file",
            }
        ),
        flush=True,
    )
    while True:
        packet_header = exact(capture.stdout, 16)
        if not packet_header:
            break
        sec, usec, caplen, _ = struct.unpack(endian + "IIII", packet_header)
        packet = exact(capture.stdout, caplen)
        if packet is None:
            break
        link = {1: 14, 113: 16, 276: 20}.get(network)
        if link is None:
            raise RuntimeError("Unsupported packet link type")
        ip = packet[link:]
        if not ip or ip[0] >> 4 != 4:
            continue
        ihl = (ip[0] & 15) * 4
        if len(ip) < ihl + 20 or ip[9] != 6:
            continue
        tcp = ip[ihl:]
        src, dst, seq = struct.unpack("!HHI", tcp[:8])
        offset = (tcp[12] >> 4) * 4
        if src != 8091:
            continue
        data = tcp[offset:]
        flags = tcp[13]
        key = (ip[12:16], ip[16:20], dst)
        if flags & 2:
            states[key] = {"next": seq + 1, "parts": {}, "buf": bytearray()}
        state = states.setdefault(key, {"next": seq, "parts": {}, "buf": bytearray()})
        if not data:
            continue
        if seq < state["next"]:
            cut = state["next"] - seq
            if cut >= len(data):
                continue
            data = data[cut:]
            seq = state["next"]
        state["parts"][seq] = data
        while state["next"] in state["parts"]:
            part = state["parts"].pop(state["next"])
            state["buf"].extend(part)
            state["next"] += len(part)
        buf = state["buf"]
        while b"\r\n\r\n" in buf:
            end = buf.index(b"\r\n\r\n")
            head = bytes(buf[:end]).decode("latin1")
            if not head.startswith("HTTP/"):
                buf.clear()
                break
            fields = {}
            for line in head.split("\r\n")[1:]:
                if ":" in line:
                    k, v = line.split(":", 1)
                    fields[k.lower()] = v.strip()
            if "content-length" not in fields:
                append(
                    "local-response-observer-errors.jsonl",
                    {
                        "utc": utc(),
                        "error": "Missing Content-Length; original body not retained",
                        "status_line": head.split("\r\n")[0],
                    },
                )
                buf.clear()
                break
            length = int(fields["content-length"])
            total = end + 4 + length
            if length > 8_000_000:
                buf.clear()
                break
            if len(buf) < total:
                break
            body = bytes(buf[end + 4 : total])
            del buf[:total]
            status = int(head.split(" ", 2)[1])
            if status == 400:
                try:
                    parsed = json.loads(body)
                except (ValueError, UnicodeDecodeError):
                    parsed = {"text": body.decode("utf-8", "replace")}
                append(
                    "local-http-400-responses.jsonl",
                    {
                        "utc": utc(),
                        "packet_unix_timestamp": sec + usec / 1e6,
                        "status": status,
                        "client_port": dst,
                        "response_bytes": length,
                        "response_body": redact(parsed),
                        "capture_scope": "original server-to-client HTTP response only; request direction excluded",
                    },
                )
                print(
                    json.dumps(
                        {"http_status": 400, "response_bytes": length, "utc": utc()}
                    ),
                    flush=True,
                )
        if len(buf) > 8_000_000:
            buf.clear()


if __name__ == "__main__":
    try:
        main()
    except (OSError, ValueError, RuntimeError, struct.error) as exc:
        append(
            "local-response-observer-errors.jsonl", {"utc": utc(), "error": str(exc)}
        )
        sys.exit(1)
