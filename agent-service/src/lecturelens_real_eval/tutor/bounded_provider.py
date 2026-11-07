"""Explicit evaluation adapter; product factories never install a paid Channel."""

from lecturelens_real_eval.tutor_channel import EvalError

from .bounded_runtime import BlockProposal
from .contracts import Search


class BoundedTutorProvider:
    def __init__(self, channel, authority):
        self.channel, self.authority = channel, authority
        self.scope, self.proposals = None, []

    def decide(self, messages, schemas, timeout):
        return self.channel.request(messages, schemas, timeout, validate=self.validate, purpose="tutor")

    def validate(self, result):
        self.proposals.append(result)
        if result["name"] == "search_tutor_evidence":
            Search.model_validate(result["arguments"])
            return
        value = BlockProposal.model_validate(result["arguments"])
        canonical = {e["evidence_id"] for e in self.authority.rows(self.scope)}
        if any(b.evidence_id not in canonical for b in value.blocks + value.evaluation_blocks):
            self.channel.ledger.block("REAL_EVAL_CITATION_FABRICATED")
            raise EvalError("REAL_EVAL_CITATION_FABRICATED")

    def accounting_observation(self):
        call = self.channel.turn_calls[-1] if self.channel.turn_calls else {}
        call_id = call.get("ledger_call_id")
        ledger = self.channel.ledger
        with ledger.locked() as (conn, file):
            records, _ = ledger._check(conn, file)
        row = next((r for r in reversed(records) if r["call_id"] == call_id), None)
        if row is None:
            return {"fee_state": "unknown", "ledger_call_id": call_id, "charged_nano_usd": None}
        return {
            "fee_state": row["state"],
            "ledger_call_id": call_id,
            "reserved_nano_usd": row["reserved_nano_usd"],
            "charged_nano_usd": row["charged_nano_usd"],
            "charge_basis": "conservative_local_ledger_not_supplier_invoice",
        }
