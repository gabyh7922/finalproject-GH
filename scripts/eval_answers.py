"""Eval end-to-end: CAG vs RAG vs Agente sobre el golden set.

Métricas deterministas (sin LLM-juez), por respuesta:
    citation_precision  citas verificadas / citas totales (artículo visto + frase textual)
    article_recall      fracción de artículos relevantes del golden set que la respuesta CITA
    scope_ok            out_of_scope coincide con la anotación (3 preguntas fuera de alcance)
    cost_usd, latency_ms
Solo agente: nº de llamadas a herramientas y si usó calculadora.

Las respuestas quedan en evals/results/answers_<sistema>.jsonl para que RAGAS
(scripts/eval_ragas.py) las puntúe sin volver a pagar la generación.

Uso:
    uv run python scripts/eval_answers.py rag agent        # todas las preguntas
    uv run python scripts/eval_answers.py cag --limit 12   # CAG es caro: subconjunto
"""

import argparse
import asyncio
import json
import statistics
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.database import get_sessionmaker  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
GOLDEN = ROOT / "evals" / "golden_set.json"
OUT = ROOT / "evals" / "results"


def answer_text(answer) -> str:
    return answer.short_answer + "\n" + "\n".join(f"- {p.statement}" for p in answer.points)


async def run_one(system: str, question: str) -> dict:
    t0 = time.perf_counter()
    if system == "cag":
        from app.cag.service import answer_question

        r = await asyncio.to_thread(answer_question, question)
        contexts, retrieved, extra = {}, [], {}
    else:
        async with get_sessionmaker()() as session:
            if system == "rag":
                from app.generation.rag_pipeline import answer_question

                r = await answer_question(session, question)
                contexts, retrieved, extra = r.context, [c.article_id for c in r.retrieved], {}
            else:
                from app.agent.runner import run_agent

                r = await run_agent(session, question)
                contexts, retrieved = r.seen_text, r.seen_articles
                extra = {
                    "tool_calls": [{"name": t.name, "input": t.input, "is_error": t.is_error} for t in r.trace],
                    "steps": r.steps,
                    "hit_step_limit": r.hit_step_limit,
                }
    cited = sorted({c.article_id for p in r.answer.points for c in p.citations})
    return {
        "answer": r.answer.model_dump(),
        "answer_text": answer_text(r.answer),
        "cited_article_ids": cited,
        "retrieved_article_ids": retrieved,
        "contexts": contexts,
        "citations": [c.model_dump() for c in r.citation_report.checks],
        "citation_precision": r.citation_report.citation_precision,
        "cost_usd": r.usage.cost_usd,
        "latency_ms": (time.perf_counter() - t0) * 1000,
        **extra,
    }


async def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("systems", nargs="+", choices=["cag", "rag", "agent"])
    parser.add_argument("--limit", type=int, default=None)
    args = parser.parse_args()

    queries = json.loads(GOLDEN.read_text(encoding="utf-8"))["queries"]
    if args.limit:
        # subconjunto estable que incluye preguntas fuera de alcance
        in_scope = [q for q in queries if q["relevant_article_ids"]]
        queries = in_scope[: args.limit - 1] + [q for q in queries if not q["relevant_article_ids"]][:1]
    OUT.mkdir(parents=True, exist_ok=True)

    for system in args.systems:
        path = OUT / f"answers_{system}.jsonl"
        done = {}
        if path.exists():  # reanudable: no se vuelve a pagar lo ya generado
            done = {json.loads(line)["id"]: json.loads(line) for line in path.read_text().splitlines() if line}
        with path.open("a", encoding="utf-8") as fh:
            for q in queries:
                if q["id"] in done:
                    continue
                try:
                    rec = await run_one(system, q["query"])
                except Exception as exc:  # una falla no debe perder las demás respuestas
                    rec = {"error": repr(exc)[:500]}
                rec.update(id=q["id"], query=q["query"], relevant=q["relevant_article_ids"],
                           out_of_scope_expected=bool(q.get("out_of_scope")))
                fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
                fh.flush()
                done[q["id"]] = rec
                print(f"[{system}] {q['id']} cp={rec.get('citation_precision', 'ERR')} ${rec.get('cost_usd', 0):.3f}")
        print(summarize(system, [done[q["id"]] for q in queries if q["id"] in done]))


def summarize(system: str, recs: list[dict]) -> str:
    ok = [r for r in recs if "error" not in r]
    in_scope = [r for r in ok if r["relevant"]]
    recall = [len(set(r["cited_article_ids"]) & set(r["relevant"])) / len(r["relevant"]) for r in in_scope]
    scope_ok = [r["answer"]["out_of_scope"] == r["out_of_scope_expected"] for r in ok]
    lines = [
        f"\n== {system}: {len(ok)}/{len(recs)} respuestas sin error ==",
        f"citation_precision  {statistics.fmean(r['citation_precision'] for r in ok):.3f}",
        f"article_recall      {statistics.fmean(recall):.3f}" if recall else "",
        f"scope_accuracy      {statistics.fmean(scope_ok):.3f}",
        f"costo medio         US${statistics.fmean(r['cost_usd'] for r in ok):.4f}",
        f"latencia p50        {statistics.median(r['latency_ms'] for r in ok) / 1000:.1f}s",
    ]
    if system == "agent":
        lines.append(f"herramientas/preg.  {statistics.fmean(len(r['tool_calls']) for r in ok):.1f}")
    return "\n".join(line for line in lines if line)


if __name__ == "__main__":
    asyncio.run(main())
