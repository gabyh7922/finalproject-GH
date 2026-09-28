"""¿La búsqueda híbrida sirve cuando las consultas las escribe el agente?

Hipótesis: la rama léxica falló con las preguntas coloquiales de las personas
("vacaciones", "me echaron"), pero el agente reformula con el vocabulario del
Código ("feriado anual", "término del contrato"), justo donde la coincidencia
exacta de términos debería ayudar.

Método (sin costo de LLM): se toman las consultas `buscar_articulos` que el
agente emitió realmente en evals/results/answers_agent.jsonl y se vuelven a
ejecutar con búsqueda vectorial e híbrida. Por pregunta del golden set se une
el top-5 de todas las consultas del agente y se mide recall de los artículos
relevantes. Referencia: la pregunta original del usuario con búsqueda vectorial.

Uso:
    uv run python scripts/eval_agent_queries.py
"""

import asyncio
import json
import statistics
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.database import get_sessionmaker  # noqa: E402
from app.rag.embedder import embed_one  # noqa: E402
from app.rag.retrieval import retrieve  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
ANSWERS = ROOT / "evals" / "results" / "answers_agent.jsonl"
OUT = ROOT / "evals" / "results" / "agent_queries.md"


async def top_ids(query: str, mode: str, cache: dict) -> list[str]:
    if query not in cache:
        cache[query] = embed_one(query)
    async with get_sessionmaker()() as session:
        chunks, _ = await retrieve(session, query_text=query, query_vector=cache[query], search_mode=mode, rerank=False, top_k=5)
    return [c.article_id for c in chunks]


async def main() -> None:
    recs = [json.loads(line) for line in ANSWERS.read_text().splitlines() if line]
    recs = [r for r in recs if "error" not in r and r["relevant"]]
    cache: dict = {}
    rows, scores = [], {"usuario_vector": [], "agente_vector": [], "agente_hibrida": []}
    for r in recs:
        rel = set(r["relevant"])
        agent_queries = [t["input"]["consulta"] for t in r["tool_calls"] if t["name"] == "buscar_articulos"]
        base = set(await top_ids(r["query"], "vector", cache))
        vec, hyb = set(), set()
        for q in agent_queries:
            vec |= set(await top_ids(q, "vector", cache))
            hyb |= set(await top_ids(q, "hybrid", cache))
        s = {k: len(rel & v) / len(rel) for k, v in (("usuario_vector", base), ("agente_vector", vec), ("agente_hibrida", hyb))}
        for k in scores:
            scores[k].append(s[k])
        rows.append(f"| {r['id']} | {len(agent_queries)} | {s['usuario_vector']:.2f} | {s['agente_vector']:.2f} | {s['agente_hibrida']:.2f} | {'; '.join(agent_queries)[:90]} |")

    means = {k: statistics.fmean(v) for k, v in scores.items()}
    md = [
        f"# Consultas del agente: vectorial vs híbrida ({len(recs)} preguntas)\n",
        "Recall de artículos relevantes en la unión de los top-5 de cada consulta.\n",
        "| Búsqueda | recall |", "| --- | --- |",
        f"| Pregunta del usuario, vectorial (1 consulta) | {means['usuario_vector']:.2f} |",
        f"| Consultas del agente, vectorial | {means['agente_vector']:.2f} |",
        f"| Consultas del agente, híbrida | {means['agente_hibrida']:.2f} |",
        "", "| Pregunta | nº consultas | usuario·vector | agente·vector | agente·híbrida | consultas del agente |",
        "| --- | --- | --- | --- | --- | --- |", *rows,
    ]
    OUT.write_text("\n".join(md) + "\n", encoding="utf-8")
    print("\n".join(md[:8]))


if __name__ == "__main__":
    asyncio.run(main())
