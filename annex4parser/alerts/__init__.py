# alerts package
"""Event-driven алерты для мониторинга регуляторных изменений."""

from .webhook import (
    AlertEmitter,
    get_alert_emitter,
    emit_rule_changed,
    emit_rss_update,
    emit_regulation_update
)

__all__ = [
    "AlertEmitter",
    "get_alert_emitter", 
    "emit_rule_changed",
    "emit_rss_update",
    "emit_regulation_update"
]


