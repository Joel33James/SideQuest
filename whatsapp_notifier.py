"""
whatsapp_notifier.py — Send Adventure Scout alerts via WhatsApp.

Uses the Twilio API to send WhatsApp messages. You'll need:

1. A Twilio account (free trial works for testing)
2. A Twilio WhatsApp-enabled number (or the sandbox for testing)
3. Environment variables or a config dict with:
   - TWILIO_ACCOUNT_SID
   - TWILIO_AUTH_TOKEN
   - TWILIO_WHATSAPP_FROM  (e.g., "whatsapp:+14155238886")
   - WHATSAPP_TO           (e.g., "whatsapp:+12065551234")

Setup guide:
  1. Sign up at https://www.twilio.com
  2. Go to Console → Messaging → Try it Out → WhatsApp
  3. Follow the sandbox setup (send "join <word>" from your phone)
  4. For production, request a Twilio WhatsApp Business number
  5. Set the env vars above, or pass them in the config dict

The notifier only sends messages when results meet the pass threshold.
Exceptional results get extra emphasis in the message.
"""

import os
import json
import urllib.request
import urllib.parse
import base64
from . import BaseNotifier


class WhatsAppNotifier(BaseNotifier):

    def notifier_name(self) -> str:
        return "WhatsApp (Twilio)"

    def required_config_keys(self) -> list:
        return [
            "TWILIO_ACCOUNT_SID",
            "TWILIO_AUTH_TOKEN",
            "TWILIO_WHATSAPP_FROM",
            "WHATSAPP_TO",
        ]

    def send_alert(self, report, config: dict) -> bool:
        """
        Send a WhatsApp message summarizing actionable results.

        Only sends if at least one location meets the pass threshold.
        Config values can come from the config dict or environment variables.
        """
        # Resolve config — dict values take priority over env vars
        sid = config.get("TWILIO_ACCOUNT_SID") or os.environ.get("TWILIO_ACCOUNT_SID")
        token = config.get("TWILIO_AUTH_TOKEN") or os.environ.get("TWILIO_AUTH_TOKEN")
        from_number = config.get("TWILIO_WHATSAPP_FROM") or os.environ.get("TWILIO_WHATSAPP_FROM")
        to_number = config.get("WHATSAPP_TO") or os.environ.get("WHATSAPP_TO")

        # Validate
        missing = []
        if not sid: missing.append("TWILIO_ACCOUNT_SID")
        if not token: missing.append("TWILIO_AUTH_TOKEN")
        if not from_number: missing.append("TWILIO_WHATSAPP_FROM")
        if not to_number: missing.append("WHATSAPP_TO")

        if missing:
            print(
                f"⚠ WhatsApp notifier: Missing config: {', '.join(missing)}. "
                f"Set as environment variables or pass in config dict.",
            )
            return False

        # Filter to actionable results
        actionable = [
            r for r in report.location_results
            if r.pass_threshold_met or r.highlight_threshold_met
        ]

        if not actionable:
            # Don't spam — only send when there's something worth reporting
            return True

        # Build the message
        message = self._format_message(report, actionable)

        # Send via Twilio
        return self._send_twilio(sid, token, from_number, to_number, message)

    def _format_message(self, report, actionable_results) -> str:
        """Build a WhatsApp-friendly message (plain text, emoji OK)."""
        lines = []

        # Check if any are exceptional
        has_exceptional = any(r.highlight_threshold_met for r in actionable_results)

        if has_exceptional:
            lines.append(f"🏔⭐ ADVENTURE SCOUT: {report.profile_name}")
            lines.append("EXCEPTIONAL conditions detected!")
        else:
            lines.append(f"🏔 ADVENTURE SCOUT: {report.profile_name}")
            lines.append("Good conditions detected:")

        lines.append("")

        for r in sorted(actionable_results, key=lambda x: -x.total_score):
            icon = "⭐" if r.highlight_threshold_met else "✅"
            lines.append(f"{icon} {r.location_name}")
            lines.append(f"   {r.forecast_date} — {r.total_score}/100")

            # Include key details for the top criteria
            for cr in r.criteria_results:
                if cr.actual_value is not None:
                    val = f"{cr.actual_value:.0f}" if cr.actual_value == int(cr.actual_value) else f"{cr.actual_value:.1f}"
                    lines.append(f"   {cr.status_icon} {cr.label}: {val}")

            lines.append("")

        if report.best_result:
            lines.append(
                f"→ Best: {report.best_result.location_name} on "
                f"{report.best_result.forecast_date}"
            )

        return "\n".join(lines)

    def _send_twilio(self, sid: str, token: str, from_number: str,
                     to_number: str, message: str) -> bool:
        """Send a message via the Twilio REST API."""
        url = f"https://api.twilio.com/2010-04-01/Accounts/{sid}/Messages.json"

        data = urllib.parse.urlencode({
            "From": from_number,
            "To": to_number,
            "Body": message,
        }).encode("utf-8")

        # Basic auth
        credentials = base64.b64encode(f"{sid}:{token}".encode()).decode()

        req = urllib.request.Request(url, data=data, method="POST")
        req.add_header("Authorization", f"Basic {credentials}")
        req.add_header("Content-Type", "application/x-www-form-urlencoded")

        try:
            with urllib.request.urlopen(req, timeout=15) as response:
                result = json.loads(response.read().decode())
                status = result.get("status", "unknown")
                if status in ("queued", "sent", "delivered"):
                    print(f"✓ WhatsApp message sent (status: {status})")
                    return True
                else:
                    print(f"⚠ WhatsApp message status: {status}")
                    return True  # Twilio accepted it, delivery is async
        except urllib.error.HTTPError as e:
            body = e.read().decode() if e.fp else ""
            print(f"✗ WhatsApp send failed (HTTP {e.code}): {body}")
            return False
        except Exception as e:
            print(f"✗ WhatsApp send failed: {e}")
            return False
