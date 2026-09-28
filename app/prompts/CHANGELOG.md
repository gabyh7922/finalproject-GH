# Historial de prompts

Cada versión queda como archivo propio; `loader.CURRENT` indica la activa. Los
cambios se justifican con resultados de evals (`evals/`).

## legal_answer

### v1 — versión inicial
- Rol y audiencia explícitos (personas sin formación jurídica → lenguaje simple).
- Se explica *por qué* no usar conocimiento propio (la ley cambia; el contexto es la versión vigente) en vez de solo prohibirlo.
- Citas con `article_id` + fragmento textual, avisando que se verifican automáticamente.
- Criterio explícito de `out_of_scope` con ejemplos de leyes vecinas (AFP, Isapre, impuestos).
