"""Tabla chunks con vector (pgvector, HNSW) y tsvector en español (full-text).

- HNSW con distancia coseno: ~1.000 filas no lo exigen, pero es el índice que
  usaríamos en producción y no cuesta nada tenerlo desde el inicio.
- `embed_tsv` generado desde `embed_text` (ruta jerárquica + texto) con la
  configuración 'spanish': stemming ("vacaciones"/"vacación") y stopwords
  correctas. Incluir la ruta hace que "FERIADO ANUAL" del título del capítulo
  también cuente para la búsqueda léxica de cada artículo del capítulo.

Revision ID: 0001
Revises:
"""

import sqlalchemy as sa
from pgvector.sqlalchemy import Vector
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    op.create_table(
        "chunks",
        sa.Column("chunk_id", sa.Text, primary_key=True),
        sa.Column("article_id", sa.Text, nullable=False),
        sa.Column("part", sa.Integer, nullable=False),
        sa.Column("total_parts", sa.Integer, nullable=False),
        sa.Column("content", sa.Text, nullable=False),
        sa.Column("embed_text", sa.Text, nullable=False),
        sa.Column("embedding", Vector(1536), nullable=False),
        sa.Column("metadata", postgresql.JSONB, server_default="{}", nullable=False),
    )
    op.execute(
        "ALTER TABLE chunks ADD COLUMN embed_tsv tsvector "
        "GENERATED ALWAYS AS (to_tsvector('spanish', embed_text)) STORED"
    )
    op.create_index("ix_chunks_article_id", "chunks", ["article_id"])
    op.create_index("ix_chunks_embed_tsv", "chunks", ["embed_tsv"], postgresql_using="gin")
    op.execute(
        "CREATE INDEX ix_chunks_embedding_hnsw ON chunks "
        "USING hnsw (embedding vector_cosine_ops)"
    )


def downgrade() -> None:
    op.drop_table("chunks")
