"""User-owned model connections and immutable, encrypted per-run routing snapshots."""

import base64
import hashlib
import json
import os
import re
import threading
import time
import uuid
from importlib.resources import files
from typing import Annotated, Literal
from urllib.parse import urlsplit

import httpx
from cryptography.fernet import Fernet, InvalidToken
from psycopg.types.json import Jsonb
from pydantic import Field, SecretStr, TypeAdapter, ValidationError

from ..contracts import Contract, Identifier
from .provider import ChatProvider
from .store import BudgetExceeded, StudyError, StudyStore

SCHEMA = """
CREATE TABLE IF NOT EXISTS agent_model_connection (
    connection_id text PRIMARY KEY, owner_id bigint NOT NULL, name text NOT NULL,
    base_url text NOT NULL, credential text NOT NULL, model_ids jsonb NOT NULL,
    enabled boolean NOT NULL, version integer NOT NULL, checks jsonb NOT NULL DEFAULT '{}',
    created_at timestamptz NOT NULL DEFAULT now(), updated_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS agent_model_connection_owner ON agent_model_connection(owner_id);
CREATE TABLE IF NOT EXISTS agent_model_routing (
    owner_id bigint PRIMARY KEY, bindings jsonb NOT NULL, updated_at timestamptz NOT NULL DEFAULT now()
);
"""
PRESET_CATALOG = json.loads(files(__package__).joinpath("model_presets.json").read_text(encoding="utf-8"))
# One catalog supplies both UI choices and exact trusted origins; never trust browser-supplied presets.
DEFAULT_ORIGINS = {
    f"{urlsplit(preset['base_url']).scheme}://{urlsplit(preset['base_url']).netloc}"
    for preset in PRESET_CATALOG["presets"]
} | {
    "http://localhost:8091",
    "http://localhost:11434",
    "http://localhost:1234",
}
ModelId = Annotated[str, Field(min_length=1, max_length=160, pattern=r"^[^\s\x00-\x1f]+$")]
DISCOVERY_LIMIT = 1000
MODEL_ID_ADAPTER = TypeAdapter(ModelId)


def discovery_catalog(payload):
    """Bound the directory independently of the 80 saved-model limit."""
    if not isinstance(payload, dict) or not isinstance(payload.get("data"), list):
        raise StudyError("MODEL_CHECK_FAILED", 422)
    ids = {}
    skipped = 0
    for item in payload["data"]:
        try:
            model = MODEL_ID_ADAPTER.validate_python(item.get("id") if isinstance(item, dict) else None)
        except ValidationError:
            skipped += 1
            continue
        ids[model] = None
    return {
        "model_ids": list(ids)[:DISCOVERY_LIMIT],
        "total_count": len(ids),
        "truncated": len(ids) > DISCOVERY_LIMIT,
        "limit": DISCOVERY_LIMIT,
        "skipped_count": skipped,
        # Do not follow untrusted provider pagination URLs or silently claim completeness.
        "provider_has_more": bool(payload.get("has_more") or payload.get("next") or payload.get("next_page")),
    }


class ConnectionInput(Contract):
    name: Annotated[str, Field(min_length=1, max_length=80)]
    base_url: Annotated[str, Field(min_length=1, max_length=500)]
    api_key: SecretStr | None = None
    clear_key: bool = False
    model_ids: Annotated[list[ModelId], Field(max_length=80)]
    enabled: bool = True


class Binding(Contract):
    connection_id: Identifier | None = None  # None explicitly selects the server environment default.
    model: ModelId | None = None


class Bindings(Contract):
    decision: Binding
    review: Binding


class ModelCommand(Contract):
    owner_id: Annotated[int, Field(ge=1)]
    operation: Literal["LIST", "SAVE", "DELETE", "DISCOVER", "PROBE", "ROUTE", "CLEAR_ROUTES"]
    connection_id: Identifier | None = None
    version: Annotated[int, Field(ge=1)] | None = None
    connection: ConnectionInput | None = None
    model: ModelId | None = None
    bindings: Bindings | None = None


def origin(url):
    try:
        if any(ord(char) < 32 for char in url):
            raise ValueError("Control character")
        parsed = urlsplit(url)
    except ValueError:
        raise StudyError("MODEL_BASE_URL_INVALID", 422) from None
    if (
        parsed.scheme not in {"http", "https"}
        or not parsed.hostname
        or parsed.username is not None
        or parsed.password is not None
        or parsed.query
        or parsed.fragment
        or "\\" in url
        or not re.fullmatch(r"(?:/[A-Za-z0-9._~-]+)*/?", parsed.path)
        or any(part in {".", ".."} for part in parsed.path.split("/"))
    ):
        raise StudyError("MODEL_BASE_URL_INVALID", 422)
    try:
        port = parsed.port
    except ValueError:
        raise StudyError("MODEL_BASE_URL_INVALID", 422) from None
    host = parsed.hostname.lower()
    default = 443 if parsed.scheme == "https" else 80
    return f"{parsed.scheme}://{host}" + (f":{port}" if port and port != default else "")


