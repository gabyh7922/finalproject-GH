"""Acceso al corpus procesado (data/processed/articulos.json)."""

from __future__ import annotations

import json
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

CORPUS_PATH = Path(__file__).resolve().parent.parent / "data" / "processed" / "articulos.json"


@dataclass(frozen=True)
class CorpusArticle:
    article_id: str
    number: str
    text: str
    path: tuple[str, ...]
    derogado: bool
    transitorio: bool

    @property
    def label(self) -> str:
        """Nombre legible para mostrar al usuario: 'Art. 67' / 'Art. 1 transitorio'."""
        return f"Art. {self.number.lower()}" + (" transitorio" if self.transitorio else "")

    @property
    def breadcrumb(self) -> str:
        return " › ".join(self.path)


@lru_cache
def load_corpus() -> dict:
    return json.loads(CORPUS_PATH.read_text(encoding="utf-8"))


@lru_cache
def articles_by_id() -> dict[str, CorpusArticle]:
    return {
        a["article_id"]: CorpusArticle(
            article_id=a["article_id"],
            number=a["number"],
            text=a["text"],
            path=tuple(a["path"]),
            derogado=a["derogado"],
            transitorio=a["transitorio"],
        )
        for a in load_corpus()["articulos"]
    }


def vigentes() -> list[CorpusArticle]:
    return [a for a in articles_by_id().values() if not a.derogado]
