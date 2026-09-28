"""Ingesta RAG: artículos -> chunks -> embeddings -> Postgres/pgvector.

Idempotente: vacía la tabla y la vuelve a cargar (el corpus es uno y cabe
entero; reemplazar es más simple y seguro que calcular diferencias).

Uso (con `docker compose -p lexlaboral up -d` y `uv run alembic upgrade head`):
    uv run python scripts/ingest.py             # reemplaza todo
    uv run python scripts/ingest.py --if-empty  # solo si la tabla está vacía (arranque en producción)
"""

import asyncio
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import delete, func, select  # noqa: E402

from app.corpus import load_corpus, vigentes  # noqa: E402
from app.database import get_sessionmaker  # noqa: E402
from app.rag.chunker import chunk_corpus  # noqa: E402
from app.rag.embedder import PRICE_PER_MILLION_TOKENS_USD, embed_many  # noqa: E402
from app.rag.models import ChunkRow  # noqa: E402


async def main() -> None:
    if "--if-empty" in sys.argv:
        async with get_sessionmaker()() as session:
            existing = await session.scalar(select(func.count()).select_from(ChunkRow))
        if existing:
            print(f"La tabla ya tiene {existing} chunks: no se reingesta.")
            return
    started = time.perf_counter()
    chunks = chunk_corpus(vigentes())
    total_tokens = sum(c.metadata["token_count"] for c in chunks)
    print(f"{len(chunks)} chunks de {len(vigentes())} artículos · {total_tokens:,} tokens a embeber")

    vectors = embed_many([c.embed_text for c in chunks])

    async with get_sessionmaker()() as session:
        await session.execute(delete(ChunkRow))
        session.add_all(
            ChunkRow(
                chunk_id=c.chunk_id,
                article_id=c.article_id,
                part=c.part,
                total_parts=c.total_parts,
                content=c.content,
                embed_text=c.embed_text,
                embedding=v,
                chunk_metadata={**c.metadata, "fecha_version": load_corpus()["fecha_version"]},
            )
            for c, v in zip(chunks, vectors)
        )
        await session.commit()
        stored = await session.scalar(select(func.count()).select_from(ChunkRow))

    cost = total_tokens / 1_000_000 * PRICE_PER_MILLION_TOKENS_USD
    print(f"{stored} chunks guardados · costo embeddings ~US${cost:.4f} · {time.perf_counter() - started:.1f}s")


if __name__ == "__main__":
    asyncio.run(main())
