"""Separate observed list-price usage from unpriced failures and diagnostics."""

import collections
import json

from score import REPORT, records, token_cost


def scope(rows):
    prices = [token_cost(r.get("usage")) for r in rows]
    return {
        "observed_transport_calls": len(rows),
        "http_status_counts": dict(
            collections.Counter(str(r.get("http_status")) for r in rows)
        ),
        "usage_complete_calls": sum(p is not None for p in prices),
        "usage_missing_calls": sum(p is None for p in prices),
        "known_response_list_price_cny": sum(p for p in prices if p is not None),
        "complete_scope_list_price_cny": sum(prices)
        if rows and all(p is not None for p in prices)
        else None,
    }


def main():
    formal = [
        r for r in records(REPORT / "batch-v2/http-calls.jsonl") if r["kind"] == "asr"
    ]
    invalid = [r for r in records(REPORT / "http-calls.jsonl") if r["kind"] == "asr"]
    probes = []
    for name in (
        "readiness-probe.json",
        "readiness-spoken-probe.json",
        "direct-long-diagnostic.json",
    ):
        row = json.loads((REPORT / name).read_text())
        probes.append(
            {
                "source_file": name,
                "http_status": row["http_status"],
                "usage": (row.get("response") or {}).get("usage"),
            }
        )
    scopes = {
        "formal_batch": scope(formal),
        "invalid_proxy_forwarded_calls_excluded_from_baseline": scope(invalid),
        "diagnostics_excluded_from_baseline": scope(probes),
    }
    print(
        json.dumps(
            {
                "scopes": scopes,
                "all_observed_known_list_price_cny": sum(
                    s["known_response_list_price_cny"] for s in scopes.values()
                ),
                "all_observed_usage_missing_calls": sum(
                    s["usage_missing_calls"] for s in scopes.values()
                ),
                "actual_invoice_cny": None,
                "local_translation_and_embedding_external_api_fee_cny": 0,
                "machine_and_electricity_cost_cny": None,
                "budget_guard": "Before each new formal trial: known usage fees + 1 CNY per missing formal response + 3 CNY diagnostic/invalid reserve <=15 CNY. Reserves are control headroom, never measured costs. User cap 30 CNY.",
                "availability": "Unknown failed-request charges are not priced at zero. Catalog usage totals are not invoice amounts. Legacy local proxy guard 402 responses did not forward ASR requests; these are not extra provider-call observations.",
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
