"""
profile_loader.py — Parse and validate weather scout search profiles.

Loads YAML profile files into structured Python objects with validation.
Designed to give clear error messages when a profile has issues, so humans
can fix their YAML without guessing what went wrong.
"""

import yaml
import os
import sys
from dataclasses import dataclass, field
from typing import Optional
from pathlib import Path


# ── Data Classes ────────────────────────────────────────────────────────────────

@dataclass
class Location:
    name: str
    lat: float
    lon: float
    elevation_ft: Optional[float] = None
    notes: Optional[str] = None


@dataclass
class Criterion:
    field: str
    label: str
    operator: str  # "<=", ">=", "==", "between"
    threshold: float
    required: bool
    weight: float
    ideal: Optional[float] = None
    threshold_upper: Optional[float] = None  # for "between" operator
    scoring_curve: str = "linear"  # linear, step, exponential, bell
    rationale: Optional[str] = None

    def __post_init__(self):
        valid_operators = {"<=", ">=", "==", "between"}
        if self.operator not in valid_operators:
            raise ValueError(
                f"Criterion '{self.label}': operator must be one of {valid_operators}, "
                f"got '{self.operator}'"
            )
        if self.operator == "between" and self.threshold_upper is None:
            raise ValueError(
                f"Criterion '{self.label}': 'between' operator requires 'threshold_upper'"
            )
        valid_curves = {"linear", "step", "exponential", "bell"}
        if self.scoring_curve not in valid_curves:
            raise ValueError(
                f"Criterion '{self.label}': scoring_curve must be one of {valid_curves}, "
                f"got '{self.scoring_curve}'"
            )


@dataclass
class TimeWindow:
    start_hour: int  # 0-23
    end_hour: int     # 0-23
    days_ahead: int   # how many days of forecast to evaluate

    def __post_init__(self):
        if not (0 <= self.start_hour <= 23):
            raise ValueError(f"start_hour must be 0-23, got {self.start_hour}")
        if not (0 <= self.end_hour <= 23):
            raise ValueError(f"end_hour must be 0-23, got {self.end_hour}")
        if self.days_ahead < 1:
            raise ValueError(f"days_ahead must be >= 1, got {self.days_ahead}")


@dataclass
class ScoringConfig:
    method: str = "weighted_sum"  # weighted_sum, min_score, multiplicative
    pass_threshold: float = 60.0
    highlight_threshold: float = 85.0

    def __post_init__(self):
        valid_methods = {"weighted_sum", "min_score", "multiplicative"}
        if self.method not in valid_methods:
            raise ValueError(
                f"scoring.method must be one of {valid_methods}, got '{self.method}'"
            )


@dataclass
class SearchProfile:
    name: str
    description: str
    time_window: TimeWindow
    locations: list  # List[Location]
    criteria: list   # List[Criterion]
    scoring: ScoringConfig
    source_file: Optional[str] = None

    def summary(self) -> str:
        """One-line summary for listing profiles."""
        loc_names = ", ".join(loc.name for loc in self.locations)
        return f"{self.name} — {len(self.criteria)} criteria across {len(self.locations)} locations ({loc_names})"


# ── Loader ──────────────────────────────────────────────────────────────────────

