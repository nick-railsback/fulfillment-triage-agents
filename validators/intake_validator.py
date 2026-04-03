"""Post-Intake semantic validation.

Checks that the Intake agent's extraction makes sense given the raw input.
"""

from datetime import datetime, timezone

from models.ticket import ParsedTicket
from models.trace import TriageTrace, ValidationResult
from config.validation_thresholds import INTAKE_CONFIDENCE_FLOOR


async def validate_intake(
    parsed: ParsedTicket,
    raw_body: str,
    trace: TriageTrace,
    app,
) -> list[ValidationResult]:
    """Run all post-intake semantic checks. Returns ValidationResults and appends to trace."""
    results: list[ValidationResult] = []

    # 1. LLM-as-judge: is the assigned category plausible?
    category_result = await _check_category_plausibility(parsed, raw_body, app)
    results.append(category_result)

    # 2. Entity presence: do extracted entities appear in the raw message?
    entity_result = _check_entity_presence(parsed, raw_body)
    results.append(entity_result)

    # 3. Confidence threshold check
    confidence_result = _check_confidence_threshold(parsed)
    results.append(confidence_result)

    trace.validation_results.extend(results)
    return results


async def _check_category_plausibility(
    parsed: ParsedTicket,
    raw_body: str,
    app,
) -> ValidationResult:
    """Use LLM-as-judge to verify the extracted category is reasonable."""
    judge_prompt = (
        f"Given this raw support message, is the assigned category of "
        f"'{parsed.issue_category}' reasonable?\n\n"
        f"Raw message:\n{raw_body}\n\n"
        f"Respond with ONLY 'pass' or 'fail' on the first line, "
        f"followed by a one-sentence rationale on the second line."
    )

    try:
        response = await app.ai(
            system="You are a quality assurance validator. Evaluate whether a category assignment is reasonable for the given message. Be lenient — only fail if the category is clearly wrong.",
            user=judge_prompt,
        )
        response_text = str(response).strip()
        lines = response_text.split("\n", 1)
        first_line = lines[0].strip().lower()
        # Accept common affirmative phrasings, not just literal "pass"
        if first_line.startswith("pass") or first_line.startswith("yes") or first_line.startswith("reasonable"):
            verdict = "pass"
        elif first_line.startswith("fail") or first_line.startswith("no") or first_line.startswith("unreasonable"):
            verdict = "fail"
        else:
            verdict = "warning"
        rationale = lines[1].strip() if len(lines) > 1 else response_text
    except Exception as e:
        verdict = "warning"
        rationale = f"LLM-as-judge call failed: {e}"

    return ValidationResult(
        check_name="intake_category_plausibility",
        status=verdict,
        details=f"Category '{parsed.issue_category}': {rationale}",
    )


def _check_entity_presence(parsed: ParsedTicket, raw_body: str) -> ValidationResult:
    """Verify extracted entities can be found in the raw message."""
    missing = []
    body_lower = raw_body.lower()

    for oid in parsed.order_ids:
        if oid.lower() not in body_lower:
            missing.append(f"order_id:{oid}")

    for sku in parsed.sku_references:
        if sku.lower() not in body_lower:
            missing.append(f"sku:{sku}")

    for tn in parsed.tracking_numbers:
        if tn.lower() not in body_lower:
            missing.append(f"tracking:{tn}")

    if missing:
        return ValidationResult(
            check_name="intake_entity_presence",
            status="fail",
            details=f"Entities not found in raw message: {', '.join(missing)}",
        )

    entity_count = len(parsed.order_ids) + len(parsed.sku_references) + len(parsed.tracking_numbers)
    return ValidationResult(
        check_name="intake_entity_presence",
        status="pass",
        details=f"All {entity_count} extracted entities found in raw message",
    )


def _check_confidence_threshold(parsed: ParsedTicket) -> ValidationResult:
    """Flag if extraction confidence is below the configured floor."""
    if parsed.extraction_confidence < INTAKE_CONFIDENCE_FLOOR:
        return ValidationResult(
            check_name="intake_confidence_threshold",
            status="warning",
            details=(
                f"Extraction confidence {parsed.extraction_confidence:.2f} "
                f"is below floor of {INTAKE_CONFIDENCE_FLOOR}"
            ),
        )

    return ValidationResult(
        check_name="intake_confidence_threshold",
        status="pass",
        details=f"Extraction confidence {parsed.extraction_confidence:.2f} is acceptable",
    )
