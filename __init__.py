"""
notifiers/__init__.py — Notifier interface and registry for Adventure Scout.

Each notifier implements send_alert() to deliver scored results via a
specific channel. Adding a new notifier:

1. Create a new file in this directory (e.g., slack_notifier.py)
2. Implement a class with send_alert(report, config) -> bool
3. Register it in NOTIFIER_REGISTRY below

The orchestrator (run_scout.py) calls get_notifier(name) to look up
the right notifier. This keeps the notifier layer fully decoupled from
the engine and providers.
"""

from abc import ABC, abstractmethod


class BaseNotifier(ABC):
    """
    Interface that all notifiers must implement.

    send_alert() receives a ScoutReport and a config dict.
    Returns True if the notification was sent successfully.
    """

    @abstractmethod
    def send_alert(self, report, config: dict) -> bool:
        """
        Send an alert for a scored report.

        Args:
            report: A ScoutReport from engine.py
            config: Dict with notifier-specific settings (API keys, phone numbers, etc.)

        Returns:
            True if sent successfully, False otherwise.
        """
        pass

    @abstractmethod
    def notifier_name(self) -> str:
        """Human-readable name for logging."""
        pass

    @abstractmethod
    def required_config_keys(self) -> list:
        """List of config keys this notifier needs (for validation)."""
        pass


# ── Registry ────────────────────────────────────────────────────────────────────
# Import notifiers here. Lazy imports so missing dependencies don't crash
# the whole system — you only need twilio installed if you use WhatsApp.

def get_notifier(name: str) -> BaseNotifier:
    """Look up a notifier by name. Raises ValueError if not found."""
    if name == "console":
        from .console_notifier import ConsoleNotifier
        return ConsoleNotifier()
    elif name == "whatsapp":
        from .whatsapp_notifier import WhatsAppNotifier
        return WhatsAppNotifier()
    else:
        available = ["console", "whatsapp"]
        raise ValueError(
            f"Unknown notifier '{name}'. Available: {', '.join(available)}"
        )


def list_notifiers() -> list:
    """Return names of all registered notifiers."""
    return ["console", "whatsapp"]
