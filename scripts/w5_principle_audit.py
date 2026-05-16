"""W5 Three-Principles Audit — works on historical data, no production needed.

Principles to verify:
  P1: Judge is independent of evidence count (low correlation with source_count)
  P2: Judge doesn't treat cluster_status as importance (similar score distributions)
  P3: Guard rails are observable and minimal (1%-20% trigger rate)

Data sources (both historical, mode-b friendly):
  - rss_judgement_runs (last N days) — for guard counters (post P0/P1 only) + token cost
  - rss_signals (last N days) — for importance distribution stratified by cluster_status
                                 + retrospective guard replay via heat_vs_importance_note

Run: PYTHONPATH=. .venv/bin/python scripts/w5_principle_audit.py [--days N]
"""
import re
import sys
import statistics
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone

sys.path.insert(0, "/Users/eason/Documents/Coding/Antigravity/Podcast Project")
from app.clients.firestore_client import firestore_client


LOOKBACK_DAYS = 4

# Regex to parse guard-rail traces from signal.heat_vs_importance_note,
# enabling retrospective analysis on signals judged before P1 counter shipped.
_GUARD_REGEX = re.compile(
    r"\[guard\] (market_wrap|single-source non-systemic earnings|public-health|analysis/feature)",
    re.IGNORECASE,
)
_GUARD_NAME_MAP = {
    "market_wrap": "market_wrap",
    "single-source non-systemic earnings": "single_corp",
    "public-health": "public_health",
    "analysis/feature": "analysis",
}


def replay_guards_from_note(note: str) -> list[str]:
    """Parse signal.heat_vs_importance_note → which guard rules fired (retrospective)."""
    if not note:
        return []
    triggered = []
    for match in _GUARD_REGEX.findall(note):
        canonical = _GUARD_NAME_MAP.get(match.lower())
        if canonical:
            triggered.append(canonical)
    return triggered


def _since_iso(days: int) -> str:
    return (
        (datetime.now(timezone.utc) - timedelta(days=days))
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z")
    )


def _corr(xs: list[float], ys: list[float]) -> float:
    """Pearson correlation, robust to small samples."""
    if len(xs) < 5 or len(xs) != len(ys):
        return 0.0
    n = len(xs)
    mx, my = sum(xs)/n, sum(ys)/n
    num = sum((x-mx)*(y-my) for x, y in zip(xs, ys))
    dx = sum((x-mx)**2 for x in xs) ** 0.5
    dy = sum((y-my)**2 for y in ys) ** 0.5
    if not dx or not dy:
        return 0.0
    return round(num / (dx * dy), 3)


