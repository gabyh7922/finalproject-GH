"""Cliente de Claude compartido por CAG, RAG y agente.

- Salida estructurada con `messages.parse` + Pydantic: la respuesta llega ya validada.
- `fallbacks="default"`: si el clasificador de seguridad rechazara una consulta
  (poco probable en consultas laborales, pero posible con temas como acoso o
  violencia), la API reintenta con otro modelo en la misma llamada.
- Registra el uso de tokens (incluida la caché) de cada llamada para medir costo.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from functools import lru_cache

import anthropic
from pydantic import BaseModel, ValidationError

from app.config import get_settings
from app.observability import log_event

FALLBACK_BETA = "server-side-fallback-2026-07-01"

# USD por millón de tokens (claude-opus-5). Constantes explícitas: cambian con el tiempo.
PRICE_INPUT = 5.00
PRICE_OUTPUT = 25.00
PRICE_CACHE_WRITE = 6.25
PRICE_CACHE_READ = 0.50


class RefusalError(RuntimeError):
    pass


@dataclass
class Usage:
    input_tokens: int = 0
    output_tokens: int = 0
    cache_creation_input_tokens: int = 0
    cache_read_input_tokens: int = 0
    latency_ms: float = 0.0

    @property
    def cost_usd(self) -> float:
        return (
            self.input_tokens * PRICE_INPUT
            + self.output_tokens * PRICE_OUTPUT
            + self.cache_creation_input_tokens * PRICE_CACHE_WRITE
            + self.cache_read_input_tokens * PRICE_CACHE_READ
        ) / 1_000_000

    def add(self, other: "Usage") -> None:
        self.input_tokens += other.input_tokens
        self.output_tokens += other.output_tokens
        self.cache_creation_input_tokens += other.cache_creation_input_tokens
        self.cache_read_input_tokens += other.cache_read_input_tokens
        self.latency_ms += other.latency_ms


@lru_cache
def get_client() -> anthropic.Anthropic:
    settings = get_settings()
    if not settings.anthropic_api_key:
        raise RuntimeError("Falta ANTHROPIC_API_KEY en el entorno (.env).")
    return anthropic.Anthropic(api_key=settings.anthropic_api_key)


def usage_from(response, latency_ms: float) -> Usage:
    u = response.usage
    return Usage(
        input_tokens=u.input_tokens or 0,
        output_tokens=u.output_tokens or 0,
        cache_creation_input_tokens=getattr(u, "cache_creation_input_tokens", 0) or 0,
        cache_read_input_tokens=getattr(u, "cache_read_input_tokens", 0) or 0,
        latency_ms=latency_ms,
    )


def parse_structured(
    *,
    system: str | list[dict],
    user: str,
    output_format: type[BaseModel],
    request_id: str,
    stage: str,
    max_tokens: int = 16000,
):
    """Llama a Claude y devuelve (objeto validado, Usage). Un reintento si el JSON no valida."""
    settings = get_settings()
    client = get_client()
    last_error: Exception | None = None
    for attempt in range(2):
        started = time.perf_counter()
        response = client.beta.messages.parse(
            model=settings.llm_model,
            max_tokens=max_tokens,
            betas=[FALLBACK_BETA],
            fallbacks="default",
            thinking={"type": "adaptive"},
            output_config={"effort": settings.llm_effort},
            system=system,
            messages=[{"role": "user", "content": user}],
            output_format=output_format,
        )
        usage = usage_from(response, (time.perf_counter() - started) * 1000)
        log_event(
            "llm_call",
            request_id=request_id,
            stage=stage,
            model=response.model,
            stop_reason=response.stop_reason,
            attempt=attempt,
            **{k: v for k, v in usage.__dict__.items()},
            cost_usd=round(usage.cost_usd, 5),
        )
        if response.stop_reason == "refusal":
            raise RefusalError("El modelo rechazó la consulta.")
        try:
            parsed = response.parsed_output
            if parsed is None:
                raise ValueError(f"sin salida estructurada (stop_reason={response.stop_reason})")
            return parsed, usage
        except (ValidationError, ValueError) as exc:
            last_error = exc
            log_event("llm_parse_retry", request_id=request_id, stage=stage, error=str(exc)[:300])
    raise RuntimeError(f"Salida inválida tras reintento: {last_error}")
