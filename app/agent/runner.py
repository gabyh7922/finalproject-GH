"""Fase 5 — Agente con herramientas (bucle manual sobre la Messages API).

Por qué un agente y no solo RAG: el RAG hace UNA búsqueda con las palabras del
usuario. Muchas consultas laborales necesitan más: reformular al vocabulario
del Código, buscar varias materias (despido + aviso + plazo para demandar),
seguir remisiones entre artículos y hacer cálculos con fechas y topes. El
agente decide esos pasos; las calculadoras hacen la aritmética.

Por qué bucle manual (y no el Tool Runner del SDK): se necesita (1) un tope de
pasos, (2) la traza de cada llamada para los evals del agente, y (3) registrar
el texto legal que el agente realmente vio, contra el que se verifican sus citas.

La respuesta final usa el mismo esquema `LegalAnswer` que CAG y RAG.
"""

from __future__ import annotations

import time
import uuid
from datetime import date
from dataclasses import dataclass, field

from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from app.agent.tools import TOOLS, ToolExecutor
from app.config import get_settings
from app.generation.citations import verify_citations
from app.generation.schemas import CitationReport, LegalAnswer
from app.llm import FALLBACK_BETA, RefusalError, Usage, get_client, usage_from
from app.observability import log_event
from app.prompts.loader import load_prompt


@dataclass
class ToolCall:
    name: str
    input: dict
    is_error: bool
    latency_ms: float
    output_preview: str


@dataclass
class AgentResult:
    request_id: str
    answer: LegalAnswer
    trace: list[ToolCall]
    seen_articles: list[str]
    seen_text: dict[str, str]
    citation_report: CitationReport
    usage: Usage
    steps: int
    hit_step_limit: bool = False
    extra: dict = field(default_factory=dict)


async def run_agent(session: AsyncSession, question: str) -> AgentResult:
    settings = get_settings()
    client = get_client()
    request_id = str(uuid.uuid4())
    executor = ToolExecutor(session)
    trace: list[ToolCall] = []
    total = Usage()
    # La fecha de hoy va en el mensaje (no en el sistema) para no invalidar la caché:
    # sin ella el agente no puede saber si un plazo legal ya venció.
    today = date.today().isoformat()
    messages: list[dict] = [{"role": "user", "content": f"Fecha de hoy: {today}\n\n{question}"}]
    # Sistema + herramientas son estables: caché explícita en el sistema; la
    # caché automática (top-level) cubre además la conversación que va creciendo.
    system = [{"type": "text", "text": load_prompt("agent"), "cache_control": {"type": "ephemeral"}}]

    for step in range(1, settings.agent_max_steps + 1):
        last_step = step == settings.agent_max_steps
        started = time.perf_counter()
        response = client.beta.messages.parse(
            model=settings.llm_model,
            max_tokens=16000,
            betas=[FALLBACK_BETA],
            fallbacks="default",
            thinking={"type": "adaptive"},
            output_config={"effort": settings.llm_effort},
            cache_control={"type": "ephemeral"},
            system=system,
            tools=TOOLS,
            # En el último paso se prohíben más herramientas: debe responder con lo que tiene.
            tool_choice={"type": "none"} if last_step else {"type": "auto"},
            messages=messages,
            output_format=LegalAnswer,
        )
        usage = usage_from(response, (time.perf_counter() - started) * 1000)
        total.add(usage)
        log_event("agent_step", request_id=request_id, step=step, stop_reason=response.stop_reason,
                  cost_usd=round(usage.cost_usd, 5), cache_read=usage.cache_read_input_tokens)

        if response.stop_reason == "refusal":
            raise RefusalError("El modelo rechazó la consulta.")

        tool_uses = [b for b in response.content if b.type == "tool_use"]
        if response.stop_reason != "tool_use" or not tool_uses:
            try:
                answer = response.parsed_output
                if answer is None:
                    raise ValueError(f"sin salida estructurada (stop_reason={response.stop_reason})")
            except (ValidationError, ValueError) as exc:
                raise RuntimeError(f"Respuesta final inválida: {exc}") from exc
            report = verify_citations(answer, executor.seen_text, request_id=request_id)
            log_event("agent_done", request_id=request_id, steps=step, tools=len(trace),
                      cost_usd=round(total.cost_usd, 4), latency_ms=round(total.latency_ms))
            return AgentResult(
                request_id, answer, trace, list(executor.seen_text), dict(executor.seen_text), report, total, step,
                hit_step_limit=last_step,
            )

        messages.append({"role": "assistant", "content": response.content})
        results = []
        for block in tool_uses:  # todas las respuestas de herramientas van en UN mensaje
            t0 = time.perf_counter()
            content, is_error = await executor.run(block.name, block.input)
            ms = (time.perf_counter() - t0) * 1000
            trace.append(ToolCall(block.name, dict(block.input), is_error, ms, content[:200]))
            log_event("agent_tool", request_id=request_id, tool=block.name, input=block.input,
                      is_error=is_error, latency_ms=round(ms))
            results.append({"type": "tool_result", "tool_use_id": block.id, "content": content, "is_error": is_error})
        messages.append({"role": "user", "content": results})

    raise RuntimeError("unreachable")  # pragma: no cover
