# Search Profile Schema Reference

Complete specification for Weather Scout search profile YAML files.

## File Format

Profiles are YAML files stored in the `search-profiles/` directory. Each file
defines one search profile. Filenames should be kebab-case and descriptive
(e.g., `bluebird-powder-day.yaml`, `summer-stargazing.yaml`).

## Comments and Documentation

YAML supports inline comments with `#`. Use them generously — profiles are
designed to be read and refined by humans. Add `rationale:` fields to criteria
to explain the "why" behind thresholds.

## Top-Level Fields

### name (required, string)
Human-readable title for this search. Shows up in reports and listings.

### description (required, string)
Paragraph explaining what this profile looks for and why. Use YAML block scalar
`>` for multi-line descriptions.

### time_window (required, object)

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| start_hour | int (0-23) | yes | Beginning of evaluation window |
| end_hour | int (0-23) | yes | End of evaluation window |
| days_ahead | int (≥1) | yes | Number of forecast days to check |

The time window defines when during the day conditions are evaluated. For a
ski morning, you might use 6-11. For stargazing, 21-2 (wraps past midnight).

### locations (required, list)

Each location entry:

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| name | string | yes | Display name |
| lat | float | yes | Latitude (decimal degrees) |
| lon | float | yes | Longitude (decimal degrees) |
| elevation_ft | float | no | Elevation in feet (for context/display) |
| notes | string | no | Human notes about this location |

### criteria (required, list)

Each criterion entry:

| Field | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| field | string | yes | — | Weather variable (see Supported Fields) |
| label | string | yes | — | Human-readable name |
| operator | string | yes | — | `<=`, `>=`, `==`, `between` |
| threshold | number | yes | — | Pass/fail boundary value |
| threshold_upper | number | conditional | — | Upper bound (required for `between`) |
| required | bool | yes | — | If true, failing zeros the total score |
| weight | number | yes | — | Points this criterion contributes |
| ideal | number | no | threshold | The "perfect" value for max score |
| scoring_curve | string | no | linear | How score scales between threshold and ideal |
| rationale | string | no | — | Why this criterion exists / how to tune it |

**Operators:**
- `<=` — actual value must be less than or equal to threshold
- `>=` — actual value must be greater than or equal to threshold
- `==` — actual value must equal threshold (within 0.01)
- `between` — actual value must be between threshold and threshold_upper

**Scoring curves:**
- `linear` — proportional between threshold (0 points) and ideal (full points)
- `step` — binary: full points if threshold met, zero if not
- `exponential` — score accelerates as value approaches ideal (square root curve)
- `bell` — Gaussian peak at ideal, drops off in both directions

### scoring (optional, object)

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| method | string | weighted_sum | How criteria scores combine |
| pass_threshold | number | 60 | Minimum total score to flag as "good" |
| highlight_threshold | number | 85 | Score that flags as "exceptional" |

**Scoring methods:**
- `weighted_sum` — sum of (raw_score × weight) / total_weight × 100
- `min_score` — total = lowest individual criterion score × 100
- `multiplicative` — product of all raw scores × 100

## Supported Weather Fields

| Field | Unit | Source | Description |
|-------|------|--------|-------------|
| temperature_f | °F | window avg | Air temperature |
| feels_like_f | °F | window avg | Apparent temperature (wind chill/heat index) |
| cloud_cover_pct | % (0-100) | window avg | Sky coverage |
| wind_speed_mph | mph | window avg | Sustained wind speed |
| wind_gust_mph | mph | window max | Peak gust speed |
| precipitation_in | inches | window sum | Total precipitation |
| overnight_snowfall_in | inches | overnight sum | Snowfall from 6PM-6AM |
| overnight_low_f | °F | overnight min | Minimum overnight temperature |
| humidity_pct | % | window avg | Relative humidity |
| visibility_mi | miles | window avg | Visibility distance |
| uv_index | 0-11+ | window max | UV intensity index |
| pressure_mb | mbar | window avg | Barometric pressure |
| dewpoint_f | °F | window avg | Dew point temperature |
| precipitation_probability_pct | % | window max | Chance of precipitation |

"Window" values are aggregated over the time_window hours.
"Overnight" values cover 6PM previous day through 6AM target day.

## Example: Complete Profile

```yaml
name: "Summer Stargazing"
description: >
  Clear, dark, calm nights ideal for telescope work or naked-eye
  astronomy. Checks for cloud cover, humidity (affects seeing),
  and wind (shakes the scope).

time_window:
  start_hour: 21
  end_hour: 2
  days_ahead: 5

locations:
  - name: "Goldendale Observatory"
    lat: 45.8203
    lon: -120.8217
    elevation_ft: 2100
    notes: "Dark sky site, public observatory"

criteria:
  - field: cloud_cover_pct
    label: "Clear sky"
    operator: "<="
    threshold: 10
    required: true
    weight: 40
    ideal: 0
    scoring_curve: linear

  - field: humidity_pct
    label: "Low humidity (good seeing)"
    operator: "<="
    threshold: 60
    required: false
    weight: 25
    ideal: 30
    scoring_curve: linear

  - field: wind_speed_mph
    label: "Calm air"
    operator: "<="
    threshold: 10
    required: false
    weight: 20
    ideal: 0
    scoring_curve: linear

  - field: temperature_f
    label: "Comfortable temp"
    operator: "between"
    threshold: 45
    threshold_upper: 75
    required: false
    weight: 15
    ideal: 60
    scoring_curve: bell

scoring:
  method: weighted_sum
  pass_threshold: 65
  highlight_threshold: 90
```

## Tips for Profile Authors

1. **Start with required criteria** — what conditions absolutely must be met?
   These are your gates. If any fails, the score is zero.

2. **Weight by importance** — the thing you care most about should have the
   highest weight. For powder skiing, snowfall matters more than wind.

3. **Set realistic thresholds** — too strict and you'll never get matches.
   Start loose, then tighten as you see what real data looks like.

4. **Use ideal values** — they reward better-than-minimum conditions. Without
   an ideal, meeting the threshold gets full points regardless of how much
   the actual value exceeds it.

5. **Add rationale** — future-you (or your friend using the profile) will
   thank you for explaining why 26°F is the overnight threshold.

6. **Sum weights to ~100** — it's not required, but it makes weights feel
   like percentages, which is more intuitive.
