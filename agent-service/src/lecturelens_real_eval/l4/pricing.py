"""Official DeepSeek list prices for the L4 benchmark, in integer nano-USD per token.

Read from https://api-docs.deepseek.com/quick_start/pricing on 2026-11-17 (PLAN.json "pricing").
Peak hours are 01:00-04:00 and 06:00-10:00 UTC, Monday-Friday. Chinese public holidays are
off-peak but are not modelled; counting them as peak only overstates cost.
"""

from datetime import datetime, timezone

PRICE_ID = "deepseek-official-20261117"
RATES = {
    "deepseek-flash": {
        "off_peak": {"hit": 3, "miss": 150, "output": 600},
        "peak": {"hit": 6, "miss": 300, "output": 1200},
    },
    "deepseek-v4-pro": {
        "off_peak": {"hit": 22, "miss": 660, "output": 1980},
        "peak": {"hit": 44, "miss": 1320, "output": 3960},
    },
}
NANO = 1_000_000_000


def tier(at):
    moment = (
        at.astimezone(timezone.utc) if isinstance(at, datetime) else datetime.fromtimestamp(at, timezone.utc)
    )
    peak = moment.weekday() < 5 and (1 <= moment.hour < 4 or 6 <= moment.hour < 10)
    return "peak" if peak else "off_peak"


def usage_tokens(usage):
    """Return (cache_hit, cache_miss, output) or None when usage cannot be priced."""
    if not isinstance(usage, dict):
        return None
    prompt = usage.get("prompt_tokens")
    output = usage.get("completion_tokens")
    if type(prompt) is not int or type(output) is not int or prompt < 0 or output < 0:
        return None
    hit = usage.get("prompt_cache_hit_tokens")
    miss = usage.get("prompt_cache_miss_tokens")
    if type(hit) is int and type(miss) is int and hit >= 0 and miss >= 0 and hit + miss == prompt:
        return hit, miss, output
    # Without a cache split every prompt token is charged at the miss rate (an upper bound).
    return 0, prompt, output


def cost_nano(model, usage, at):
    tokens = usage_tokens(usage)
    if tokens is None:
        return None
    rate = RATES[model][tier(at)]
    hit, miss, output = tokens
    return hit * rate["hit"] + miss * rate["miss"] + output * rate["output"]


def upper_nano(model, input_tokens, output_tokens):
    """Peak-price bound for a request of at most these sizes, all input at the cache-miss rate."""
    rate = RATES[model]["peak"]
    return input_tokens * rate["miss"] + output_tokens * rate["output"]
