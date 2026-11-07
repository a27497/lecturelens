"""Disposable cross-service v17 ASGI process. No embedding/model initialization."""

import argparse
import json
import os
import signal
import uuid
from contextlib import contextmanager
from pathlib import Path
from types import SimpleNamespace

import psycopg
import uvicorn
from lecturelens_real_eval.tutor.guarded_app import create_app
from psycopg import sql
from psycopg.conninfo import make_conninfo


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, required=True)
    parser.add_argument("--java-url", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    assert os.environ.get("LECTURELENS_PREFLIGHT_GUARDED") == "1"
    assert 32768 <= args.port <= 65535 and args.java_url.startswith("http://127.0.0.1:")
    args.output.mkdir(parents=True, exist_ok=False)
    dsn = "postgresql://tutor_scale:synthetic-local-only@127.0.0.1:25841/lecturelens_agent_acceptance"
    schema = "v17_cross_" + uuid.uuid4().hex
    with psycopg.connect(dsn) as conn:
        conn.execute(sql.SQL("CREATE SCHEMA {}").format(sql.Identifier(schema)))
    (args.output / "owner.json").write_text(
        json.dumps({"schema": schema, "owner": "tutor-followup-v17-20261108"}) + "\n"
    )
    isolated = make_conninfo(dsn, options=f"-csearch_path={schema},public")
    os.environ.update(
        AGENT_LLM_MODE="mock",
        STUDY_AGENT_ENABLED="false",
        TUTOR_V17_DATABASE_URL=isolated,
        AGENT_JAVA_BASE_URL=args.java_url,
    )

    class NoEmbedding:
        embedder = SimpleNamespace(index_version="phase-mock-no-embedding")

        def search(self, *args):
            raise AssertionError(
                "Cross-service test must not initialize/use embeddings"
            )

    app = create_app(
        retriever=NoEmbedding(), secret="phase-synthetic-service-secret-32-minimum"
    )

    class ExportingServer(uvicorn.Server):
        @contextmanager
        def capture_signals(self):
            # Uvicorn's signal re-emission precedes an outer finally. This test
            # server must finish its own export/schema cleanup after graceful exit.
            previous = {
                sig: signal.signal(sig, self.handle_exit)
                for sig in (signal.SIGINT, signal.SIGTERM)
            }
            try:
                yield
            finally:
                for sig, handler in previous.items():
                    signal.signal(sig, handler)

    try:
        ExportingServer(
            uvicorn.Config(app, host="127.0.0.1", port=args.port, log_level="warning")
        ).run()
    finally:
        with psycopg.connect(isolated) as conn:
            turns = conn.execute(
                "SELECT status,answer,citations,usage,checkpoint->'call_accounting',checkpoint->>'candidate' FROM tutor_turn ORDER BY ordinal"
            ).fetchall()
            (args.output / "runtime.json").write_text(
                json.dumps(
                    {
                        "turns": turns,
                        "real_model_calls": 0,
                        "embedding_calls": 0,
                        "reviewer_calls": 0,
                        "cost_usd": "0",
                        "provider": "VerifiedMock",
                        "schema": schema,
                        "cleanup": "DROP_OWN_SCHEMA",
                    },
                    indent=2,
                )
                + "\n"
            )
        with psycopg.connect(dsn) as conn:
            conn.execute(
                sql.SQL("DROP SCHEMA {} CASCADE").format(sql.Identifier(schema))
            )


if __name__ == "__main__":
    main()
