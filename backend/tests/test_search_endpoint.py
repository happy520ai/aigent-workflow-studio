# tests/test_search_endpoint.py —— A9：v1 的全局检索接口移植到 perfect_main
def test_search_hits_nodes_and_operators(perfect_client):
    r = perfect_client.get("/api/v1/search", params={"q": "意图"})
    assert r.status_code == 200
    data = r.json()
    assert data["query"] == "意图"
    # 命中画布节点（意图识别智能体）
    assert any(n["id"] == "node_intent_agent" for n in data["nodes"])
    # 命中算子库（意图分析 Intent Agent）
    assert any(c["id"] == "agent_intent" for c in data["components"])
    # logs 键存在
    assert isinstance(data["logs"], list)


def test_search_requires_q(perfect_client):
    r = perfect_client.get("/api/v1/search")
    assert r.status_code == 422