def load_profile(filepath: str) -> SearchProfile:
    """Load and validate a single search profile from a YAML file."""
    path = Path(filepath)
    if not path.exists():
        raise FileNotFoundError(f"Profile not found: {filepath}")
    if not path.suffix in (".yaml", ".yml"):
        raise ValueError(f"Profile must be a .yaml or .yml file: {filepath}")

    with open(path, "r") as f:
        raw = yaml.safe_load(f)

    if not isinstance(raw, dict):
        raise ValueError(f"Profile {filepath} must be a YAML mapping (dictionary)")

    # Required top-level keys
    for key in ("name", "description", "time_window", "locations", "criteria"):
        if key not in raw:
            raise ValueError(f"Profile {filepath} missing required key: '{key}'")

    # Parse time window
    tw_raw = raw["time_window"]
    time_window = TimeWindow(
        start_hour=tw_raw["start_hour"],
        end_hour=tw_raw["end_hour"],
        days_ahead=tw_raw.get("days_ahead", 3),
    )

    # Parse locations
    locations = []
    for i, loc_raw in enumerate(raw["locations"]):
        if "name" not in loc_raw or "lat" not in loc_raw or "lon" not in loc_raw:
            raise ValueError(
                f"Profile {filepath}, location #{i+1}: must have 'name', 'lat', 'lon'"
            )
        locations.append(Location(
            name=loc_raw["name"],
            lat=float(loc_raw["lat"]),
            lon=float(loc_raw["lon"]),
            elevation_ft=loc_raw.get("elevation_ft"),
            notes=loc_raw.get("notes"),
        ))

    # Parse criteria
    criteria = []
    for i, crit_raw in enumerate(raw["criteria"]):
        required_keys = ("field", "label", "operator", "threshold", "required", "weight")
        for key in required_keys:
            if key not in crit_raw:
                raise ValueError(
                    f"Profile {filepath}, criterion #{i+1}: missing required key '{key}'"
                )
        criteria.append(Criterion(
            field=crit_raw["field"],
            label=crit_raw["label"],
            operator=crit_raw["operator"],
            threshold=float(crit_raw["threshold"]),
            required=bool(crit_raw["required"]),
            weight=float(crit_raw["weight"]),
            ideal=float(crit_raw["ideal"]) if "ideal" in crit_raw else None,
            threshold_upper=float(crit_raw["threshold_upper"]) if "threshold_upper" in crit_raw else None,
            scoring_curve=crit_raw.get("scoring_curve", "linear"),
            rationale=crit_raw.get("rationale"),
        ))

    # Parse scoring config
    scoring_raw = raw.get("scoring", {})
    scoring = ScoringConfig(
        method=scoring_raw.get("method", "weighted_sum"),
        pass_threshold=float(scoring_raw.get("pass_threshold", 60)),
        highlight_threshold=float(scoring_raw.get("highlight_threshold", 85)),
    )

    # Weight validation — warn if weights don't sum close to 100
    total_weight = sum(c.weight for c in criteria)
    if abs(total_weight - 100) > 5:
        print(
            f"⚠ Warning: Criteria weights in '{raw['name']}' sum to {total_weight} "
            f"(expected ~100). Scores will still normalize, but weights may not "
            f"behave as intended.",
            file=sys.stderr,
        )

    return SearchProfile(
        name=raw["name"],
        description=raw["description"],
        time_window=time_window,
        locations=locations,
        criteria=criteria,
        scoring=scoring,
        source_file=str(path),
    )


def load_all_profiles(directory: str) -> list:
    """Load all .yaml profiles from a directory."""
    profiles = []
    dir_path = Path(directory)
    if not dir_path.is_dir():
        raise FileNotFoundError(f"Profile directory not found: {directory}")

    for yaml_file in sorted(dir_path.glob("*.yaml")) + sorted(dir_path.glob("*.yml")):
        try:
            profile = load_profile(str(yaml_file))
            profiles.append(profile)
        except (ValueError, KeyError) as e:
            print(f"⚠ Skipping {yaml_file.name}: {e}", file=sys.stderr)

    return profiles


# ── CLI usage ───────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python profile_loader.py <profile.yaml | profiles-dir/>")
        sys.exit(1)

    target = sys.argv[1]
    if os.path.isdir(target):
        profiles = load_all_profiles(target)
        print(f"Loaded {len(profiles)} profiles:")
        for p in profiles:
            print(f"  • {p.summary()}")
    else:
        profile = load_profile(target)
        print(f"✓ Loaded: {profile.summary()}")
        print(f"  Description: {profile.description.strip()}")
        print(f"  Time window: {profile.time_window.start_hour}:00 – {profile.time_window.end_hour}:00, {profile.time_window.days_ahead} days ahead")
        print(f"  Scoring: {profile.scoring.method}, pass={profile.scoring.pass_threshold}, highlight={profile.scoring.highlight_threshold}")
        print(f"  Criteria:")
        for c in profile.criteria:
            req = "REQUIRED" if c.required else "optional"
            print(f"    [{req}] {c.label}: {c.field} {c.operator} {c.threshold} (weight={c.weight}, ideal={c.ideal})")
