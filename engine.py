"""
engine.py — The scoring engine for Weather Scout.

Takes a SearchProfile and weather data, produces scored results per location
per forecast day. This is the core logic — it doesn't know where weather data
comes from (that's the provider's job) or how results are displayed.

Scoring Philosophy:
  - Each criterion produces a score from 0.0 to 1.0
  - Required criteria act as gates: if any fails, the location score is 0
  - Weighted criteria are combined via the profile's scoring method
  - Final scores are scaled to 0-100 for human readability
"""

import math
from dataclasses import dataclass, field
from typing import Optional
from datetime import datetime


# ── Score Result Types ──────────────────────────────────────────────────────────

@dataclass
class CriterionResult:
    """Result of evaluating a single criterion against weather data."""
    label: str
    field: str
    operator: str
    threshold: float
    actual_value: Optional[float]
    passed: bool           # Did it meet the threshold?
    raw_score: float       # 0.0 – 1.0 score for this criterion
    weighted_score: float  # raw_score * weight
    weight: float
    required: bool
    ideal: Optional[float] = None
    scoring_curve: str = "linear"

    @property
    def status_icon(self) -> str:
        if self.actual_value is None:
            return "❓"
        if not self.passed and self.required:
            return "🔴"
        if not self.passed:
            return "🟡"
        if self.raw_score >= 0.8:
            return "🟢"
        return "🔵"


@dataclass
class LocationResult:
    """Scored result for a single location on a single forecast day."""
    location_name: str
    lat: float
    lon: float
    forecast_date: str               # ISO date
    criteria_results: list           # List[CriterionResult]
    total_score: float               # 0-100
    pass_threshold_met: bool
    highlight_threshold_met: bool
    any_required_failed: bool
    scoring_method: str

    @property
    def grade(self) -> str:
        if self.any_required_failed:
            return "FAIL"
        if self.highlight_threshold_met:
            return "EXCEPTIONAL"
        if self.pass_threshold_met:
            return "GOOD"
        return "MARGINAL"


@dataclass
class ScoutReport:
    """Complete report for one profile run."""
    profile_name: str
    profile_description: str
    run_timestamp: str
    location_results: list  # List[LocationResult]
    best_result: Optional[LocationResult] = None

    def __post_init__(self):
        if self.location_results:
            self.best_result = max(self.location_results, key=lambda r: r.total_score)


# ── Scoring Curves ──────────────────────────────────────────────────────────────

def score_linear(actual: float, threshold: float, ideal: float, operator: str) -> float:
    """
    Linear interpolation between threshold (0 points) and ideal (full points).
    Returns 0.0 to 1.0.
    """
    if ideal == threshold:
        return 1.0 if _passes_threshold(actual, threshold, operator) else 0.0

    # Determine direction
    if operator in ("<=", "<"):
        # Lower is better: threshold is max acceptable, ideal is below it
        if actual > threshold:
            return 0.0
        if actual <= ideal:
            return 1.0
        return (threshold - actual) / (threshold - ideal)
    elif operator in (">=", ">"):
        # Higher is better: threshold is min acceptable, ideal is above it
        if actual < threshold:
            return 0.0
        if actual >= ideal:
            return 1.0
        return (actual - threshold) / (ideal - threshold)
    else:
        # == or between — binary
        return 1.0 if _passes_threshold(actual, threshold, operator) else 0.0


def score_step(actual: float, threshold: float, ideal: float, operator: str) -> float:
    """Binary scoring: 1.0 if threshold is met, 0.0 if not."""
    return 1.0 if _passes_threshold(actual, threshold, operator) else 0.0


def score_exponential(actual: float, threshold: float, ideal: float, operator: str) -> float:
    """
    Exponential curve — rewards getting closer to ideal more aggressively.
    Score accelerates as actual value approaches ideal.
    """
    linear = score_linear(actual, threshold, ideal, operator)
    return linear ** 0.5  # Square root makes it accelerate toward ideal


