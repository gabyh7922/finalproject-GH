"""RAGAS sobre las respuestas ya generadas (evals/results/answers_<sistema>.jsonl).

Mismas cuatro métricas que la Sesión 11 del curso:
    faithfulness       ¿cada afirmación está respaldada por el contexto que vio el sistema?
    answer_relevancy   ¿la respuesta aborda la pregunta?
    context_precision  ¿los artículos recuperados son relevantes y están bien ordenados?
    context_recall     ¿el contexto contiene lo que pide la respuesta de referencia?

Juez: gpt-4o-mini; embeddings: text-embedding-3-small (OpenAI). Se usa un juez
de OTRO proveedor que el generador (Claude) para no premiar el propio estilo.
Solo RAG y agente: el CAG no tiene "contexto recuperado" (ve el Código entero),
así que las métricas de contexto no aplican; se evalúa con las métricas
deterministas de scripts/eval_answers.py.

Uso:
    uv run --group eval python scripts/eval_ragas.py rag agent
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from ragas import EvaluationDataset, SingleTurnSample, evaluate  # noqa: E402
from ragas.embeddings import LangchainEmbeddingsWrapper  # noqa: E402
from ragas.llms import LangchainLLMWrapper  # noqa: E402
from ragas.metrics import answer_relevancy, context_precision, context_recall, faithfulness  # noqa: E402

from app.config import get_settings  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
GOLDEN = ROOT / "evals" / "golden_set.json"
RESULTS = ROOT / "evals" / "results"
METRICS = [faithfulness, answer_relevancy, context_precision, context_recall]
NAMES = [m.name for m in METRICS]


def judge():
    from langchain_openai import ChatOpenAI, OpenAIEmbeddings

    key = get_settings().openai_api_key
    return (
        LangchainLLMWrapper(ChatOpenAI(model="gpt-4o-mini", api_key=key, temperature=0)),
        LangchainEmbeddingsWrapper(OpenAIEmbeddings(model="text-embedding-3-small", api_key=key)),
    )


def main(systems: list[str]) -> None:
    ground_truth = {q["id"]: q["ground_truth"] for q in json.loads(GOLDEN.read_text())["queries"]}
    llm, emb = judge()
    report = ["# RAGAS — respuestas en lenguaje natural vs. referencia del golden set\n"]
    summary_rows = []
    for system in systems:
        recs = [json.loads(line) for line in (RESULTS / f"answers_{system}.jsonl").read_text().splitlines() if line]
        recs = [r for r in recs if "error" not in r and r["relevant"]]  # dentro del alcance
        dataset = EvaluationDataset(samples=[
            SingleTurnSample(
                user_input=r["query"],
                response=r["answer_text"],
                retrieved_contexts=list(r["contexts"].values()) or ["(sin contexto)"],
                reference=ground_truth[r["id"]],
            )
            for r in recs
        ])
        print(f"RAGAS sobre {len(recs)} respuestas de {system}...")
        df = evaluate(dataset, metrics=METRICS, llm=llm, embeddings=emb).to_pandas()
        means = {n: float(df[n].mean()) for n in NAMES}
        summary_rows.append((system, means))
        report += [f"\n## {system}\n", "| Pregunta | " + " | ".join(NAMES) + " |", "| --- |" + " --- |" * len(NAMES)]
        for r, (_, row) in zip(recs, df.iterrows()):
            report.append(f"| {r['id']} | " + " | ".join(f"{row[n]:.2f}" for n in NAMES) + " |")
        report.append("| **Promedio** | " + " | ".join(f"**{means[n]:.2f}**" for n in NAMES) + " |")

    report[1:1] = ["\n| Sistema | " + " | ".join(NAMES) + " |", "| --- |" + " --- |" * len(NAMES)] + [
        f"| {s} | " + " | ".join(f"{m[n]:.2f}" for n in NAMES) + " |" for s, m in summary_rows
    ]
    (RESULTS / "ragas.md").write_text("\n".join(report) + "\n", encoding="utf-8")
    print("\n".join(report[:2 + len(summary_rows) + 1]))


if __name__ == "__main__":
    main(sys.argv[1:] or ["rag", "agent"])
