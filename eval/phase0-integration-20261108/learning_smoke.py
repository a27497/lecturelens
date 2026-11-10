"""Extend the unchanged isolated mock smoke with existing Study learning flows.

Only synthetic data and mock providers are used. The original harness owns fresh
projects, ports, secrets, the offline network guard, process limits and cleanup.
No teaching quality or new learning capability is asserted here.
"""

import argparse
import hashlib
import importlib.util
import traceback
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location(
    "phase0_base_smoke", ROOT / "scripts/ci/mock-study-tutor-e2e.py"
)
BASE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(BASE)


class Phase0Smoke(BASE.Smoke):
    def preflight(self):
        super().preflight()
        # Exercise the existing opt-in feedback protocol only in this new mock stack.
        self.env["STUDY_FEEDBACK_ENABLED"] = "true"
        self.result["phase0_feedback_test_only"] = True
        self.result["phase0_runner_sha256"] = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()

    def start_agent(self):
        self.phase0_agent = super().start_agent()
        return self.phase0_agent

    def read_run(self, run_id):
        return self.study_command("READ", session_id=self.study_session, run_id=run_id)

    def finish_run(self, run_id):
        def read():
            result = self.read_run(run_id)
            assert result["run"]["status"] not in ("failed", "cancelled", "budget_exceeded"), (
                f"Study status={result['run']['status']} code={result['run'].get('error_code')}"
            )
            return result

        return self.wait(read, lambda row: row["run"]["status"] == "succeeded", 100, "Study Run succeeded")

    def flashcards(self):
        super().flashcards()
        with self.stage("phase0-learning-flow"):
            self.result["phase0_observations"] = []
            try:
                self.learning_flow()
            except (AssertionError, KeyError, StopIteration) as error:
                frame = traceback.extract_tb(error.__traceback__)[-1]
                self.result["phase0_failure_location"] = {"line": frame.lineno, "type": type(error).__name__}
                raise AssertionError(
                    f"Phase 0 learning check at line {frame.lineno}: {type(error).__name__}"
                ) from None

    def study_command(self, operation, **body):
        result = super().study_command(operation, **body)
        if "phase0_observations" in self.result:
            run, artifact = result.get("run") or {}, result.get("artifact") or {}
            attempt, feedback, note = (
                result.get("attempt") or {},
                result.get("feedback") or {},
                result.get("note") or {},
            )
            self.result["phase0_observations"].append(
                {
                    "operation": operation,
                    "status": run.get("status"),
                    "error_code": run.get("error_code"),
                    "feedback_enabled": result.get("feedback_enabled"),
                    "questions": len(artifact.get("questions", [])),
                    "attempt_version": attempt.get("version"),
                    "feedback_answer_version": feedback.get("answer_version"),
                    "feedback_mode": (feedback.get("content") or {}).get("mode"),
                    "note_version": note.get("version"),
                    "choice_correct": (attempt.get("choice_result") or {}).get("is_correct"),
                    "wrong_count": result.get("wrong_count"),
                    "correct_count": result.get("correct_count"),
                }
            )
            self.save()
        return result

    def learning_flow(self):
        session = self.study_session
        evidence = self.api("GET", f"/api/tasks/{self.task}/evidence")["items"]
        quote = next(
            item["normalizedText"] for item in evidence if item["retrievable"] and item["normalizedText"]
        )
        started = self.study_command(
            "START",
            session_id=session,
            request_key="phase0-open",
            goal=f"Explain this course passage: {quote[:200]}",
        )
        self.open_run = started["run"]["run_id"]
        practice = self.finish_run(self.open_run)
        artifact = practice["artifact"]
        assert artifact["questions"] and artifact["citations"] and practice["feedback_enabled"]
        assert all(c["evidence_id"] in self.canonical for c in artifact["citations"])
        scope = {
            "session_id": session,
            "run_id": self.open_run,
            "artifact_id": artifact["artifact_id"],
            "question_index": 0,
        }
        attempts, feedback_versions = [], []
        for version in (1, 2):
            answer = dict(
                **scope,
                request_key=f"phase0-answer-{version}",
                expected_version=version - 1,
                answer_text=f"Synthetic saved pipeline explanation version {version}.",
            )
            saved = self.study_command("SAVE_ATTEMPT", **answer)["attempt"]
            assert saved["version"] == version
            assert self.study_command("SAVE_ATTEMPT", **answer)["attempt"] == saved
            attempts.append(saved["attempt_id"])
            feedback_run = self.study_command(
                "START_FEEDBACK",
                **scope,
                attempt_id=saved["attempt_id"],
                request_key=f"phase0-feedback-{version}",
            )["run"]["run_id"]
            feedback = self.finish_run(feedback_run)["feedback"]
            assert feedback["answer_version"] == version and feedback["attempt_id"] == saved["attempt_id"]
            assert feedback["content"]["mode"] == "mock"
            feedback_versions.append(feedback["answer_version"])
            note = self.study_command(
                "SAVE_FEEDBACK_NOTE",
                session_id=session,
                run_id=feedback_run,
                feedback_id=feedback["feedback_id"],
                request_key=f"phase0-note-{version}",
                expected_version=0,
                disposition="acknowledged",
                note_text="Synthetic mechanism check; no correctness claim.",
            )["note"]
            assert note["version"] == 1
        history = self.study_command("ATTEMPT_HISTORY", **scope)["attempts"]
        assert [row["version"] for row in history] == [2, 1]
        assert [row["attempt_id"] for row in history] == attempts[::-1]
        started = self.study_command(
            "START",
            session_id=session,
            request_key="phase0-choice",
            goal=f"Practice recognizing this original course evidence: {quote[:200]}",
            practice_format="choice",
        )
        self.choice_run = started["run"]["run_id"]
        generated = self.finish_run(self.choice_run)["artifact"]
        index, question = next(
            (i, q) for i, q in enumerate(generated["questions"]) if q.get("kind") == "choice"
        )
        assert "correct_option_id" not in question
        choice_scope = {
            "session_id": session,
            "run_id": self.choice_run,
            "artifact_id": generated["artifact_id"],
            "question_index": index,
        }
        selected = question["options"][0]["id"]
        saved = self.study_command(
            "SAVE_ATTEMPT",
            **choice_scope,
            request_key="phase0-choice-first",
            expected_version=0,
            selected_option_id=selected,
        )["attempt"]
        if saved["choice_result"]["is_correct"]:
            selected = next(option["id"] for option in question["options"] if option["id"] != selected)
            saved = self.study_command(
                "SAVE_ATTEMPT",
                **choice_scope,
                request_key="phase0-choice-wrong",
                expected_version=1,
                selected_option_id=selected,
            )["attempt"]
        assert not saved["choice_result"]["is_correct"]
        review = self.study_command("CHOICE_REVIEW")
        assert review["wrong_count"] == 1 and review["correct_count"] == 0
        assert (
            len(review["items"]) == 1 and review["items"][0]["attempt"]["attempt_id"] == saved["attempt_id"]
        )
        before = self.read_run(self.open_run)
        self.stop(self.phase0_agent, kill=True)
        self.start_agent()
        after = self.read_run(self.open_run)
        for key in ("run", "artifact", "attempts", "feedback_runs"):
            assert before[key] == after[key], f"Saved Study {key} changed across process restart"
        assert self.study_command("CHOICE_REVIEW") == review
        self.result["phase0_learning_flow"] = {
            "answer_versions": [row["version"] for row in history],
            "feedback_answer_versions": feedback_versions,
            "save_replay_identical": True,
            "notes_saved": 2,
            "choice_wrong_count": review["wrong_count"],
            "private_key_hidden_before_submission": True,
            "study_and_choice_history_identical_after_sigkill": True,
            "quality": "NOT_RUN; synthetic answers, mock feedback and program key grading only",
        }

    def cross_account(self):
        super().cross_account()
        self.token = ""
        self.login()
        try:
            for operation, body in [
                ("CHOICE_REVIEW", {}),
                ("READ", {"session_id": self.study_session, "run_id": self.open_run}),
                ("READ", {"session_id": self.study_session, "run_id": self.choice_run}),
            ]:
                self.api("POST", self.study, {"operation": operation, **body}, expected=404)
                self.result["cross_account"][f"phase0 {operation} {body.get('run_id', 'course')}"] = 404
        finally:
            self.token = self.owner_token


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--embedding-cache-source", type=Path, required=True)
    args = parser.parse_args()
    args.legacy_only = False
    return Phase0Smoke(args).execute()


if __name__ == "__main__":
    raise SystemExit(main())
