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

    print()
    print("=" * 100)
    print(f"{'Scenario':<30} {'Category':<20} {'Score':>5} {'Tier':<10} {'Routing':<18} {'Overrides'}")
    print("-" * 100)

    for name, result, error in results:
        if error:
            print(f"{name:<30} {'ERROR':<20} {'':>5} {'':<10} {'':<18} {error}")
        else:
            ticket = result["parsed_ticket"]
            overrides = ", ".join(result.get("overrides", [])) or "-"
            print(
                f"{name:<30} "
                f"{ticket['issue_category']:<20} "
                f"{result['risk_score']:>5} "
                f"{result['risk_tier']:<10} "
                f"{result['routing_decision']:<18} "
                f"{overrides}"
            )

    print("=" * 100)

    passed = sum(1 for _, r, e in results if e is None)
    print(f"\n{passed}/{len(results)} scenarios completed successfully.")


if __name__ == "__main__":
    main()
