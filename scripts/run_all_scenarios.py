#!/usr/bin/env python3
"""Run all test scenarios through the triage pipeline and print a summary table."""

import json
import sys
from pathlib import Path

import httpx

SCENARIOS_DIR = Path(__file__).parent.parent / "tests" / "scenarios"


def main() -> None:
    url = sys.argv[1] if len(sys.argv) > 1 else "http://localhost:8001"

    scenario_files = sorted(SCENARIOS_DIR.glob("*.json"))
    if not scenario_files:
        print(f"No scenario files found in {SCENARIOS_DIR}")
        sys.exit(1)

    results = []
    for path in scenario_files:
        with open(path) as f:
            scenario = json.load(f)

        print(f"Running: {path.name}...", end=" ", flush=True)

        try:
            response = httpx.post(
                f"{url}/reasoners/process_message",
                json=scenario,
                timeout=60.0,
            )
            response.raise_for_status()
            result = response.json()
            results.append((path.name, result, None))
            print("OK")
        except Exception as e:
            results.append((path.name, None, str(e)))
            print(f"FAILED: {e}")

    # Main results table
    print()
    print("=" * 120)
    print(
        f"{'Scenario':<40} {'Category':<20} {'Score':>5} {'Tier':<10} "
        f"{'Routing':<18} {'Overrides'}"
    )
    print("-" * 120)

    for name, result, error in results:
        if error:
            print(f"{name:<40} {'ERROR':<20} {'':>5} {'':<10} {'':<18} {error}")
        else:
            ticket = result["parsed_ticket"]
            overrides = ", ".join(result.get("overrides", [])) or "-"
            print(
                f"{name:<40} "
                f"{ticket['issue_category']:<20} "
                f"{result['risk_score']:>5} "
                f"{result['risk_tier']:<10} "
                f"{result['routing_decision']:<18} "
                f"{overrides}"
            )

    print("=" * 120)

    # Verification summary table
    print()
    print("=" * 100)
    print(f"{'Scenario':<40} {'Verdict':<15} {'Confidence':>10} {'Anomalies'}")
    print("-" * 100)

    for name, result, error in results:
        if error:
            print(f"{name:<40} {'ERROR':<15} {'':>10} {error}")
        else:
            verification = result.get("verification_result")
            if verification:
                verdict = verification.get("overall_verdict", "N/A")
                confidence = f"{verification.get('confidence', 0):.2f}"
                anomalies = ", ".join(verification.get("trace_anomalies", [])) or "-"
                print(f"{name:<40} {verdict:<15} {confidence:>10} {anomalies}")
            else:
                print(f"{name:<40} {'no verifier':<15} {'':>10} -")

    print("=" * 100)

    # Validation summary
    print()
    total_checks = 0
    total_pass = 0
    total_fail = 0
    total_warn = 0

    for name, result, error in results:
        if result and result.get("trace"):
            for v in result["trace"].get("validation_results", []):
                total_checks += 1
                status = v.get("status")
                if status == "pass":
                    total_pass += 1
                elif status == "fail":
                    total_fail += 1
                elif status == "warning":
                    total_warn += 1

    print(f"Validation checks: {total_checks} total | "
          f"\033[32m{total_pass} pass\033[0m | "
          f"\033[31m{total_fail} fail\033[0m | "
          f"\033[33m{total_warn} warning\033[0m")

    passed = sum(1 for _, r, e in results if e is None)
    print(f"\n{passed}/{len(results)} scenarios completed successfully.")


if __name__ == "__main__":
    main()
