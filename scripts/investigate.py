#!/usr/bin/env python3
"""CLI tool for failure investigation via trace analysis.

Usage:
  python scripts/investigate.py trace-msg-001.json
  python scripts/investigate.py trace-msg-001.json --counterfactual "Modified message text"
  python scripts/investigate.py trace-msg-001.json --isolate-agent scorer
"""

import argparse
import json
import sys
from datetime import datetime

import httpx


# ANSI color helpers
RED = "\033[31m"
YELLOW = "\033[33m"
GREEN = "\033[32m"
CYAN = "\033[36m"
BOLD = "\033[1m"
DIM = "\033[2m"
RESET = "\033[0m"


def load_trace(path: str) -> dict:
    """Load a trace JSON file."""
    with open(path) as f:
        return json.load(f)


def format_timestamp(ts: str | None) -> str:
    """Format an ISO timestamp for display."""
    if not ts:
        return "N/A"
    try:
        dt = datetime.fromisoformat(ts)
        return dt.strftime("%H:%M:%S.%f")[:-3]
    except ValueError:
        return ts


def compute_stage_duration(start: str | None, end: str | None) -> str:
    """Compute duration between two ISO timestamps."""
    if not start or not end:
        return "N/A"
    try:
        s = datetime.fromisoformat(start)
        e = datetime.fromisoformat(end)
        ms = (e - s).total_seconds() * 1000
        return f"{ms:.0f}ms"
    except ValueError:
        return "N/A"


def print_timeline(trace: dict) -> None:
    """Pretty-print the full trace timeline."""
    print(f"\n{BOLD}{'='*80}{RESET}")
    print(f"{BOLD}TRACE TIMELINE{RESET} — {trace.get('trace_id', 'unknown')}")
    print(f"{'='*80}")

    # Raw input
    raw = trace.get("raw_input", "")
    print(f"\n{CYAN}Raw Input:{RESET}")
    print(f"  {raw[:200]}{'...' if len(raw) > 200 else ''}")

    # Intake stage
    print(f"\n{BOLD}┌─ INTAKE AGENT{RESET}")
    print(f"│  Start: {format_timestamp(trace.get('intake_start'))}")
    print(f"│  End:   {format_timestamp(trace.get('intake_end'))}")
    print(f"│  Duration: {compute_stage_duration(trace.get('intake_start'), trace.get('intake_end'))}")
    print(f"│  Confidence: {trace.get('intake_confidence', 'N/A')}")
    if trace.get("intake_reasoning"):
        print(f"│  Reasoning: {trace['intake_reasoning']}")
    if trace.get("parsed_ticket_snapshot"):
        snap = trace["parsed_ticket_snapshot"]
        print(f"│  → Category: {snap.get('issue_category')}")
        print(f"│  → Sentiment: {snap.get('customer_sentiment')}")
        print(f"│  → Orders: {snap.get('order_ids', [])}")

    # Scorer stage
    print(f"│")
    print(f"{BOLD}├─ SCORER AGENT{RESET}")
    print(f"│  Start: {format_timestamp(trace.get('scorer_start'))}")
    print(f"│  End:   {format_timestamp(trace.get('scorer_end'))}")
    print(f"│  Duration: {compute_stage_duration(trace.get('scorer_start'), trace.get('scorer_end'))}")
    print(f"│  Confidence: {trace.get('scorer_confidence', 'N/A')}")
    if trace.get("scorer_reasoning"):
        print(f"│  Reasoning: {trace['scorer_reasoning']}")
    if trace.get("scored_ticket_snapshot"):
        snap = trace["scored_ticket_snapshot"]
        print(f"│  → Risk Score: {snap.get('risk_score')}/100")
        print(f"│  → Risk Tier: {snap.get('risk_tier')}")
        print(f"│  → Deterministic: {snap.get('deterministic_score')}")

    # Router stage
    print(f"│")
    print(f"{BOLD}├─ ROUTER AGENT{RESET}")
    print(f"│  Start: {format_timestamp(trace.get('router_start'))}")
    print(f"│  End:   {format_timestamp(trace.get('router_end'))}")
    print(f"│  Duration: {compute_stage_duration(trace.get('router_start'), trace.get('router_end'))}")
    if trace.get("router_reasoning"):
        print(f"│  Reasoning: {trace['router_reasoning']}")
    print(f"│  Final Routing: {trace.get('final_routing_decision', 'N/A')}")

    # Overrides
    overrides = trace.get("overrides_applied", [])
    if overrides:
        print(f"│  Overrides:")
        for o in overrides:
            print(f"│    - {o.get('rule', '?')}: {o.get('reason', '')}")

    # HITL
    if trace.get("hitl_triggered"):
        print(f"│  {YELLOW}HITL: triggered → {trace.get('hitl_outcome', 'pending')}{RESET}")

    print(f"│")
    print(f"{BOLD}└─ TOTAL LATENCY: {trace.get('total_latency_ms', '?')}ms{RESET}")

    # Validation results
    validation = trace.get("validation_results", [])
    if validation:
        print(f"\n{BOLD}VALIDATION CHECKS{RESET}")
        print(f"{'-'*60}")
        for v in validation:
            status = v.get("status", "unknown")
            if status == "fail":
                color = RED
                icon = "✗"
            elif status == "warning":
                color = YELLOW
                icon = "⚠"
            else:
                color = GREEN
                icon = "✓"
            print(f"  {color}[{icon} {status.upper()}]{RESET} {v['check_name']}")
            print(f"    {DIM}{v.get('details', '')}{RESET}")


