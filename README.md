# ⚖️ LexLaboral — Asistente de IA sobre el Código del Trabajo de Chile

> Proyecto Final · AI Engineering · Autora: **Gaby (GH)**
> Rama de entrega: `finalproject-GH`

## El problema

En Chile, la mayoría de las dudas laborales del día a día ("¿cuántos días de vacaciones me
corresponden?", "¿me pueden despedir estando con licencia?", "¿cómo se calcula mi
indemnización?") tienen respuesta en el **Código del Trabajo**. Pero el Código tiene
**737 artículos**, lenguaje jurídico y remisiones cruzadas entre artículos: una persona común
no sabe dónde buscar, y un chatbot genérico responde de memoria, sin decir de dónde sale su
respuesta, y a veces inventa.

**LexLaboral** responde preguntas laborales **citando el artículo exacto** del Código que
respalda cada afirmación, y **verifica** que cada cita exista realmente en el texto recuperado.
Si la ley no cubre la pregunta, lo dice en vez de inventar.

## Datos reales

| | |
|---|---|
| Fuente | [LeyChile — Biblioteca del Congreso Nacional](https://www.bcn.cl/leychile/navegar?idNorma=207436) (servicio oficial XML) |
| Norma | DFL 1 (2003), texto refundido del Código del Trabajo · `idNorma 207436` |
| Versión | 2026-07-23 (versionada en `data/raw/codigo_trabajo.xml` para reproducibilidad) |
| Tamaño | 737 artículos (733 vigentes, 4 derogados), jerarquía Libro › Título › Capítulo › Párrafo |

## Estado del proyecto

| Fase | Pieza | Estado |
|---|---|---|
| 0 | Ingesta: parser del XML oficial → artículos limpios con jerarquía | ✅ |
| 1 | CAG: baseline con el Código en el contexto (prompt caching) | ✅ |
| 2 | RAG: chunking por artículo + embeddings + pgvector | ✅ |
| 3 | Recuperación híbrida (vector + full-text español) con RRF + reranking, medida con golden set | ✅ |
| 4 | Generación con citas por artículo + verificación de citas | ✅ código · ⏳ eval |
| 5 | Agente con herramientas (búsqueda, lectura de artículo, calculadoras legales) | ⏳ |
| 6 | Evals: golden set, métricas de retrieval, RAGAS, evals del agente | ⏳ |
| 7 | Despliegue público + UI | ⏳ |

## Levantar localmente

Requisitos: [uv](https://docs.astral.sh/uv/), Docker, claves de OpenAI (embeddings) y Anthropic (generación).

```bash
cp .env.example .env                      # y rellena OPENAI_API_KEY / ANTHROPIC_API_KEY
uv sync                                   # dependencias
docker compose -p lexlaboral up -d        # Postgres 16 + pgvector (puerto 5434)
uv run alembic upgrade head               # esquema
uv run python -m app.ingestion.parser     # XML oficial -> data/processed/articulos.json
uv run python scripts/ingest.py           # chunks + embeddings -> pgvector (~US$0,005)
uv run uvicorn app.main:app --reload      # API en http://localhost:8000/docs
uv run pytest -q                          # tests
```

Evals: `uv run python scripts/eval_retrieval.py` (retrieval, sin costo de LLM).

## Decisiones técnicas

### Ingesta
- **Fuente XML oficial y no scraping de HTML/PDF**: la BCN publica cada norma con estructura
  explícita (`EstructuraFuncional` con `tipoParte` = Libro/Título/Capítulo/Artículo). Parsear esa
  estructura es exacto; extraer de un PDF perdería la jerarquía y mezclaría columnas.
- **Limpieza de la columna de notas al margen**: el texto oficial trae a la derecha referencias
  de modificación ("L. 18.620 / ART. PRIMERO"). Son ruido semántico para los embeddings y la
  búsqueda léxica, así que se eliminan del texto indexado (ver `app/ingestion/parser.py` y sus
  tests).
- **Ids estables por artículo** (`art-67`, `art-40-bis-a`, `art-t-1` para transitorios): la
  unidad de citación del sistema es el artículo, igual que en la práctica jurídica.

### Fase 1 — CAG (baseline)
- **El Código completo cabe en el contexto, pero solo en modelos de 1M tokens**: mide ~258k
  tokens en `claude-opus-5` (193k en Haiku 4.5, cuyo contexto de 200k no deja espacio útil).
- **Prompt caching**: instrucciones + Código son un prefijo estable con `cache_control`; la
  pregunta va después del breakpoint para no invalidarlo.
- **Lo que enseñó la primera ejecución real** ([evals/cag_sample_output.md](evals/cag_sample_output.md)):
  calidad excelente (6/6 citas verificadas), pero ~US$3,7 por la primera pregunta. El contexto
  medía 367k tokens porque la ruta jerárquica se repetía en cada artículo (ahora se escribe una
  vez por sección) y el TTL de 1h cobra 2× la escritura (ahora TTL de 5 min, 1,25×). Aun
  optimizado, cada consulta sin caché paga ~260k tokens: **CAG queda como referencia de calidad,
  no como arquitectura de producción.**

### Fase 2 — RAG: chunking, embeddings, pgvector
- **Chunk = artículo** (la unidad de sentido y de citación de una ley), sin tamaño fijo ni
  overlap. Los 106 artículos de más de 400 tokens se dividen **por incisos completos**, porque el
  reranker solo lee ~512 tokens del par pregunta–chunk. Resultado: 822 chunks de 733 artículos.
- **Enriquecimiento contextual**: se embebe `ruta jerárquica + texto`. El art. 67 no dice
  "vacaciones", pero su capítulo se llama "Del feriado anual y de los permisos".
- **Small-to-big**: se busca por chunks, pero al LLM se le entrega el artículo completo.
- `text-embedding-3-small` (1536 dim, igual que en el curso), índice **HNSW** coseno, y
  `tsvector` en español generado por Postgres para la rama léxica. Embeber todo el corpus
  cuesta ~US$0,005.

### Fase 3 — Recuperación: lo que midieron los evals
Golden set: [evals/golden_set.json](evals/golden_set.json), 37 preguntas en lenguaje coloquial
(34 dentro del alcance + 3 fuera), anotadas a mano con los artículos que las responden, cada
anotación verificada contra el texto. Métricas a nivel de artículo: hit@5, recall@5, MRR@5.

- **La búsqueda híbrida, que ayudó en el estimador, aquí empeoró la recuperación** (hit@5 0,94 →
  0,65). Diagnóstico: la rama léxica sola acierta solo el 26% porque las personas preguntan con
  palabras que el Código no usa ("vacaciones"/feriado, "me echaron"/despido, "papá"/padre), y
  términos ubicuos ("trabajo", "días") dominaban el ranking.
- **Arreglo genérico, no ajustado a preguntas concretas**: filtro IDF (se descartan lexemas
  presentes en >15% de los chunks) y RRF ponderado. La rama léxica sube de 26% a 44%, pero la
  híbrida sigue sin superar a la vectorial con preguntas coloquiales.
- Resultados completos: [evals/results/retrieval.md](evals/results/retrieval.md).

## Limitaciones conocidas y próximos pasos

_(se completa al cierre del proyecto)_

## ⚠️ Aviso

LexLaboral es un proyecto académico. Sus respuestas son orientativas y no reemplazan la
asesoría de un abogado ni de la Dirección del Trabajo.
