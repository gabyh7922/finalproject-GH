from app.generation.citations import quote_in_text, verify_citations
from app.generation.schemas import AnswerPoint, Citation, LegalAnswer

ART67 = (
    "Art. 67. Los trabajadores con más de un año de servicio tendrán derecho a un feriado anual "
    "de quince días hábiles, con remuneración íntegra."
)


def test_quote_matching_tolerates_case_spacing_and_quotes():
    assert quote_in_text("“tendrán derecho a un   FERIADO anual de quince días hábiles”", ART67)


def test_quote_with_ellipsis_requires_ordered_fragments():
    assert quote_in_text("Los trabajadores con más de un año ... quince días hábiles", ART67)
    assert not quote_in_text("quince días hábiles ... Los trabajadores", ART67)


def test_paraphrase_is_not_a_valid_quote():
    assert not quote_in_text("tienen 15 días de vacaciones", ART67)


def test_verify_citations_buckets():
    answer = LegalAnswer(
        short_answer="15 días hábiles.",
        out_of_scope=False,
        points=[
            AnswerPoint(statement="ok", grounded=True, citations=[Citation(article_id="art-67", quote="feriado anual de quince días hábiles")]),
            AnswerPoint(statement="inventado", grounded=True, citations=[Citation(article_id="art-999", quote="x")]),
            AnswerPoint(statement="parafraseo", grounded=True, citations=[Citation(article_id="art-67", quote="15 días de vacaciones")]),
            AnswerPoint(statement="sin fuente", grounded=False),
        ],
    )
    report = verify_citations(answer, {"art-67": ART67}, request_id="t")
    assert (report.verified, report.dangling, report.misquoted, report.ungrounded_points) == (1, 1, 1, 1)
    assert report.citation_precision == 1 / 3


def test_schema_rejects_grounded_point_without_citations():
    import pytest
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        AnswerPoint(statement="x", grounded=True)
