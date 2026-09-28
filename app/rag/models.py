"""Tabla `chunks`: un fragmento de artículo por fila, con su vector y su tsvector.

A diferencia del estimador (tablas `documents` + `chunks`), aquí hay un único
documento —el Código— así que una tabla basta; el "documento padre" de cada
chunk es su artículo (`article_id`), que es además la unidad de citación.
"""

from pgvector.sqlalchemy import Vector
from sqlalchemy import Computed, Integer, Text
from sqlalchemy.dialects.postgresql import JSONB, TSVECTOR
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base

EMBEDDING_DIMENSION = 1536


class ChunkRow(Base):
    __tablename__ = "chunks"

    chunk_id: Mapped[str] = mapped_column(Text, primary_key=True)  # "art-67#1"
    article_id: Mapped[str] = mapped_column(Text, index=True)
    part: Mapped[int] = mapped_column(Integer)
    total_parts: Mapped[int] = mapped_column(Integer)
    content: Mapped[str] = mapped_column(Text)  # texto legal del fragmento (lo que se muestra y cita)
    embed_text: Mapped[str] = mapped_column(Text)  # contexto jerárquico + content (lo que se indexa)
    embedding: Mapped[list[float]] = mapped_column(Vector(EMBEDDING_DIMENSION))
    chunk_metadata: Mapped[dict] = mapped_column("metadata", JSONB, server_default="{}")
    # Columna generada por Postgres (migración 0001); nunca se escribe desde Python.
    embed_tsv: Mapped[str | None] = mapped_column(
        TSVECTOR, Computed("to_tsvector('spanish', embed_text)", persisted=True)
    )
