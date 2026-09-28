"""Protección de gasto para el despliegue público.

Cada consulta paga tokens reales. Dos frenos en memoria (suficientes para una
sola instancia; con varias réplicas harían falta en Redis/Postgres):
- límite de consultas por IP por hora,
- presupuesto diario global en USD: al superarlo, /ask responde 429 hasta el día siguiente.
"""

from __future__ import annotations

import threading
import time
from collections import defaultdict, deque
from datetime import date

from app.config import get_settings

_lock = threading.Lock()
_hits: dict[str, deque] = defaultdict(deque)
_spent = {"day": date.today(), "usd": 0.0}


def check(ip: str) -> str | None:
    """None si puede consultar; si no, el motivo."""
    settings = get_settings()
    now = time.time()
    with _lock:
        if _spent["day"] != date.today():
            _spent.update(day=date.today(), usd=0.0)
        if _spent["usd"] >= settings.daily_budget_usd:
            return "Se alcanzó el presupuesto diario de la demo. Vuelve mañana o levanta el proyecto localmente."
        window = _hits[ip]
        while window and now - window[0] > 3600:
            window.popleft()
        if len(window) >= settings.requests_per_ip_per_hour:
            return "Demasiadas consultas desde tu conexión en la última hora. Intenta más tarde."
        window.append(now)
    return None


def record_spend(usd: float) -> None:
    with _lock:
        _spent["usd"] += usd


def spent_today() -> float:
    return round(_spent["usd"], 4)
