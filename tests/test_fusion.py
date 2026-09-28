from app.rag.fusion import reciprocal_rank_fusion


def test_rrf_rewards_consensus_between_branches():
    vector = ["a", "b", "c"]
    lexical = ["c", "d", "a"]
    fused = reciprocal_rank_fusion([vector, lexical], k=60)
    assert fused[0] in {"a", "c"}  # aparecen en ambas ramas
    assert set(fused) == {"a", "b", "c", "d"}
    assert fused.index("b") > fused.index("c")
