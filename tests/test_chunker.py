from app.corpus import CorpusArticle, articles_by_id, vigentes
from app.rag.chunker import MAX_CHUNK_TOKENS, chunk_article, chunk_corpus, count_tokens


def _article(text: str) -> CorpusArticle:
    return CorpusArticle("art-99", "99", text, ("LIBRO I X", "Capítulo VII DEL FERIADO"), False, False)


def test_short_article_is_one_chunk_with_hierarchy_context():
    [chunk] = chunk_article(_article("Art. 99. Texto breve."))
    assert chunk.chunk_id == "art-99#1"
    assert chunk.content == "Art. 99. Texto breve."
    assert chunk.embed_text.startswith("Código del Trabajo › LIBRO I X › Capítulo VII DEL FERIADO")


def test_long_article_splits_on_whole_paragraphs():
    paragraph = " ".join(["palabra"] * 150)
    chunks = chunk_article(_article("\n\n".join([paragraph] * 5)), max_tokens=320)
    assert len(chunks) > 1
    assert all(c.total_parts == len(chunks) for c in chunks)
    assert chunks[1].content.startswith("Art. 99 (continuación, parte 2 de")
    # ningún inciso queda cortado por la mitad
    assert all(p.strip() == paragraph for c in chunks for p in c.content.split("\n\n") if "continuación" not in p)


def test_real_corpus_chunks_respect_limit_except_single_giant_paragraphs():
    chunks = chunk_corpus(vigentes())
    ids = [c.chunk_id for c in chunks]
    assert len(ids) == len(set(ids))
    assert {c.article_id for c in chunks} == {a.article_id for a in vigentes()}
    for c in chunks:
        if count_tokens(c.content) > MAX_CHUNK_TOKENS + 30:
            assert "\n\n" not in c.content.split("\n\n", 1)[-1], c.chunk_id  # solo un inciso gigante


def test_derogated_articles_are_not_indexed():
    derogados = [a for a in articles_by_id().values() if a.derogado]
    assert derogados and not ({a.article_id for a in derogados} & {a.article_id for a in vigentes()})
