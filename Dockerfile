FROM python:3.11-slim

RUN pip install --no-cache-dir uv
WORKDIR /app

# Solo dependencias de producción: sin grupos dev/eval/rerank (PyTorch no se usa
# en producción porque el reranker no mejoró la recuperación; ver README).
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

COPY . .
RUN uv sync --frozen --no-dev

ENV PORT=8000
EXPOSE 8000
CMD ["sh", "scripts/start.sh"]
