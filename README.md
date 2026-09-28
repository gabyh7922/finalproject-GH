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
| 1 | CAG: baseline con el Código en el contexto (prompt caching) | ⏳ |
| 2 | RAG: chunking por artículo + embeddings + pgvector | ⏳ |
| 3 | Recuperación híbrida (vector + full-text español) con RRF + reranking | ⏳ |
| 4 | Generación con citas por artículo + verificación de citas | ⏳ |
| 5 | Agente con herramientas (búsqueda, lectura de artículo, calculadoras legales) | ⏳ |
| 6 | Evals: golden set, métricas de retrieval, RAGAS, evals del agente | ⏳ |
| 7 | Despliegue público + UI | ⏳ |

## Levantar localmente

```bash
uv sync                                   # dependencias
uv run python scripts/download_data.py    # (opcional) re-descargar el XML oficial
uv run python -m app.ingestion.parser     # XML -> data/processed/articulos.json
uv run pytest -q                          # tests
```

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

## Limitaciones conocidas y próximos pasos

_(se completa al cierre del proyecto)_

## ⚠️ Aviso

LexLaboral es un proyecto académico. Sus respuestas son orientativas y no reemplazan la
asesoría de un abogado ni de la Dirección del Trabajo.
