"""Esquema de respuesta con citas por afirmación (heredero de la Sesión 11 del curso).

En el estimador cada línea del presupuesto citaba chunk_ids. Aquí la unidad de
citación es el **artículo** del Código, y además cada cita trae la **frase
textual** del artículo que respalda la afirmación. Eso permite una verificación
más fuerte que "el id existe": la frase tiene que aparecer literalmente en el
artículo citado (ver `app/generation/citations.py`).

El validador impide representar una afirmación "respaldada" sin citas, o una
"no respaldada" que igual cite algo: una afirmación legal sin fuente es
exactamente el fallo que este esquema quiere hacer imposible.
"""

from __future__ import annotations

from pydantic import BaseModel, Field, model_validator


class Citation(BaseModel):
    article_id: str = Field(description="Id del artículo citado, copiado tal cual del contexto (p.ej. 'art-67').")
    quote: str = Field(description="Fragmento TEXTUAL del artículo que respalda la afirmación (copiado, no parafraseado).")


class AnswerPoint(BaseModel):
    statement: str = Field(description="Una afirmación concreta, en lenguaje simple.")
    grounded: bool = Field(description="True solo si al menos un artículo del contexto la respalda.")
    citations: list[Citation] = Field(default_factory=list)

    @model_validator(mode="after")
    def _grounding_integrity(self) -> "AnswerPoint":
        if self.grounded and not self.citations:
            raise ValueError("grounded=True requiere al menos una cita")
        if not self.grounded and self.citations:
            raise ValueError("grounded=False no puede llevar citas")
        return self


class LegalAnswer(BaseModel):
    short_answer: str = Field(description="Respuesta directa en 1-3 frases, en lenguaje simple.")
    points: list[AnswerPoint] = Field(description="Desarrollo en afirmaciones, cada una con sus citas.")
    out_of_scope: bool = Field(
        description="True si la pregunta no la resuelve el Código del Trabajo (otra ley, un caso que requiere abogado, o no es laboral)."
    )


class CitationCheck(BaseModel):
    article_id: str
    status: str  # "verified" | "dangling" | "misquoted"


class CitationReport(BaseModel):
    """Resultado de verificar cada cita contra el contexto que realmente vio el modelo.

    - verified:  el artículo estaba en el contexto y la frase aparece en él.
    - dangling:  cita un artículo que nunca estuvo en el contexto (inventado o fuera del retrieval).
    - misquoted: el artículo sí estaba, pero la "frase textual" no aparece en él (parafraseo o invento).
    """

    checks: list[CitationCheck]
    ungrounded_points: int

    @property
    def verified(self) -> int:
        return sum(c.status == "verified" for c in self.checks)

    @property
    def dangling(self) -> int:
        return sum(c.status == "dangling" for c in self.checks)

    @property
    def misquoted(self) -> int:
        return sum(c.status == "misquoted" for c in self.checks)

    @property
    def citation_precision(self) -> float:
        """Fracción de citas totalmente verificadas (1.0 si no hubo citas)."""
        return self.verified / len(self.checks) if self.checks else 1.0
