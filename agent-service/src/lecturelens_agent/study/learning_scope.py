"""Versioned evidence selection and worker compatibility; Java remains the authority."""

from typing import Annotated, Literal

from pydantic import Field, model_validator

from ..contracts import Contract, Identifier


class LearningScope(Contract):
    version: Annotated[int, Field(strict=True, ge=1, le=1)]
    kind: Literal["course", "segments"]
    policy: Literal["strict", "course"]
    revision: Annotated[int, Field(ge=0, strict=True)]
    evidence_ids: Annotated[list[Identifier], Field(max_length=16)]

    @model_validator(mode="after")
    def selection(self):
        if len(set(self.evidence_ids)) != len(self.evidence_ids):
            raise ValueError("Duplicate source selection")
        if self.kind == "course" and (self.evidence_ids or self.policy != "strict"):
            raise ValueError("A whole-course scope has no segment selection")
        if self.kind == "segments" and not self.evidence_ids:
            raise ValueError("Select actual Evidence")
        self.evidence_ids = sorted(self.evidence_ids)
        return self


ACTIVE_SQL = "'queued','running','awaiting_approval','queued_scoped_v1','running_scoped_v1','awaiting_approval_scoped_v1'"


def public_status(status):
    return status.removesuffix("_scoped_v1")


def stored_status(run, status):
    # Old workers only poll queued/running; they cannot claim a scope they cannot enforce.
    return f"{status}_scoped_v1" if run.get("learning_scope") is not None else status


def inject_scope(scope, payload):
    frozen = scope.get("learning_scope")
    if frozen is not None:
        frozen = LearningScope.model_validate(frozen).model_dump()
        if frozen["revision"] != scope["revision"]:
            from .store import StudyError

            raise StudyError("EVIDENCE_SCOPE_MISMATCH")
        payload["learning_scope"] = frozen
    return payload


def check_scope_response(payload, result):
    frozen = payload.get("learning_scope")
    if frozen is None:
        return
    from .store import StudyError

    # A legacy Java server must fail the initial CHECK, before any unscoped search/model call.
    if result.get("learning_scope") != frozen:
        raise StudyError("EVIDENCE_SCOPE_MISMATCH")
    if frozen["kind"] == "segments" and frozen["policy"] == "strict":
        if any(e["evidence_id"] not in frozen["evidence_ids"] for e in result.get("evidence", [])):
            raise StudyError("EVIDENCE_SCOPE_MISMATCH")


def validate_scope_call(scope, action, arguments):
    frozen = scope.get("learning_scope")
    if frozen is None:
        return
    frozen = LearningScope.model_validate(frozen).model_dump()
    from .store import StudyError

    if arguments.get("expand_to_course") and frozen["policy"] != "course":
        raise StudyError("EVIDENCE_SCOPE_MISMATCH")
    if frozen["kind"] == "segments" and frozen["policy"] == "strict":
        ids = (
            arguments.get("evidence_ids", [])
            if action == "READ"
            else [arguments["evidence_id"]]
            if action == "WINDOW"
            else []
        )
        if not set(ids) <= set(frozen["evidence_ids"]):
            raise StudyError("EVIDENCE_SCOPE_MISMATCH")


SCHEMA = """
CREATE OR REPLACE FUNCTION study_learning_scope_fence() RETURNS trigger AS $$
DECLARE parent_scope jsonb;
BEGIN
    IF TG_OP='UPDATE' AND NEW.learning_scope IS DISTINCT FROM OLD.learning_scope THEN
        RAISE EXCEPTION 'Learning scope is immutable';
    END IF;
    IF TG_OP='INSERT' AND NEW.task_kind='feedback' THEN
        SELECT p.learning_scope INTO parent_scope FROM study_attempt a
          JOIN study_artifact x USING(artifact_id) JOIN study_run p ON p.run_id=x.run_id
          WHERE a.attempt_id=NEW.source_attempt_id AND p.session_id=NEW.session_id;
        IF NOT FOUND THEN RAISE EXCEPTION 'Feedback source outside Session'; END IF;
        IF NEW.learning_scope IS NOT NULL AND NEW.learning_scope IS DISTINCT FROM parent_scope THEN
            RAISE EXCEPTION 'Feedback must inherit its source scope';
        END IF;
        NEW.learning_scope := parent_scope;
    END IF;
    IF NEW.learning_scope IS NOT NULL AND NEW.status IN ('queued','running','awaiting_approval') THEN
        NEW.status := NEW.status || '_scoped_v1';
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;
DROP TRIGGER IF EXISTS study_learning_scope_fence ON study_run;
CREATE TRIGGER study_learning_scope_fence BEFORE INSERT OR UPDATE ON study_run
  FOR EACH ROW EXECUTE FUNCTION study_learning_scope_fence();
"""
