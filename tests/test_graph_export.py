from src.web.graph_export import build_social_graph, export_gexf


def test_build_social_graph():
    results = [
        {"name": "get_followers", "result": [{"username": "alice", "id": "1"}, {"username": "bob", "id": "2"}]},
        {"name": "get_followings", "result": [{"username": "alice", "id": "1"}, {"username": "charlie", "id": "3"}]},
        {"name": "get_people_who_commented", "result": [{"username": "dave", "count": 5}]},
    ]
    graph = build_social_graph(results, target="target_user")

    assert graph["target"] == "target_user"
    assert graph["stats"]["node_count"] == 5  # target, alice, bob, charlie, dave
    assert graph["stats"]["edge_count"] == 5  # alice->target, bob->target, target->alice, target->charlie, dave->target

    # Alice is mutual
    alice_node = next(n for n in graph["nodes"] if n["id"] == "alice")
    assert alice_node.get("mutual_with_target") is True


def test_export_gexf():
    results = [
        {"name": "get_followers", "result": [{"username": "alice", "id": "1"}]},
    ]
    graph = build_social_graph(results, target="target_user")
    gexf_xml = export_gexf(graph)

    assert "<?xml version=" in gexf_xml
    assert "<gexf" in gexf_xml
    assert 'label="@target_user"' in gexf_xml
    assert 'source="alice" target="target_user"' in gexf_xml