def run_counterfactual(trace: dict, modified_message: str, url: str) -> None:
    """Re-run the pipeline with a modified input message."""
    print(f"\n{BOLD}COUNTERFACTUAL ANALYSIS{RESET}")
    print(f"Original:  {trace.get('raw_input', '')[:100]}...")
    print(f"Modified:  {modified_message[:100]}...")
    print()

    # Build a scenario from the trace's parsed ticket snapshot
    snapshot = trace.get("parsed_ticket_snapshot", {})
    scored_snapshot = trace.get("scored_ticket_snapshot", {})
    context = scored_snapshot.get("context", {})

    scenario = {
        "message_id": f"counterfactual-{trace.get('trace_id', 'unknown')[:8]}",
        "source_channel": "api",
        "sender_id": "counterfactual",
        "sender_type": "customer",
        "body": modified_message,
        "metadata": {
            "order_value_usd": context.get("order_value_usd"),
            "customer_tier": context.get("customer_tier", "standard"),
            "customer_lifetime_orders": context.get("customer_lifetime_orders", 1),
        },
    }

    try:
        response = httpx.post(
            f"{url}/reasoners/process_message",
            json=scenario,
            timeout=60.0,
        )
        response.raise_for_status()
        result = response.json()
    except Exception as e:
        print(f"{RED}Counterfactual run failed: {e}{RESET}")
        return

    # Compare original vs counterfactual
    orig_snap = trace.get("scored_ticket_snapshot", {})
    print(f"{'Dimension':<25} {'Original':<25} {'Counterfactual':<25}")
    print(f"{'-'*75}")
    print(f"{'Category':<25} {snapshot.get('issue_category', '?'):<25} {result['parsed_ticket']['issue_category']:<25}")
    print(f"{'Risk Score':<25} {orig_snap.get('risk_score', '?'):<25} {result['risk_score']:<25}")
    print(f"{'Risk Tier':<25} {orig_snap.get('risk_tier', '?'):<25} {result['risk_tier']:<25}")
    print(f"{'Routing':<25} {trace.get('final_routing_decision', '?'):<25} {result['routing_decision']:<25}")

    changed = (
        snapshot.get("issue_category") != result["parsed_ticket"]["issue_category"]
        or trace.get("final_routing_decision") != result["routing_decision"]
    )
    if changed:
        print(f"\n{YELLOW}⚠ Different phrasing changed the outcome.{RESET}")
    else:
        print(f"\n{GREEN}✓ Outcome unchanged despite different phrasing.{RESET}")


def run_isolated_agent(trace: dict, agent_name: str, url: str) -> None:
    """Run a single agent in isolation against the trace's recorded input for that stage."""
    print(f"\n{BOLD}ISOLATED AGENT RUN: {agent_name}{RESET}")

    if agent_name == "intake":
        # Re-run intake with the raw input
        scenario = {
            "message_id": f"isolate-intake-{trace.get('trace_id', 'unknown')[:8]}",
            "source_channel": "api",
            "sender_id": "isolated",
            "sender_type": "customer",
            "body": trace.get("raw_input", ""),
            "metadata": {},
        }
        # Note: this will run the full pipeline since intake calls scorer
        # In a real system, you'd have an isolated endpoint
        print(f"  Input: raw message ({len(trace.get('raw_input', ''))} chars)")
        print(f"  Original output: category={trace.get('parsed_ticket_snapshot', {}).get('issue_category')}")
        print(f"  {DIM}(Full isolation requires single-agent endpoint; running full pipeline){RESET}")

    elif agent_name == "scorer":
        parsed_snapshot = trace.get("parsed_ticket_snapshot")
        if not parsed_snapshot:
            print(f"  {RED}No parsed_ticket_snapshot in trace — cannot isolate scorer{RESET}")
            return
        print(f"  Input: ParsedTicket (category={parsed_snapshot.get('issue_category')})")
        scored_snapshot = trace.get("scored_ticket_snapshot") or {}
        print(f"  Original output: risk_score={scored_snapshot.get('risk_score', '?')}, tier={scored_snapshot.get('risk_tier', '?')}")

    elif agent_name == "router":
        scored_snapshot = trace.get("scored_ticket_snapshot")
        if not scored_snapshot:
            print(f"  {RED}No scored_ticket_snapshot in trace — cannot isolate router{RESET}")
            return
        print(f"  Input: ScoredTicket (score={scored_snapshot.get('risk_score')}, tier={scored_snapshot.get('risk_tier')})")
        print(f"  Original output: routing={trace.get('final_routing_decision')}")
        print(f"  Overrides: {[o.get('rule') for o in trace.get('overrides_applied', [])]}")

    else:
        print(f"  {RED}Unknown agent: {agent_name}. Valid: intake, scorer, router{RESET}")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Investigate triage failures via trace analysis"
    )
    parser.add_argument("trace_file", help="Path to trace JSON file")
    parser.add_argument(
        "--counterfactual",
        help="Re-run pipeline with modified input message",
    )
    parser.add_argument(
        "--isolate-agent",
        choices=["intake", "scorer", "router"],
        help="Run a single agent in isolation against its recorded input",
    )
    parser.add_argument(
        "--url",
        default="http://localhost:8001",
        help="Intake agent URL (default: http://localhost:8001)",
    )
    args = parser.parse_args()

    trace = load_trace(args.trace_file)

    # Always print the timeline
    print_timeline(trace)

    # Counterfactual mode
    if args.counterfactual:
        run_counterfactual(trace, args.counterfactual, args.url)

    # Isolate agent mode
    if args.isolate_agent:
        run_isolated_agent(trace, args.isolate_agent, args.url)


if __name__ == "__main__":
    main()
