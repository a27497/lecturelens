"""Transaction and cancellation boundaries of Run-scoped connection reuse."""

import contextvars
import threading

import psycopg
import pytest
import test_study
from psycopg.pq import TransactionStatus

from lecturelens_agent.study.connections import execution_connection
from lecturelens_agent.study.contracts import StudyCommand
from lecturelens_agent.study.store import RunStopped

setup = test_study.setup


def claimed(setup):
    store, _, _, _ = setup
    run = test_study.start(setup)
    store.claim(run["run_id"], "lease-test", 90)
    return run


def test_each_operation_commits_and_failed_operation_rolls_back_alone(setup):
    store, _, _, _ = setup
    run = claimed(setup)
    with store.execution_connections():
        store.reserve(run["run_id"], "lease-test", "tool")
        with pytest.raises(ValueError), store.connect() as conn:
            conn.execute("UPDATE study_run SET tool_calls=7 WHERE run_id=%s", (run["run_id"],))
            raise ValueError("rollback this operation")
        with psycopg.connect(store.dsn) as independent:
            independent.execute("SET LOCAL lock_timeout='250ms'")
            assert (
                independent.execute(
                    "SELECT tool_calls FROM study_run WHERE run_id=%s FOR UPDATE", (run["run_id"],)
                ).fetchone()[0]
                == 1
            )
        assert store.guard(run["run_id"], "lease-test")["tool_calls"] == 1


def test_no_transaction_or_row_lock_spans_external_tool_io(setup):
    store, authority, runtime, _ = setup
    original = authority.read
    run = test_study.start(setup)
    checked = []

    def read(scope, action="CHECK", **args):
        if action == "SEARCH":
            lease = execution_connection.get()[1]
            assert lease.connection.info.transaction_status == TransactionStatus.IDLE
            with psycopg.connect(store.dsn) as independent:
                independent.execute("SET LOCAL lock_timeout='250ms'")
                independent.execute(
                    "SELECT run_id FROM study_run WHERE run_id=%s FOR UPDATE", (run["run_id"],)
                )
            checked.append(action)
        return original(scope, action, **args)

    authority.read = read
    runtime.execute(run)
    assert checked and test_study.read(setup)["run"]["status"] == "succeeded"


def test_reused_connection_reads_external_cancellation_in_a_new_transaction(setup):
    store, _, _, scope = setup
    run = claimed(setup)
    with store.execution_connections():
        assert store.guard(run["run_id"], "lease-test")["status"] == "running"
        with psycopg.connect(store.dsn) as conn:
            conn.execute("UPDATE study_run SET status='cancelled' WHERE run_id=%s", (run["run_id"],))
        with pytest.raises(RunStopped):
            store.guard(run["run_id"], "lease-test")
    assert store.command(StudyCommand(**scope, operation="READ"), "mock")["run"]["status"] == "cancelled"


def test_propagated_node_threads_do_not_share_a_transaction(setup):
    store, _, _, _ = setup
    run = claimed(setup)
    first_entered, release, second_entered = threading.Event(), threading.Event(), threading.Event()
    errors = []

    def first():
        try:
            with store.connect() as conn:
                conn.execute("UPDATE study_run SET tool_calls=1 WHERE run_id=%s", (run["run_id"],))
                first_entered.set()
                assert release.wait(5)
        except BaseException as error:  # noqa: BLE001 -- worker failures must fail the parent test
            errors.append(error)

    def second():
        try:
            with pytest.raises(ValueError), store.connect() as conn:
                second_entered.set()
                conn.execute("UPDATE study_run SET tool_calls=2 WHERE run_id=%s", (run["run_id"],))
                raise ValueError("second transaction rolls back")
        except BaseException as error:  # noqa: BLE001 -- worker failures must fail the parent test
            errors.append(error)

    with store.execution_connections():
        workers = [
            threading.Thread(target=contextvars.copy_context().run, args=(fn,)) for fn in (first, second)
        ]
        workers[0].start()
        try:
            assert first_entered.wait(5)
            workers[1].start()
            assert not second_entered.wait(0.05)
        finally:
            release.set()
            for worker in workers:
                if worker.ident is not None:
                    worker.join(5)
        assert not errors and all(not worker.is_alive() for worker in workers)
        assert store.guard(run["run_id"], "lease-test")["tool_calls"] == 1


def test_stale_node_context_cannot_reopen_a_closed_run_lease(setup):
    store, _, _, _ = setup
    with store.execution_connections():
        stale = contextvars.copy_context()
    with pytest.raises(RunStopped):
        stale.run(lambda: store.guard("missing-run", "stale-token"))
    with store.connect() as conn:
        assert conn.execute("SELECT 1 AS value").fetchone()["value"] == 1
