"""Post-Scorer semantic validation.

Checks internal consistency of the hybrid scoring output.
"""

from models.scoring import ScoredTicket
from models.trace import TriageTrace, ValidationResult
from config.validation_thresholds import (
    SCORER_DIVERGENCE_THRESHOLD,
    CATEGORY_SCORE_BOUNDS,
)


def validate_scorer(
    scored: ScoredTicket,
    trace: TriageTrace,
) -> list[ValidationResult]:
    """Run all post-scorer semantic checks."""
    results: list[ValidationResult] = []

    results.append(_check_score_divergence(scored))
    results.append(_check_score_bounds(scored))
    results.append(_check_internal_consistency(scored))

    trace.validation_results.extend(results)
    return results


def _check_score_divergence(scored: ScoredTicket) -> ValidationResult:
    """Check if deterministic and LLM components diverge beyond threshold."""
    # Normalize both to 0-1 scale
    det_normalized = scored.deterministic_score / 60.0
    llm_total = (
        scored.llm_severity.escalation_risk
        + scored.llm_severity.resolution_complexity
        + scored.llm_severity.time_sensitivity
    )
    llm_normalized = llm_total / 40.0

    divergence = abs(det_normalized - llm_normalized)

    if divergence > SCORER_DIVERGENCE_THRESHOLD:
        return ValidationResult(
            check_name="scorer_divergence",
            status="warning",
            details=(
                f"Deterministic ({scored.deterministic_score}/60 = {det_normalized:.2f}) "
                f"and LLM ({llm_total}/40 = {llm_normalized:.2f}) scores diverge "
                f"by {divergence:.2f} (threshold: {SCORER_DIVERGENCE_THRESHOLD})"
            ),
        )

    return ValidationResult(
        check_name="scorer_divergence",
        status="pass",
        details=f"Score divergence {divergence:.2f} within threshold {SCORER_DIVERGENCE_THRESHOLD}",
    )


def _check_score_bounds(scored: ScoredTicket) -> ValidationResult:
    """Verify the composite score falls within expected bounds for the category."""
    category = scored.ticket.issue_category
    bounds = CATEGORY_SCORE_BOUNDS.get(category, (0, 100))
    min_score, max_score = bounds

    if scored.risk_score < min_score or scored.risk_score > max_score:
        return ValidationResult(
            check_name="scorer_bounds",
            status="warning",
            details=(
                f"Risk score {scored.risk_score} for category '{category}' "
                f"is outside expected bounds [{min_score}, {max_score}]"
            ),
        )

    return ValidationResult(
        check_name="scorer_bounds",
        status="pass",
        details=(
            f"Risk score {scored.risk_score} within expected bounds "
            f"[{min_score}, {max_score}] for category '{category}'"
        ),
    )


def _check_internal_consistency(scored: ScoredTicket) -> ValidationResult:
    """Check for obvious inconsistencies between fields.

    Example: a "low" LLM severity with "enterprise" tier and "damaged_item"
    category should not produce a low composite score.
    """
    llm_total = (
        scored.llm_severity.escalation_risk
        + scored.llm_severity.resolution_complexity
        + scored.llm_severity.time_sensitivity
    )

    issues = []

    # High-value enterprise damaged item should not have low LLM severity
    if (
        scored.ticket.issue_category in ("damaged_item", "missing_item")
        and scored.context.customer_tier == "enterprise"
        and llm_total < 10
    ):
        issues.append(
            f"LLM severity ({llm_total}/40) seems low for "
            f"enterprise-tier {scored.ticket.issue_category}"
        )

    # Angry sentiment with very low risk score
    if scored.ticket.customer_sentiment == "angry" and scored.risk_score < 20:
        issues.append(
            f"Risk score {scored.risk_score} seems low for angry customer sentiment"
        )

    if issues:
        return ValidationResult(
            check_name="scorer_internal_consistency",
            status="warning",
            details="; ".join(issues),
        )

    return ValidationResult(
        check_name="scorer_internal_consistency",
        status="pass",
        details="No internal consistency issues detected",
    )
