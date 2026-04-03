#!/usr/bin/env python3
"""Run all scenarios, collect calibration records, and produce a calibration report.

Compares pipeline predictions against expected values from test scenario files
to measure accuracy by category, risk level, and confidence calibration.
"""

import json
import sys
from collections import defaultdict
from pathlib import Path

import httpx

SCENARIOS_DIR = Path(__file__).parent.parent / "tests" / "scenarios"


def main() -> None:
    url = sys.argv[1] if len(sys.argv) > 1 else "http://localhost:8001"

    scenario_files = sorted(SCENARIOS_DIR.glob("*.json"))
    if not scenario_files:
        print(f"No scenario files found in {SCENARIOS_DIR}")
        sys.exit(1)

    records = []

    for path in scenario_files:
        with open(path) as f:
            scenario = json.load(f)

        expected = scenario.get("expected", {})
        if not expected:
            continue

        print(f"Running: {path.name}...", end=" ", flush=True)

        try:
            response = httpx.post(
                f"{url}/reasoners/process_message",
                json=scenario,
                timeout=60.0,
            )
            response.raise_for_status()
            result = response.json()
            print("OK")
        except Exception as e:
            print(f"FAILED: {e}")
            continue

        ticket = result["parsed_ticket"]
        verification = result.get("verification_result")

        # Parse expected values (some use | for multiple acceptable values)
        expected_categories = expected.get("category", "").split("|")
        expected_tiers = expected.get("risk_tier", "").split("|")
        expected_routings = expected.get("routing", "").split("|")

        actual_category = ticket["issue_category"]
        actual_tier = result["risk_tier"]
        actual_routing = result["routing_decision"]

        record = {
            "scenario": path.name,
            "message_id": result.get("message_id"),
            "actual_category": actual_category,
            "expected_categories": expected_categories,
            "category_correct": actual_category in expected_categories,
            "actual_risk_tier": actual_tier,
            "expected_tiers": expected_tiers,
            "risk_tier_correct": actual_tier in expected_tiers,
            "actual_routing": actual_routing,
            "expected_routings": expected_routings,
            "routing_correct": actual_routing in expected_routings,
            "risk_score": result["risk_score"],
            "extraction_confidence": ticket["extraction_confidence"],
            "verifier_verdict": verification.get("overall_verdict") if verification else None,
            "verifier_confidence": verification.get("confidence") if verification else None,
        }
        records.append(record)

    if not records:
        print("No records to analyze.")
        sys.exit(1)

    # --- Report ---
    print()
    print("=" * 80)
    print("CALIBRATION REPORT")
    print("=" * 80)

    # Overall accuracy
    cat_correct = sum(1 for r in records if r["category_correct"])
    tier_correct = sum(1 for r in records if r["risk_tier_correct"])
    route_correct = sum(1 for r in records if r["routing_correct"])
    total = len(records)

    print(f"\nOverall Accuracy ({total} scenarios):")
    print(f"  Category:  {cat_correct}/{total} ({100*cat_correct/total:.0f}%)")
    print(f"  Risk Tier: {tier_correct}/{total} ({100*tier_correct/total:.0f}%)")
    print(f"  Routing:   {route_correct}/{total} ({100*route_correct/total:.0f}%)")

    # Accuracy by category
    print(f"\nAccuracy by Actual Category:")
    cat_groups = defaultdict(list)
    for r in records:
        cat_groups[r["actual_category"]].append(r)
    for cat, group in sorted(cat_groups.items()):
        correct = sum(1 for r in group if r["category_correct"])
        print(f"  {cat:<25} {correct}/{len(group)}")

    # Accuracy by risk tier
    print(f"\nAccuracy by Actual Risk Tier:")
    tier_groups = defaultdict(list)
    for r in records:
        tier_groups[r["actual_risk_tier"]].append(r)
    for tier, group in sorted(tier_groups.items()):
        correct = sum(1 for r in group if r["risk_tier_correct"])
        print(f"  {tier:<25} {correct}/{len(group)}")

    # Confidence analysis
    correct_confs = [r["extraction_confidence"] for r in records if r["category_correct"]]
    incorrect_confs = [r["extraction_confidence"] for r in records if not r["category_correct"]]

    print(f"\nConfidence Analysis:")
    if correct_confs:
        print(f"  Avg confidence (correct predictions):   {sum(correct_confs)/len(correct_confs):.3f}")
    if incorrect_confs:
        print(f"  Avg confidence (incorrect predictions): {sum(incorrect_confs)/len(incorrect_confs):.3f}")
    else:
        print(f"  Avg confidence (incorrect predictions): N/A (all correct)")

    # Systematic bias detection
    print(f"\nSystematic Bias Detection:")
    scores_by_tier = defaultdict(list)
    for r in records:
        scores_by_tier[r["actual_risk_tier"]].append(r["risk_score"])
    for tier in ["low", "medium", "high", "critical"]:
        if tier in scores_by_tier:
            scores = scores_by_tier[tier]
            avg = sum(scores) / len(scores)
            print(f"  {tier:<10} avg score: {avg:.1f} (n={len(scores)})")

    # Verifier agreement
    verifier_records = [r for r in records if r["verifier_verdict"]]
    if verifier_records:
        print(f"\nVerifier Agreement:")
        verdict_counts = defaultdict(int)
        for r in verifier_records:
            verdict_counts[r["verifier_verdict"]] += 1
        for verdict, count in sorted(verdict_counts.items()):
            print(f"  {verdict:<15} {count}/{len(verifier_records)}")

    # Detail table
    print(f"\n{'='*120}")
    print(f"{'Scenario':<40} {'Cat':>3} {'Tier':>4} {'Route':>5} {'Score':>5} {'Conf':>5} {'Verifier':<12}")
    print(f"{'-'*120}")
    for r in records:
        cat_mark = "\033[32m✓\033[0m" if r["category_correct"] else "\033[31m✗\033[0m"
        tier_mark = "\033[32m✓\033[0m" if r["risk_tier_correct"] else "\033[31m✗\033[0m"
        route_mark = "\033[32m✓\033[0m" if r["routing_correct"] else "\033[31m✗\033[0m"
        verifier = r.get("verifier_verdict", "N/A")
        print(
            f"  {r['scenario']:<38} {cat_mark:>5} {tier_mark:>6} {route_mark:>7} "
            f"{r['risk_score']:>5} {r['extraction_confidence']:>5.2f} {verifier:<12}"
        )
    print(f"{'='*120}")


if __name__ == "__main__":
    main()
