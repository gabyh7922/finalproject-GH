"""Carga de prompts versionados (`app/prompts/<nombre>/<version>.md`).

Versionar los prompts como archivos deja en git la historia de cada iteración
y permite comparar versiones con los mismos evals (ver `app/prompts/CHANGELOG.md`).
"""

from functools import lru_cache
from pathlib import Path

PROMPTS_DIR = Path(__file__).resolve().parent

CURRENT = {"legal_answer": "v1"}


@lru_cache
def load_prompt(name: str, version: str | None = None) -> str:
    version = version or CURRENT[name]
    return (PROMPTS_DIR / name / f"{version}.md").read_text(encoding="utf-8").strip()
