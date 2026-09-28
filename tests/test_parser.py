"""Tests del parser del Código del Trabajo (limpieza de notas al margen e ids)."""

from pathlib import Path

import pytest

from app.ingestion.parser import Article, clean_article_text, clean_heading, parse_codigo

RAW = Path("data/raw/codigo_trabajo.xml")


def test_clean_article_text_removes_margin_column():
    raw = (
        "     Art. 29. Podrá excederse la jornada ordinaria, pero en         L. 18.620\n"
        "la medida indispensable para evitar perjuicios en la marcha         ART. PRIMERO\n"
        "normal del establecimiento.\n"
        "\n"
        "     Las horas trabajadas en exceso se pagarán como\n"
        "extraordinarias."
    )
    assert clean_article_text(raw) == (
        "Art. 29. Podrá excederse la jornada ordinaria, pero en la medida indispensable "
        "para evitar perjuicios en la marcha normal del establecimiento.\n\n"
        "Las horas trabajadas en exceso se pagarán como extraordinarias."
    )


def test_clean_article_text_drops_margin_only_lines():
    raw = "     Art. 91. Texto en regalías.\n             L. 18.620\nEn ningún caso."
    assert clean_article_text(raw) == "Art. 91. Texto en regalías. En ningún caso."


def test_clean_heading_removes_inline_law_reference():
    assert (
        clean_heading("Capítulo VII                 L. 19.250  DEL FERIADO ANUAL")
        == "Capítulo VII DEL FERIADO ANUAL"
    )


@pytest.mark.parametrize(
    ("number", "transitorio", "expected"),
    [
        ("67", False, "art-67"),
        ("40 BIS A", False, "art-40-bis-a"),
        ("152 QUÁTER N", False, "art-152-quater-n"),
        ("152 QUÁTER Ñ", False, "art-152-quater-nn"),
        ("1", True, "art-t-1"),
    ],
)
def test_article_id_is_stable_and_unique(number, transitorio, expected):
    assert Article(number=number, text="", transitorio=transitorio).article_id == expected


@pytest.mark.skipif(not RAW.exists(), reason="falta data/raw/codigo_trabajo.xml")
def test_parse_real_codigo():
    meta, articles = parse_codigo(RAW)
    ids = [a.article_id for a in articles]
    assert meta["norma_id"] == "207436"
    assert len(articles) > 700
    assert len(ids) == len(set(ids)), "article_id duplicado"
    feriado = next(a for a in articles if a.article_id == "art-67")
    assert "quince días hábiles" in feriado.text
    assert feriado.path[-1] == "Capítulo VII DEL FERIADO ANUAL Y DE LOS PERMISOS"


@pytest.mark.skipif(not RAW.exists(), reason="falta data/raw/codigo_trabajo.xml")
def test_subcontracting_articles_are_not_marked_transitory():
    # Regresión: el Título VII menciona "empresas de servicios transitorios" y el
    # parser marcaba sus artículos (183-A a 183-AE) como transitorios.
    _, articles = parse_codigo(RAW)
    ids = {a.article_id for a in articles}
    assert "art-183-ae" in ids and "art-t-183-ae" not in ids
    assert "art-t-1" in ids  # los transitorios reales siguen marcados
