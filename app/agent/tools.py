"""Herramientas del agente: definiciones (JSON Schema estricto) y ejecución."""

from __future__ import annotations

import asyncio
import json
import re
from datetime import date

from sqlalchemy.ext.asyncio import AsyncSession

from app.agent.calculators import calcular_feriado, calcular_indemnizacion
from app.config import get_settings
from app.corpus import articles_by_id
from app.rag.embedder import embed_one
from app.rag.retrieval import retrieve

TOOLS = [
    {
        "name": "buscar_articulos",
        "description": (
            "Busca en el Código del Trabajo de Chile vigente y devuelve los artículos más relevantes "
            "(id, nombre, ubicación y el fragmento encontrado). Usa vocabulario del Código en la consulta."
        ),
        "strict": True,
        "input_schema": {
            "type": "object",
            "properties": {"consulta": {"type": "string", "description": "Consulta en lenguaje jurídico, p. ej. 'feriado anual días hábiles'."}},
            "required": ["consulta"],
            "additionalProperties": False,
        },
    },
    {
        "name": "leer_articulo",
        "description": "Devuelve el texto completo de un artículo del Código del Trabajo. Acepta 'art-161', '161' o '152 quáter J'.",
        "strict": True,
        "input_schema": {
            "type": "object",
            "properties": {"articulo": {"type": "string"}},
            "required": ["articulo"],
            "additionalProperties": False,
        },
    },
    {
        "name": "calcular_indemnizacion",
        "description": (
            "Calcula la indemnización legal por despido por necesidades de la empresa o desahucio "
            "(arts. 161, 162, 163, 172): años de servicio, tope de 330 días, tope de 90 UF y aviso previo."
        ),
        "strict": True,
        "input_schema": {
            "type": "object",
            "properties": {
                "remuneracion_mensual": {"type": "number", "description": "Última remuneración mensual en pesos."},
                "fecha_inicio": {"type": "string", "description": "YYYY-MM-DD"},
                "fecha_termino": {"type": "string", "description": "YYYY-MM-DD"},
                "aviso_con_30_dias": {"type": "boolean", "description": "true si el empleador avisó con 30 días de anticipación."},
                "valor_uf": {"type": ["number", "null"], "description": "Valor de la UF en pesos, si se conoce; si no, null."},
            },
            "required": ["remuneracion_mensual", "fecha_inicio", "fecha_termino", "aviso_con_30_dias", "valor_uf"],
            "additionalProperties": False,
        },
    },
    {
        "name": "calcular_feriado",
        "description": "Calcula los días hábiles de feriado anual (vacaciones): base del art. 67 más feriado progresivo del art. 68.",
        "strict": True,
        "input_schema": {
            "type": "object",
            "properties": {
                "fecha_ingreso": {"type": "string", "description": "Fecha de ingreso con el empleador actual, YYYY-MM-DD."},
                "fecha_consulta": {"type": "string", "description": "YYYY-MM-DD (hoy si no se indica otra)."},
                "anos_con_empleadores_anteriores": {"type": "integer", "description": "Años trabajados para empleadores anteriores (0 si no aplica)."},
                "zona_extrema": {"type": "boolean", "description": "true si trabaja en Magallanes, Aysén o la provincia de Palena."},
            },
            "required": ["fecha_ingreso", "fecha_consulta", "anos_con_empleadores_anteriores", "zona_extrema"],
            "additionalProperties": False,
        },
    },
]


def resolve_article_id(ref: str) -> str | None:
    """'art-161', '161', 'Art. 152 quáter J', '1 transitorio' -> article_id existente o None."""
    arts = articles_by_id()
    ref = ref.strip()
    if ref in arts:
        return ref
    from app.ingestion.parser import Article

    raw = re.sub(r"^(art(í|i)culo|art\.?)\s*", "", ref, flags=re.IGNORECASE).strip()
    transitorio = bool(re.search(r"transitorio", raw, re.IGNORECASE))
    raw = re.sub(r"transitorio", "", raw, flags=re.IGNORECASE).strip(" .-º°")
    candidate = Article(number=raw.upper(), text="", transitorio=transitorio).article_id
    return candidate if candidate in arts else None


class ToolExecutor:
    """Ejecuta herramientas y registra el texto legal que el agente realmente vio."""

    def __init__(self, session: AsyncSession):
        self.session = session
        self.seen_text: dict[str, str] = {}

    def _see(self, article_id: str, text: str) -> None:
        if text not in self.seen_text.get(article_id, ""):
            self.seen_text[article_id] = (self.seen_text.get(article_id, "") + "\n\n" + text).strip()

    async def run(self, name: str, args: dict) -> tuple[str, bool]:
        """Devuelve (contenido para el tool_result, is_error)."""
        try:
            if name == "buscar_articulos":
                return await self._buscar(args["consulta"]), False
            if name == "leer_articulo":
                return self._leer(args["articulo"])
            if name == "calcular_indemnizacion":
                r = calcular_indemnizacion(
                    float(args["remuneracion_mensual"]),
                    date.fromisoformat(args["fecha_inicio"]),
                    date.fromisoformat(args["fecha_termino"]),
                    bool(args["aviso_con_30_dias"]),
                    args.get("valor_uf"),
                )
                return json.dumps(r.to_dict(), ensure_ascii=False), False
            if name == "calcular_feriado":
                r = calcular_feriado(
                    date.fromisoformat(args["fecha_ingreso"]),
                    date.fromisoformat(args["fecha_consulta"]),
                    int(args["anos_con_empleadores_anteriores"]),
                    bool(args["zona_extrema"]),
                )
                return json.dumps(r.to_dict(), ensure_ascii=False), False
            return f"Herramienta desconocida: {name}", True
        except (ValueError, KeyError) as exc:
            return f"Error en los datos de entrada: {exc}", True

    async def _buscar(self, consulta: str) -> str:
        settings = get_settings()
        chunks, _ = await retrieve(
            self.session, query_text=consulta, query_vector=await asyncio.to_thread(embed_one, consulta),
            search_mode=settings.agent_search_mode, rerank=settings.agent_rerank, top_k=5,
        )
        arts = articles_by_id()
        out = []
        for c in chunks:
            self._see(c.article_id, c.content)
            a = arts[c.article_id]
            out.append(f'<resultado article_id="{a.article_id}" nombre="{a.label}" ubicacion="{a.breadcrumb}">\n{c.content}\n</resultado>')
        return "\n\n".join(out) or "Sin resultados."

    def _leer(self, ref: str) -> tuple[str, bool]:
        article_id = resolve_article_id(ref)
        if not article_id:
            return f"No existe el artículo '{ref}' en el Código del Trabajo vigente.", True
        a = articles_by_id()[article_id]
        self._see(article_id, a.text)
        estado = " (DEROGADO)" if a.derogado else ""
        return f'<articulo article_id="{a.article_id}" nombre="{a.label}{estado}" ubicacion="{a.breadcrumb}">\n{a.text}\n</articulo>', False
