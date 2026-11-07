"""V18 output allowance with an independently bounded three-turn smoke liability."""

from dataclasses import dataclass, replace

from lecturelens_real_eval.tutor_channel import EvalError, TutorPolicy

from .usable_runtime import OUTPUT_TOKENS


@dataclass(frozen=True)
class UsablePolicy(TutorPolicy):
    max_tokens: int = OUTPUT_TOKENS
    max_calls: int = 12
    max_nano_usd: int = 300_000_000

    def validate(self):
        # Keep all original route/model/live/candidate checks; extend only the
        # explicitly versioned output allowance and tighten the run's liability.
        TutorPolicy.validate(replace(self, max_tokens=1200))
        if (
            type(self.max_tokens) is not int
            or self.max_tokens != OUTPUT_TOKENS
            or self.max_calls > 12
            or self.max_nano_usd > 300_000_000
        ):
            raise EvalError("V18_SMOKE_POLICY_INVALID")
