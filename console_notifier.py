"""
console_notifier.py — Print alerts to the terminal.

The default notifier. Useful for testing, cron job logs, and piping
output to other tools. No dependencies, always works.
"""

import sys
from . import BaseNotifier


class ConsoleNotifier(BaseNotifier):

    def notifier_name(self) -> str:
        return "Console"

    def required_config_keys(self) -> list:
        return []  # No config needed

    def send_alert(self, report, config: dict) -> bool:
        """Print a summary of actionable results to stderr."""
        actionable = [
            r for r in report.location_results
            if r.pass_threshold_met or r.highlight_threshold_met
        ]

        if not actionable:
            print(
                f"[Adventure Scout] {report.profile_name}: No locations met the threshold.",
                file=sys.stderr,
            )
            return True

        print(f"\n{'='*60}", file=sys.stderr)
        print(f"🏔  ADVENTURE SCOUT ALERT: {report.profile_name}", file=sys.stderr)
        print(f"{'='*60}", file=sys.stderr)

        for r in sorted(actionable, key=lambda x: -x.total_score):
            icon = "⭐" if r.highlight_threshold_met else "✅"
            print(
                f"  {icon} {r.location_name} on {r.forecast_date}: "
                f"{r.total_score}/100 ({r.grade})",
                file=sys.stderr,
            )
            for cr in r.criteria_results:
                val = f"{cr.actual_value:.1f}" if cr.actual_value is not None else "N/A"
                print(
                    f"     {cr.status_icon} {cr.label}: {val}",
                    file=sys.stderr,
                )

        print(f"{'='*60}\n", file=sys.stderr)
        return True