def score_bell(actual: float, threshold: float, ideal: float, operator: str) -> float:
    """
    Bell curve centered on ideal. Score drops off in both directions.
    Good for criteria where both too high AND too low are bad.
    """
    if ideal is None:
        return score_linear(actual, threshold, ideal, operator)

    # Width of the bell based on threshold-to-ideal distance
    width = abs(threshold - ideal) if threshold != ideal else 10.0
    distance = abs(actual - ideal)
    score = math.exp(-(distance ** 2) / (2 * (width / 2) ** 2))
    return max(0.0, min(1.0, score))


SCORING_CURVES = {
    "linear": score_linear,
    "step": score_step,
    "exponential": score_exponential,
    "bell": score_bell,
}


# ── Threshold Checking ─────────────────────────────────────────────────────────

def _passes_threshold(actual: float, threshold: float, operator: str,
                      threshold_upper: float = None) -> bool:
    """Check if an actual value passes a threshold given an operator."""
    if operator == "<=":
        return actual <= threshold
    elif operator == ">=":
        return actual >= threshold
    elif operator == "==":
        return abs(actual - threshold) < 0.01
    elif operator == "between":
        return threshold <= actual <= (threshold_upper or threshold)
    return False


# ── Core Engine ─────────────────────────────────────────────────────────────────

def evaluate_criterion(criterion, weather_data: dict) -> CriterionResult:
    """
    Evaluate a single criterion against a weather data dict.

    weather_data should be a flat dict mapping field names to values, e.g.:
    {
        "temperature_f": 25.0,
        "cloud_cover_pct": 10.0,
        "overnight_snowfall_in": 12.0,
        ...
    }
    """
    actual = weather_data.get(criterion.field)

    if actual is None:
        return CriterionResult(
            label=criterion.label,
            field=criterion.field,
            operator=criterion.operator,
            threshold=criterion.threshold,
            actual_value=None,
            passed=False,
            raw_score=0.0,
            weighted_score=0.0,
            weight=criterion.weight,
            required=criterion.required,
            ideal=criterion.ideal,
            scoring_curve=criterion.scoring_curve,
        )

    passed = _passes_threshold(
        actual, criterion.threshold, criterion.operator,
        getattr(criterion, 'threshold_upper', None)
    )

    # Calculate score using the appropriate curve
    ideal = criterion.ideal if criterion.ideal is not None else criterion.threshold
    curve_fn = SCORING_CURVES.get(criterion.scoring_curve, score_linear)
    raw_score = curve_fn(actual, criterion.threshold, ideal, criterion.operator)

    # If threshold isn't met, raw_score is 0 regardless of curve
    if not passed:
        raw_score = 0.0

    return CriterionResult(
        label=criterion.label,
        field=criterion.field,
        operator=criterion.operator,
        threshold=criterion.threshold,
        actual_value=actual,
        passed=passed,
        raw_score=raw_score,
        weighted_score=raw_score * criterion.weight,
        weight=criterion.weight,
        required=criterion.required,
        ideal=criterion.ideal,
        scoring_curve=criterion.scoring_curve,
    )


def score_location(profile, location, weather_by_day: dict) -> list:
    """
    Score a location across multiple forecast days.

    weather_by_day: dict mapping date strings to weather data dicts.
    e.g. { "2026-01-15": { "temperature_f": 25, ... }, ... }

    Returns a list of LocationResult, one per day.
    """
    results = []

    for date_str, weather_data in weather_by_day.items():
        criterion_results = [
            evaluate_criterion(crit, weather_data)
            for crit in profile.criteria
        ]

        any_required_failed = any(
            not cr.passed and cr.required
            for cr in criterion_results
        )

        # Calculate total score based on method
        if any_required_failed:
            total_score = 0.0
        elif profile.scoring.method == "weighted_sum":
            total_weight = sum(cr.weight for cr in criterion_results)
            if total_weight > 0:
                total_score = sum(cr.weighted_score for cr in criterion_results) / total_weight * 100
            else:
                total_score = 0.0
        elif profile.scoring.method == "min_score":
            scores = [cr.raw_score for cr in criterion_results if cr.actual_value is not None]
            total_score = min(scores) * 100 if scores else 0.0
        elif profile.scoring.method == "multiplicative":
            product = 1.0
            for cr in criterion_results:
                if cr.actual_value is not None:
                    product *= cr.raw_score
            total_score = product * 100
        else:
            total_score = 0.0

        total_score = round(total_score, 1)

        results.append(LocationResult(
            location_name=location.name,
            lat=location.lat,
            lon=location.lon,
            forecast_date=date_str,
            criteria_results=criterion_results,
            total_score=total_score,
            pass_threshold_met=total_score >= profile.scoring.pass_threshold,
            highlight_threshold_met=total_score >= profile.scoring.highlight_threshold,
            any_required_failed=any_required_failed,
            scoring_method=profile.scoring.method,
        ))

    return results


