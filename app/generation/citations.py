"""Verificación post-generación de citas (Sesión 11, reforzada).

Nada en el esquema impide que el modelo cite un artículo que no vio o que
"cite" una frase que no está en el artículo. Esta verificación corre en cada
respuesta y compara contra el contexto real entregado al modelo.
"""

from __future__ import annotations

import re
import unicodedata

from app.generation.schemas import CitationCheck, CitationReport, LegalAnswer
from app.observability import log_event


def _normalize(text: str) -> str:
    """Comparación tolerante a mayúsculas, espacios, comillas y guiones tipográficos."""
    text = unicodedata.normalize("NFKC", text).lower()
    text = text.replace("“", '"').replace("”", '"').replace("’", "'").replace("–", "-").replace("—", "-")
    text = re.sub(r"[\"'«»]", "", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip(" .,;:…")


def quote_in_text(quote: str, text: str) -> bool:
    q = _normalize(quote)
    if not q:
        return False
    body = _normalize(text)
    if q in body:
        return True
    # El modelo a veces une dos tramos con "..." — cada tramo debe aparecer, en orden.
    parts = [p.strip() for p in re.split(r"\.{3}|…", q) if p.strip()]
    if len(parts) < 2:
        return False
    pos = 0
    for part in parts:
        idx = body.find(part, pos)
        if idx < 0:
            return False
        pos = idx + len(part)
    return True


def verify_citations(answer: LegalAnswer, context: dict[str, str], *, request_id: str) -> CitationReport:
    """`context` = {article_id: texto completo del artículo} que recibió el modelo."""
    checks: list[CitationCheck] = []
    for point in answer.points:
        for citation in point.citations:
            if citation.article_id not in context:
                status = "dangling"
            elif not quote_in_text(citation.quote, context[citation.article_id]):
                status = "misquoted"
            else:
                status = "verified"
            checks.append(CitationCheck(article_id=citation.article_id, status=status))

    report = CitationReport(checks=checks, ungrounded_points=sum(not p.grounded for p in answer.points))
    log_event(
        "citation_verification",
        request_id=request_id,
        verified=report.verified,
        dangling=report.dangling,
        misquoted=report.misquoted,
        ungrounded_points=report.ungrounded_points,
    )
    return report
