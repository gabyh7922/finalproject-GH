"""Mide la recuperación contra el golden set (Sesión 10, adaptado).

Configuraciones:
    A  Vectorial               sin reranking
    B  Híbrida (RRF)           sin reranking
    C  Vectorial  + reranking  (recall 50)
    D  Híbrida    + reranking  (recall 50)
    E  Híbrida    + reranking  (recall 20)   <- ¿se puede recortar la latencia del reranker?

Métricas por query (solo las 34 preguntas dentro del alcance), a nivel de ARTÍCULO:
    hit@k     ¿al menos un artículo relevante en el top k?
    recall@k  fracción de los artículos relevantes que aparecen en el top k
    MRR@k     1 / posición del primer artículo relevante (0 si no aparece)
    latencia  de retrieve() (búsqueda + fusión + rerank), sin el embedding de la query,
              que es un costo común a todas las configuraciones.

A diferencia del estimador (precisión@5), aquí se usa recall/hit/MRR: la mayoría
de las preguntas tiene 1-2 artículos relevantes, así que precisión@5 tendría un
techo de 0,2-0,4 aunque la recuperación sea perfecta.

Uso:
    uv run python scripts/eval_retrieval.py            # escribe evals/results/retrieval.{json,md}
"""

import asyncio
import json
import statistics
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.database import get_sessionmaker  # noqa: E402
from app.rag.embedder import embed_many  # noqa: E402
from app.rag.retrieval import get_default_reranker, retrieve  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
GOLDEN = ROOT / "evals" / "golden_set.json"
OUT_DIR = ROOT / "evals" / "results"

CONFIGS = [
    ("A", "Vectorial", "No", "vector", False, 50),
    ("B", "Híbrida", "No", "hybrid", False, 50),
    ("C", "Vectorial", "Sí (50)", "vector", True, 50),
    ("D", "Híbrida", "Sí (50)", "hybrid", True, 50),
    ("E", "Híbrida", "Sí (20)", "hybrid", True, 20),
]


def score(retrieved_ids: list[str], relevant: set[str], k: int) -> dict:
    top = retrieved_ids[:k]
    hits = [i for i, aid in enumerate(top, start=1) if aid in relevant]
    return {
        "hit": 1.0 if hits else 0.0,
        "recall": len({aid for aid in top if aid in relevant}) / len(relevant),
        "mrr": 1.0 / hits[0] if hits else 0.0,
    }


async def main(selected: set[str] | None = None) -> None:
    golden = json.loads(GOLDEN.read_text(encoding="utf-8"))
    k = golden["k"]
    queries = [q for q in golden["queries"] if q["relevant_article_ids"]]
    configs = [c for c in CONFIGS if not selected or c[0] in selected]

    print(f"Embebiendo {len(queries)} preguntas...")
    vectors = dict(zip([q["id"] for q in queries], embed_many([q["query"] for q in queries])))
    if any(c[4] for c in configs):
        print("Cargando el cross-encoder...")
        get_default_reranker().load()

    results: dict = {}
    for cfg_id, search_label, rerank_label, mode, rerank, recall_k in configs:
        per_query = {}
        for q in queries:
            async with get_sessionmaker()() as session:
                t0 = time.perf_counter()
                chunks, _ = await retrieve(
                    session, query_text=q["query"], query_vector=vectors[q["id"]],
                    search_mode=mode, rerank=rerank, top_k=k, recall_k=recall_k,
                )
                latency = (time.perf_counter() - t0) * 1000
            ids = [c.article_id for c in chunks]
            per_query[q["id"]] = {**score(ids, set(q["relevant_article_ids"]), k), "latency_ms": latency, "retrieved": ids}
        summary = {
            m: statistics.fmean(v[m] for v in per_query.values()) for m in ("hit", "recall", "mrr")
        }
        summary["latency_p50_ms"] = statistics.median(v["latency_ms"] for v in per_query.values())
        results[cfg_id] = {"label": f"{search_label} / rerank {rerank_label}", "summary": summary, "per_query": per_query}
        print(f"  {cfg_id}: hit@{k}={summary['hit']:.2f} recall@{k}={summary['recall']:.2f} "
              f"MRR={summary['mrr']:.2f} p50={summary['latency_p50_ms']:.0f}ms")

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    (OUT_DIR / "retrieval.json").write_text(json.dumps(results, ensure_ascii=False, indent=1), encoding="utf-8")
    (OUT_DIR / "retrieval.md").write_text(render_markdown(results, configs, queries, k), encoding="utf-8")
    print(f"-> {OUT_DIR / 'retrieval.md'}")


def render_markdown(results: dict, configs: list, queries: list, k: int) -> str:
    lines = [
        f"# Evaluación de recuperación — {len(queries)} preguntas del golden set (k={k})\n",
        f"| Config | Búsqueda | Reranking | hit@{k} | recall@{k} | MRR@{k} | Latencia p50 (ms) |",
        "| --- | --- | --- | --- | --- | --- | --- |",
    ]
    for cfg_id, search_label, rerank_label, *_ in configs:
        s = results[cfg_id]["summary"]
        lines.append(
            f"| {cfg_id} | {search_label} | {rerank_label} | {s['hit']:.2f} | {s['recall']:.2f} "
            f"| {s['mrr']:.2f} | {s['latency_p50_ms']:.0f} |"
        )
    lines += ["", f"## MRR@{k} por pregunta", "", "| Pregunta | " + " | ".join(c[0] for c in configs) + " |",
              "| --- | " + " | ".join("---" for _ in configs) + " |"]
    for q in queries:
        row = [f"{q['id']} {q['query'][:60]}"] + [f"{results[c[0]]['per_query'][q['id']]['mrr']:.2f}" for c in configs]
        lines.append("| " + " | ".join(row) + " |")
    return "\n".join(lines) + "\n"


if __name__ == "__main__":
    asyncio.run(main(set(sys.argv[1:]) or None))