def run_scout(profile, weather_data_by_location: dict) -> ScoutReport:
    """
    Run a full scout evaluation.

    weather_data_by_location: dict mapping location names to their
    weather_by_day dicts.

    e.g. {
        "Crystal Mountain": {
            "2026-01-15": { "temperature_f": 22, "cloud_cover_pct": 5, ... },
            "2026-01-16": { ... },
        },
        "Stevens Pass": { ... },
    }
    """
    all_results = []

    for location in profile.locations:
        weather_by_day = weather_data_by_location.get(location.name, {})
        if not weather_by_day:
            continue
        location_results = score_location(profile, location, weather_by_day)
        all_results.extend(location_results)

    return ScoutReport(
        profile_name=profile.name,
        profile_description=profile.description,
        run_timestamp=datetime.now().isoformat(),
        location_results=all_results,
    )


# ── Report Formatting ──────────────────────────────────────────────────────────

def format_report_markdown(report: ScoutReport) -> str:
    """Format a ScoutReport as readable markdown."""
    lines = []
    lines.append(f"# Weather Scout Report: {report.profile_name}")
    lines.append(f"*{report.profile_description.strip()}*")
    lines.append(f"")
    lines.append(f"Run: {report.run_timestamp}")
    lines.append("")

    if not report.location_results:
        lines.append("No results — weather data may be unavailable.")
        return "\n".join(lines)

    # Summary
    if report.best_result:
        best = report.best_result
        lines.append(f"## Best Match")
        lines.append(
            f"**{best.location_name}** on {best.forecast_date} — "
            f"Score: **{best.total_score}/100** ({best.grade})"
        )
        lines.append("")

    # Group by location
    by_location = {}
    for r in report.location_results:
        by_location.setdefault(r.location_name, []).append(r)

    for loc_name, results in by_location.items():
        lines.append(f"## {loc_name}")
        for r in sorted(results, key=lambda x: x.forecast_date):
            grade_icon = {"EXCEPTIONAL": "⭐", "GOOD": "✅", "MARGINAL": "⚠️", "FAIL": "❌"}
            icon = grade_icon.get(r.grade, "")
            lines.append(f"### {r.forecast_date} — {r.total_score}/100 {icon} {r.grade}")
            for cr in r.criteria_results:
                val = f"{cr.actual_value:.1f}" if cr.actual_value is not None else "N/A"
                lines.append(
                    f"  {cr.status_icon} {cr.label}: {val} "
                    f"(need {cr.operator} {cr.threshold}) — "
                    f"score {cr.raw_score:.0%} × weight {cr.weight}"
                )
            lines.append("")

    return "\n".join(lines)


def format_report_json(report: ScoutReport) -> dict:
    """Format a ScoutReport as a JSON-serializable dict."""
    return {
        "profile_name": report.profile_name,
        "run_timestamp": report.run_timestamp,
        "best_match": {
            "location": report.best_result.location_name,
            "date": report.best_result.forecast_date,
            "score": report.best_result.total_score,
            "grade": report.best_result.grade,
        } if report.best_result else None,
        "results": [
            {
                "location": r.location_name,
                "date": r.forecast_date,
                "score": r.total_score,
                "grade": r.grade,
                "criteria": [
                    {
                        "label": cr.label,
                        "field": cr.field,
                        "actual": cr.actual_value,
                        "threshold": cr.threshold,
                        "operator": cr.operator,
                        "passed": cr.passed,
                        "score_pct": round(cr.raw_score * 100, 1),
                        "weight": cr.weight,
                        "required": cr.required,
                    }
                    for cr in r.criteria_results
                ],
            }
            for r in report.location_results
        ],
    }
