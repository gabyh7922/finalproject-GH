"""Chunking estructural por artículo (Sesión 07, adaptado al dominio legal).

Estrategia: **un artículo = un chunk**, porque el artículo es la unidad de
sentido y de citación de una ley. Sin tamaño fijo ni overlap: cortar a ciegas
cada N tokens partiría un inciso por la mitad y mezclaría artículos.

Excepción: los artículos largos (>400 tokens, 106 de 733) se dividen en partes
agrupando incisos completos. Motivo: el cross-encoder del reranking solo lee
~512 tokens del par (pregunta, chunk) y truncaría el final de un artículo largo;
además un vector de un artículo de 2.000 tokens "promedia" temas distintos.
Cada parte lleva el encabezado de su artículo para no perder a qué norma pertenece.

Enriquecimiento contextual: el texto que se embebe antepone la ruta jerárquica
(Libro › Título › Capítulo › Párrafo). El art. 67 no dice "vacaciones" pero su
capítulo se llama "DEL FERIADO ANUAL Y DE LOS PERMISOS": esa ruta acerca el
chunk a preguntas que usan el término del título y no del artículo.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import tiktoken

from app.corpus import CorpusArticle

MAX_CHUNK_TOKENS = 400
_ENCODING = tiktoken.encoding_for_model("text-embedding-3-small")


def count_tokens(text: str) -> int:
    return len(_ENCODING.encode(text))


@dataclass
class Chunk:
    chunk_id: str
    article_id: str
    part: int
    total_parts: int
    content: str
    embed_text: str
    metadata: dict = field(default_factory=dict)


def _split_paragraphs(text: str, max_tokens: int) -> list[str]:
    """Agrupa incisos completos en bloques de hasta `max_tokens` (un inciso gigante va solo)."""
    groups: list[list[str]] = [[]]
    size = 0
    for paragraph in text.split("\n\n"):
        tokens = count_tokens(paragraph)
        if groups[-1] and size + tokens > max_tokens:
            groups.append([])
            size = 0
        groups[-1].append(paragraph)
        size += tokens
    return ["\n\n".join(g) for g in groups if g]


def chunk_article(article: CorpusArticle, max_tokens: int = MAX_CHUNK_TOKENS) -> list[Chunk]:
    parts = [article.text] if count_tokens(article.text) <= max_tokens else _split_paragraphs(article.text, max_tokens)
    total = len(parts)
    chunks = []
    for i, body in enumerate(parts, start=1):
        content = body if i == 1 else f"{article.label} (continuación, parte {i} de {total})\n\n{body}"
        embed_text = f"Código del Trabajo › {article.breadcrumb}\n\n{content}"
        chunks.append(
            Chunk(
                chunk_id=f"{article.article_id}#{i}",
                article_id=article.article_id,
                part=i,
                total_parts=total,
                content=content,
                embed_text=embed_text,
                metadata={
                    "label": article.label,
                    "path": list(article.path),
                    "transitorio": article.transitorio,
                    "token_count": count_tokens(embed_text),
                },
            )
        )
    return chunks


def chunk_corpus(articles: list[CorpusArticle]) -> list[Chunk]:
    return [chunk for article in articles for chunk in chunk_article(article)]
