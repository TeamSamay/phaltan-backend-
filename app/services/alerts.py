from datetime import datetime, timezone
from typing import Any


def make_alert(category: str, title: str, description: str, severity: str = "info",
               experiment_id: str | None = None, event_id: str | None = None) -> dict[str, Any]:
    return {
        "alert_id": f"{event_id or 'system'}:{category}", "category": category,
        "severity": severity, "title": title, "description": description,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "experiment_id": experiment_id, "event_id": event_id, "acknowledged": False,
    }
