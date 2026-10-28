"""Private choice keys and deterministic, version-bound judgments; no model grader."""

from typing import Annotated

from pydantic import Field, model_validator

from ..contracts import Contract, Identifier
from .store import StudyError


class Option(Contract):
    id: Identifier
    text: Annotated[str, Field(min_length=1, max_length=1500)]


class Choice(Contract):
    question: Annotated[str, Field(min_length=5, max_length=1000)]
    options: Annotated[list[Option], Field(min_length=2, max_length=4)]
    correct_option_id: Identifier
    evidence_ids: Annotated[list[Identifier], Field(min_length=1, max_length=4)]

    @model_validator(mode="after")
    def unique_options(self):
        ids = [option.id for option in self.options]
        texts = [option.text.strip() for option in self.options]
        if len(set(ids)) != len(ids) or len(set(texts)) != len(texts) or not all(texts):
            raise ValueError("Distinct nonempty choices required")
        if self.correct_option_id not in ids:
            raise ValueError("Private key must identify an actual option")
        return self


def public_question(question):
    # A positive allowlist protects READ and explicit ANSWERS from private-key drift.
    keys = ("question", "evidence_ids", "kind", "options")
    return {key: question[key] for key in keys if key in question}


def judge(question, selected_option_id, citations):
    choice = Choice.model_validate({k: question[k] for k in Choice.model_fields})
    options = {option.id: option.text for option in choice.options}
    if selected_option_id not in options:
        raise StudyError("CHOICE_OPTION_REQUIRED_OR_INVALID", 422)
    canonical = {c["evidence_id"]: c for c in citations}
    if not set(choice.evidence_ids) <= set(canonical):
        raise StudyError("CHOICE_CITATION_MISMATCH")
    # Called only while saving a nonempty selection. Equality is the entire grading rule.
    return options[selected_option_id], {
        "is_correct": selected_option_id == choice.correct_option_id,
        "correct_option_id": choice.correct_option_id,
        "citations": [canonical[key] for key in choice.evidence_ids],
    }


SCHEMA = """
CREATE UNIQUE INDEX IF NOT EXISTS study_one_active_choice_run ON study_run(session_id)
    WHERE status IN ('queued','running','awaiting_approval','queued_scoped_v1','running_scoped_v1',
      'awaiting_approval_scoped_v1','queued_cards_v1','running_cards_v1','queued_choice_v1','running_choice_v1');
CREATE OR REPLACE FUNCTION study_choice_worker_fence() RETURNS trigger AS $$
BEGIN
    IF TG_OP='UPDATE' AND NEW.practice_format IS DISTINCT FROM OLD.practice_format THEN
        RAISE EXCEPTION 'Practice format is immutable';
    END IF;
    IF NEW.practice_format NOT IN ('open','choice') OR
       (NEW.practice_format='choice' AND (NEW.task_kind<>'practice' OR NEW.model_mode<>'mock' OR NEW.approval_required)) THEN
        RAISE EXCEPTION 'Unsupported practice format';
    END IF;
    IF NEW.practice_format='choice' AND NEW.status IN ('queued','running') THEN
        NEW.status := NEW.status || '_choice_v1';
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;
CREATE OR REPLACE TRIGGER study_choice_worker_fence BEFORE INSERT OR UPDATE ON study_run
    FOR EACH ROW EXECUTE FUNCTION study_choice_worker_fence();
"""