def main():
    since = _since_iso(LOOKBACK_DAYS)
    print(f"Auditing W5 from {since}\n")

    # === Pull judgement runs ===
    runs = firestore_client.list_recent_judgement_runs(since)
    print(f"Found {len(runs)} judgement runs in last {LOOKBACK_DAYS} days")
    if not runs:
        print("No runs — wait longer or check if /signals/judge is firing.")
        return

    # === Pull signals (only judged ones) ===
    signals = [s for s in firestore_client.list_recent_signals(since, limit=4000) if s.importance_score is not None]
    print(f"Found {len(signals)} judged signals\n")

    # ============================================================
    # PRINCIPLE 1: Verify is pure-evidence (Judge not contaminated)
    # ============================================================
    print("=" * 80)
    print("PRINCIPLE 1: importance_score correlation with source_count")
    print("=" * 80)
    xs = [s.source_count for s in signals]
    ys = [s.importance_score for s in signals]
    r1 = _corr([float(x) for x in xs], [float(y) for y in ys])
    if abs(r1) < 0.25:
        verdict1 = "✅ PASS — Judge is independent of evidence count"
    elif abs(r1) < 0.45:
        verdict1 = "⚠️  WARN — some correlation, monitor"
    else:
        verdict1 = "❌ FAIL — Judge is leaking verify info, strip source_count from prompt"
    print(f"  Pearson r(importance, source_count) = {r1}")
    print(f"  Verdict: {verdict1}")

    # ============================================================
    # PRINCIPLE 2: Judge independent of cluster_status
    # ============================================================
    print("\n" + "=" * 80)
    print("PRINCIPLE 2: importance_score distribution by cluster_status")
    print("=" * 80)
    by_status = defaultdict(list)
    for s in signals:
        if s.cluster_status:
            by_status[s.cluster_status].append(s.importance_score)
    medians = {}
    for status in sorted(by_status.keys()):
        vals = by_status[status]
        if len(vals) >= 3:
            medians[status] = statistics.median(vals)
            print(f"  {status:<22} n={len(vals):>4}  median importance = {medians[status]:.1f}")
        else:
            print(f"  {status:<22} n={len(vals):>4}  (too few)")
    spread = max(medians.values()) - min(medians.values()) if medians else 0
    print(f"  → median spread across statuses: {spread:.1f} points")
    if spread < 15:
        verdict2a = "✅ PASS — distributions consistent"
    elif spread < 25:
        verdict2a = "⚠️  WARN — slight coupling"
    else:
        verdict2a = "❌ FAIL — Judge treats cluster_status as importance"
    print(f"  Verdict: {verdict2a}")

    # Single-source high-importance rate
    single_high = sum(
        1 for s in signals
        if s.cluster_status == "single_source" and (s.importance_score or 0) >= 70
    )
    single_total = sum(1 for s in signals if s.cluster_status == "single_source")
    rate = single_high / max(1, single_total)
    print(f"\n  single_source signals at importance ≥ 70: {single_high}/{single_total} = {100*rate:.1f}%")
    if rate >= 0.05:
        verdict2b = "✅ healthy — Judge rewards strong single-source"
    elif rate >= 0.01:
        verdict2b = "⚠️  borderline — review some cases"
    else:
        verdict2b = "❌ FAIL — Judge dismisses single-source (need publisher_tier gate)"
    print(f"  Verdict: {verdict2b}")

    # ============================================================
    # PRINCIPLE 3: Guard rails — trigger rate per rule
    # Two data paths:
    #   (a) Runs with P1 counter (post-deploy) — authoritative
    #   (b) Retrospective replay from signal.heat_vs_importance_note — historical
    # ============================================================
    print("\n" + "=" * 80)
    print("PRINCIPLE 3: Guard rails trigger rate")
    print("=" * 80)

    # Path (a): from run-level counters (only runs that have the field)
    total_judged_with_counter = sum(
        getattr(r, "judged_signal_count", 0) for r in runs
        if getattr(r, "guard_rails_triggered", None)
    )
    rule_totals_a: Counter[str] = Counter()
    for r in runs:
        for rule, count in (getattr(r, "guard_rails_triggered", {}) or {}).items():
            rule_totals_a[rule] += count

    # Path (b): retrospective replay across all signals
    rule_totals_b: Counter[str] = Counter()
    signals_with_notes = 0
    for s in signals:
        triggered = replay_guards_from_note(s.heat_vs_importance_note or "")
        if triggered:
            signals_with_notes += 1
        for rule in triggered:
            rule_totals_b[rule] += 1
    total_judged_all = len(signals)

    print(f"  (a) Run-level counter (post-P1): {total_judged_with_counter} judged signals")
    if total_judged_with_counter > 0:
        for rule in ["market_wrap", "single_corp", "public_health", "analysis"]:
            count = rule_totals_a.get(rule, 0)
            rate = count / total_judged_with_counter
            print(f"      {rule:<14} fired {count:>4} = {100*rate:>5.1f}%")
    else:
        print(f"      (no P1-tagged runs yet — replay below)")

    print(f"\n  (b) Retrospective replay: {total_judged_all} judged signals "
          f"({signals_with_notes} had guard traces)")
    if total_judged_all > 0:
        for rule in ["market_wrap", "single_corp", "public_health", "analysis"]:
            count = rule_totals_b.get(rule, 0)
            rate = count / total_judged_all
            if rate < 0.01:
                tag = "🗑️  KILL — rule dead, no longer fires"
            elif rate <= 0.10:
                tag = "✅ KEEP — healthy observation"
            elif rate <= 0.20:
                tag = "⚠️  HOT — review prompt"
            else:
                tag = "❌ FIX — prompt has structural problem"
            print(f"      {rule:<14} fired {count:>4} = {100*rate:>5.1f}%   {tag}")

    # Multi-trigger detection (same signal hit by 2+ rules)
    multi_trigger = sum(
        1 for s in signals
        if len(set(replay_guards_from_note(s.heat_vs_importance_note or ""))) >= 2
    )
    print(f"\n  Multi-trigger (2+ caps on same signal): {multi_trigger}")
    if multi_trigger > total_judged_all * 0.05:
        print(f"  ⚠️  > 5% signals hit by multiple rules — caps may be overlapping")

    # ============================================================
    # P0 verification: cost sanity
    # ============================================================
    print("\n" + "=" * 80)
    print("P0 fix verification: cost sanity")
    print("=" * 80)
    total_cost = sum(getattr(r, "total_cost_usd", 0.0) or 0.0 for r in runs)
    total_input = sum(getattr(r, "total_input_tokens", 0) or 0 for r in runs)
    total_output = sum(getattr(r, "total_output_tokens", 0) or 0 for r in runs)
    print(f"  Total cost over {LOOKBACK_DAYS}d: ${total_cost:.4f}")
    print(f"  Total tokens: input={total_input:,}  output={total_output:,}")
    avg_cost_per_signal = total_cost / max(1, total_judged_all)
    print(f"  Avg cost per judged signal: ${avg_cost_per_signal:.6f}")
    # Sanity: Flash should be ~$0.0002-$0.0005 per signal
    if avg_cost_per_signal < 0.0008:
        print(f"  ✅ Cost looks like Flash pricing (P0 fix working)")
    elif avg_cost_per_signal < 0.005:
        print(f"  ⚠️  Cost between Flash and Pro — might be mixed model")
    else:
        print(f"  ❌ Cost still inflated like Pro — P0 fix not applied or not yet redeployed")


if __name__ == "__main__":
    main()
