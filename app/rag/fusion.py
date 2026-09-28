"""Reciprocal Rank Fusion (Sesión 10, reutilizado sin cambios).

La búsqueda vectorial (distancia coseno) y la léxica (`ts_rank_cd`) viven en
escalas incomparables: sumar sus puntuaciones brutas es sumar magnitudes
distintas. RRF ignora las puntuaciones y fusiona solo por posición — cada
documento suma 1/(k + posición) por cada ranking en el que aparece — así que
premia el consenso entre ramas sin necesitar calibrar nada.
"""

from collections import defaultdict

DEFAULT_RRF_K = 60


def reciprocal_rank_fusion(
    rankings: list[list[str]], k: int = DEFAULT_RRF_K, weights: list[float] | None = None
) -> list[str]:
    """Fusiona varios rankings de ids en un único ranking ordenado por consenso.

    `weights` (RRF ponderado) permite que una rama ruidosa aporte menos: con
    peso 1.0 en todas las ramas es el RRF clásico.
    """
    weights = weights or [1.0] * len(rankings)
    scores: dict[str, float] = defaultdict(float)
    for ranking, weight in zip(rankings, weights):
        for rank, item_id in enumerate(ranking, start=1):
            scores[item_id] += weight / (k + rank)
    return [
        item_id
        for item_id, _score in sorted(scores.items(), key=lambda item: item[1], reverse=True)
    ]
