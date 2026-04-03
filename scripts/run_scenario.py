#!/usr/bin/env python3
"""CLI: Feed a scenario JSON through the triage pipeline and print results."""

import argparse
import json
import sys

import httpx


def print_validation_results(validation_results: list[dict]) -> None:
    """Print validation check outcomes with status indicators."""
    if not validation_results:
        return

    print("--- Validation Results ---")
    for v in validation_results:
        status = v.get("status", "unknown")
        indicator = {"pass": "\033[32mPASS\033[0m", "fail": "\033[31mFAIL\033[0m", "warning": "\033[33mWARN\033[0m"}.get(status, status)
        print(f"  [{indicator}] {v['check_name']}: {v['details']}")
    print()


def print_verification_result(verification: dict | None) -> None:
    """Print the verifier agent's assessment."""
    if not verification:
        print("--- Verification: not available ---")
        return

    verdict = verification.get("overall_verdict", "unknown")
    verdict_color = {"pass": "\033[32m", "fail": "\033[31m", "needs_review": "\033[33m"}.get(verdict, "")
    print(f"--- Verification: {verdict_color}{verdict.upper()}\033[0m (confidence: {verification.get('confidence', '?')}) ---")
    print(f"  Category:  {verification.get('category_assessment', 'N/A')}")
    print(f"  Scoring:   {verification.get('scoring_assessment', 'N/A')}")
    print(f"  Routing:   {verification.get('routing_assessment', 'N/A')}")
    if verification.get("trace_anomalies"):
        print(f"  Anomalies: {verification['trace_anomalies']}")
    print(f"  Rationale: {verification.get('rationale', 'N/A')}")
    print()


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run a single scenario through the fulfillment triage pipeline"
    )
    parser.add_argument("scenario", help="Path to scenario JSON file")
    parser.add_argument(
        "--url",
        default="http://localhost:8001",
        help="Intake agent URL (default: http://localhost:8001)",
    )
    args = parser.parse_args()

    with open(args.scenario) as f:
        scenario = json.load(f)

    print(f"--- Sending scenario: {args.scenario} ---")
    print(f"Message ID: {scenario['message_id']}")
    print(f"Body: {scenario['body'][:80]}...")
    print()

    try:
        response = httpx.post(
            f"{args.url}/reasoners/process_message",
            json=scenario,
            timeout=60.0,
        )
        response.raise_for_status()
        result = response.json()
    except httpx.ConnectError:
        print(f"ERROR: Could not connect to intake agent at {args.url}")
        print("Make sure the agents are running (docker compose up)")
        sys.exit(1)
    except httpx.HTTPStatusError as e:
        print(f"ERROR: HTTP {e.response.status_code}")
        print(e.response.text)
        sys.exit(1)

    print("=== Triage Result ===")
    print(f"  Message ID:       {result.get('message_id')}")
    print(f"  Issue Category:   {result['parsed_ticket']['issue_category']}")
    print(f"  Sentiment:        {result['parsed_ticket']['customer_sentiment']}")
    print(f"  Confidence:       {result['parsed_ticket']['extraction_confidence']}")
    print(f"  Risk Score:       {result['risk_score']}/100")
    print(f"  Risk Tier:        {result['risk_tier']}")
    print(f"  Routing Decision: {result['routing_decision']}")
    if result.get("overrides"):
        print(f"  Overrides:        {', '.join(result['overrides'])}")
    print()
    print("--- Resolution ---")
    print(json.dumps(result["resolution"], indent=2))
    print()
    print(f"Pipeline duration: {result.get('pipeline_duration_ms', '?')}ms")
    print()

    # Print trace validation results
    trace = result.get("trace")
    if trace:
        print_validation_results(trace.get("validation_results", []))

    # Print verification result
    print_verification_result(result.get("verification_result"))

    # Save trace to file for later investigation
    if trace:
        trace_file = f"trace-{result.get('message_id', 'unknown')}.json"
        with open(trace_file, "w") as f:
            json.dump(trace, f, indent=2)
        print(f"Trace saved to: {trace_file}")


if __name__ == "__main__":
    main()