class ModelRegistry:
    def __init__(self, dsn, secret):
        self.store = StudyStore(dsn)
        derived = base64.urlsafe_b64encode(
            hashlib.sha256(b"model-credentials-v1\0" + secret.encode()).digest()
        )
        self.cipher = Fernet(os.environ.get("AGENT_MODEL_ENCRYPTION_KEY", "").encode() or derived)
        self.allowed = set(DEFAULT_ORIGINS)
        self.allowed.update(
            origin(url.strip())
            for url in os.environ.get("AGENT_MODEL_ALLOWED_ORIGINS", "").split(",")
            if url.strip()
        )
        if os.environ.get("AGENT_LLM_BASE_URL"):
            self.allowed.add(origin(os.environ["AGENT_LLM_BASE_URL"]))
        self.network_slots = threading.BoundedSemaphore(2)

    def initialize(self):
        with self.store.connect() as conn:
            conn.execute("SELECT pg_advisory_xact_lock(7812253)")
            conn.execute(SCHEMA)

    def seal(self, value):
        return self.cipher.encrypt(value.encode()).decode()

    def unseal(self, value):
        try:
            return self.cipher.decrypt(value.encode()).decode()
        except InvalidToken:
            raise StudyError("MODEL_CREDENTIAL_UNAVAILABLE", 503) from None

    def validate_url(self, url):
        if origin(url) not in self.allowed:
            raise StudyError("MODEL_ORIGIN_NOT_ALLOWED", 422)
        return url.rstrip("/")

    def environment(self):
        return bool(os.environ.get("AGENT_LLM_BASE_URL") and os.environ.get("AGENT_LLM_MODEL"))

    def environment_snapshot(self):
        if not self.environment():
            raise StudyError("MODEL_ROUTE_REQUIRED", 409)
        return {
            "connection_id": None,
            "name": "服务器默认",
            "version": 0,
            "base_url": self.validate_url(os.environ["AGENT_LLM_BASE_URL"]),
            "model": os.environ["AGENT_LLM_MODEL"],
            "credential": self.seal(os.environ.get("AGENT_LLM_API_KEY", "")),
        }

    @staticmethod
    def connection(conn, owner, identifier):
        row = conn.execute(
            "SELECT * FROM agent_model_connection WHERE owner_id=%s AND connection_id=%s FOR UPDATE",
            (owner, identifier),
        ).fetchone()
        if not row:
            raise StudyError("MODEL_CONNECTION_NOT_FOUND", 404)
        return row

    def snapshot(self, conn, owner, binding):
        if binding.connection_id is None:
            if binding.model is not None:
                raise StudyError("MODEL_BINDING_INVALID", 422)
            return self.environment_snapshot()
        row = self.connection(conn, owner, binding.connection_id)
        if not row["enabled"] or binding.model not in row["model_ids"]:
            raise StudyError("MODEL_BINDING_UNAVAILABLE", 409)
        return {key: row[key] for key in ["connection_id", "name", "version", "base_url", "credential"]} | {
            "model": binding.model
        }

    def freeze(self, owner):
        with self.store.connect() as conn:
            conn.execute("SELECT pg_advisory_xact_lock(%s)", (owner,))
            row = conn.execute(
                "SELECT bindings FROM agent_model_routing WHERE owner_id=%s", (owner,)
            ).fetchone()
            bindings = Bindings.model_validate(row["bindings"] if row else {"decision": {}, "review": {}})
            return {
                role: self.snapshot(conn, owner, getattr(bindings, role)) for role in ["decision", "review"]
            }

    def client(self, snapshot):
        self.validate_url(snapshot["base_url"])
        return ChatProvider(
            base_url=snapshot["base_url"],
            model=snapshot["model"],
            api_key=self.unseal(snapshot["credential"]),
        )

    def command(self, command):
        owner = command.owner_id
        if command.operation in {"DISCOVER", "PROBE"}:
            return self.network(command)
        with self.store.connect() as conn:
            conn.execute("SELECT pg_advisory_xact_lock(%s)", (owner,))
            if command.operation == "CLEAR_ROUTES":
                conn.execute("DELETE FROM agent_model_routing WHERE owner_id=%s", (owner,))
                return {"saved": True}
            if command.operation == "LIST":
                rows = conn.execute(
                    "SELECT * FROM agent_model_connection WHERE owner_id=%s ORDER BY created_at", (owner,)
                ).fetchall()
                route = conn.execute(
                    "SELECT bindings FROM agent_model_routing WHERE owner_id=%s", (owner,)
                ).fetchone()
                return {
                    "presets": PRESET_CATALOG["presets"],
                    "presets_checked_at": PRESET_CATALOG["checked_at"],
                    "connections": [
                        {
                            key: row[key]
                            for key in [
                                "connection_id",
                                "name",
                                "base_url",
                                "model_ids",
                                "enabled",
                                "version",
                                "checks",
                            ]
                        }
                        | {"has_key": bool(self.unseal(row["credential"]))}
                        for row in rows
                    ],
                    "bindings": route["bindings"] if route else {"decision": {}, "review": {}},
                    "environment": {
                        "available": self.environment(),
                        "model": os.environ.get("AGENT_LLM_MODEL", ""),
                        "mode": os.environ.get("AGENT_LLM_MODE", "real"),
                    },
                }
            if command.operation == "ROUTE":
                if command.bindings is None:
                    raise StudyError("MODEL_BINDING_INVALID", 422)
                for role in ["decision", "review"]:
                    self.snapshot(conn, owner, getattr(command.bindings, role))
                conn.execute(
                    "INSERT INTO agent_model_routing(owner_id,bindings) VALUES (%s,%s) ON CONFLICT(owner_id) DO UPDATE SET bindings=excluded.bindings,updated_at=now()",
                    (owner, Jsonb(command.bindings.model_dump())),
                )
                return {"saved": True}
            if command.operation == "SAVE":
                data = command.connection
                if data is None or not data.name.strip():
                    raise StudyError("MODEL_CONNECTION_INVALID", 422)
                base = self.validate_url(data.base_url)
                row = self.connection(conn, owner, command.connection_id) if command.connection_id else None
                if row and row["version"] != command.version:
                    raise StudyError("MODEL_VERSION_CONFLICT", 409)
                if (
                    not row
                    and conn.execute(
                        "SELECT count(*) AS n FROM agent_model_connection WHERE owner_id=%s", (owner,)
                    ).fetchone()["n"]
                    >= 20
                ):
                    raise StudyError("MODEL_CONNECTION_LIMIT", 409)
                key = data.api_key.get_secret_value() if data.api_key is not None else None
                if key is not None and (len(key) > 4096 or "\n" in key or "\r" in key):
                    raise StudyError("MODEL_CREDENTIAL_INVALID", 422)
                if data.clear_key and key:
                    raise StudyError("MODEL_CREDENTIAL_INVALID", 422)
                if (
                    row
                    and base != row["base_url"]
                    and key is None
                    and not data.clear_key
                    and self.unseal(row["credential"])
                ):
                    # Never send an existing credential to a newly edited destination implicitly.
                    raise StudyError("MODEL_KEY_REQUIRED_FOR_NEW_URL", 422)
                encrypted = (
                    self.seal("")
                    if data.clear_key
                    else self.seal(key)
                    if key is not None
                    else row["credential"]
                    if row
                    else self.seal("")
                )
                identifier = row["connection_id"] if row else str(uuid.uuid4())
                version = row["version"] + 1 if row else 1
                conn.execute(
                    """INSERT INTO agent_model_connection(connection_id,owner_id,name,base_url,credential,model_ids,enabled,version)
                    VALUES (%s,%s,%s,%s,%s,%s,%s,%s) ON CONFLICT(connection_id) DO UPDATE
                    SET name=excluded.name,base_url=excluded.base_url,credential=excluded.credential,
                    model_ids=excluded.model_ids,enabled=excluded.enabled,version=excluded.version,checks='{}',updated_at=now()""",
                    (
                        identifier,
                        owner,
                        data.name.strip(),
                        base,
                        encrypted,
                        Jsonb(list(dict.fromkeys(data.model_ids))),
                        data.enabled,
                        version,
                    ),
                )
                return {"connection_id": identifier, "version": version}
            row = self.connection(conn, owner, command.connection_id)
            if row["version"] != command.version:
                raise StudyError("MODEL_VERSION_CONFLICT", 409)
            route = conn.execute(
                "SELECT bindings FROM agent_model_routing WHERE owner_id=%s", (owner,)
            ).fetchone()
            if route and any(
                b.get("connection_id") == row["connection_id"] for b in route["bindings"].values()
            ):
                raise StudyError("MODEL_CONNECTION_IN_USE", 409)
            conn.execute(
                "DELETE FROM agent_model_connection WHERE owner_id=%s AND connection_id=%s",
                (owner, row["connection_id"]),
            )
            return {"deleted": True}

    def network(self, command):
        with self.store.connect() as conn:
            row = self.connection(conn, command.owner_id, command.connection_id)
            if row["version"] != command.version:
                raise StudyError("MODEL_VERSION_CONFLICT", 409)
            if not row["enabled"]:
                raise StudyError("MODEL_BINDING_UNAVAILABLE", 409)
        self.validate_url(row["base_url"])
        if not self.network_slots.acquire(blocking=False):
            raise StudyError("MODEL_CHECK_BUSY", 503)
        try:
            if command.operation == "DISCOVER":
                headers = (
                    {"Authorization": "Bearer " + self.unseal(row["credential"])}
                    if self.unseal(row["credential"])
                    else {}
                )
                with httpx.Client(timeout=8, follow_redirects=False, trust_env=False) as client:
                    with client.stream("GET", row["base_url"] + "/models", headers=headers) as response:
                        response.raise_for_status()
                        body = bytearray()
                        deadline = time.monotonic() + 8
                        for piece in response.iter_bytes():
                            body.extend(piece)
                            if len(body) > 2 * 1024 * 1024 or time.monotonic() > deadline:
                                raise StudyError("MODEL_RESPONSE_LIMIT", 422)
                return discovery_catalog(json.loads(body))
            if command.model not in row["model_ids"]:
                raise StudyError("MODEL_BINDING_UNAVAILABLE", 409)
            started = time.monotonic()
            code = None
            try:
                provider = self.client({**row, "model": command.model})
                result = provider._request(
                    [
                        {
                            "role": "user",
                            "content": "Call connection_check with ok=true. This is a connection test.",
                        }
                    ],
                    [
                        {
                            "type": "function",
                            "function": {
                                "name": "connection_check",
                                "description": "Check tool calling",
                                "parameters": {
                                    "type": "object",
                                    "properties": {"ok": {"type": "boolean"}},
                                    "required": ["ok"],
                                    "additionalProperties": False,
                                },
                            },
                        }
                    ],
                    8,
                    64,
                )
                if result["calls"] != [{"name": "connection_check", "arguments": {"ok": True}}]:
                    code = "MODEL_TOOL_CONTRACT"
            except Exception as error:  # noqa: BLE001 -- sanitize upstream responses and credentials
                code = (
                    "MODEL_CHECK_TIMEOUT"
                    if isinstance(error, (httpx.TimeoutException, TimeoutError, BudgetExceeded))
                    else "MODEL_CHECK_FAILED"
                )
            check = {
                "ok": code is None,
                "code": code,
                "latency_ms": round((time.monotonic() - started) * 1000),
                "checked_at": int(time.time()),
                "version": row["version"],
            }
            with self.store.connect() as conn:
                updated = conn.execute(
                    "UPDATE agent_model_connection SET checks=checks || %s WHERE owner_id=%s AND connection_id=%s AND version=%s RETURNING connection_id",
                    (Jsonb({command.model: check}), command.owner_id, command.connection_id, row["version"]),
                ).fetchone()
                if not updated:
                    raise StudyError("MODEL_VERSION_CONFLICT", 409)
            return {"check": check}
        except StudyError:
            raise
        except Exception:  # noqa: BLE001 -- no provider response text crosses the management boundary
            raise StudyError("MODEL_CHECK_FAILED", 422) from None
        finally:
            self.network_slots.release()


class RegistryProvider:
    mode = "real"

    def __init__(self, registry):
        self.registry = registry

    def for_run(self, run):
        config = run.get("model_config")
        if config is None:  # Legacy queued runs predate managed model snapshots.
            config = {role: self.registry.environment_snapshot() for role in ["decision", "review"]}
        return RoutedProvider(self.registry, config)


class RoutedProvider:
    mode = "real"

    def __init__(self, registry, config):
        self.config = config
        self.clients = {role: registry.client(snapshot) for role, snapshot in config.items()}

    def identity(self, purpose):
        return {key: self.config[purpose][key] for key in ["connection_id", "name", "version", "model"]}

    def decide(self, messages, timeout):
        return self.clients["decision"].decide(messages, timeout)

    def review(self, messages, timeout):
        return self.clients["review"].review(messages, timeout)

    def feedback(self, messages, schemas, timeout, *, review=False):
        return self.clients["review" if review else "decision"].feedback(
            messages, schemas, timeout, review=review
        )
