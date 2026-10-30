from src.web.graph_export import (
    build_social_graph,
    export_cytoscape,
    export_gexf,
    export_vis,
)


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
    assert "color" in alice_node
    assert "size" in alice_node


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


def test_export_cytoscape():
    results = [
        {"name": "get_followers", "result": [{"username": "alice", "id": "1"}]},
        {"name": "get_followings", "result": [{"username": "bob", "id": "2"}]},
    ]
    graph = build_social_graph(results, target="target_user")
    cyto = export_cytoscape(graph)

    assert cyto["format"] == "cytoscape"
    assert cyto["target"] == "target_user"
    assert "elements" in cyto
    assert len(cyto["elements"]["nodes"]) == 3
    assert len(cyto["elements"]["edges"]) == 2

    # Check node structure
    node = cyto["elements"]["nodes"][0]["data"]
    assert "id" in node
    assert "color" in node
    assert "category" in node

    # Check edge structure
    edge = cyto["elements"]["edges"][0]["data"]
    assert "source" in edge
    assert "target" in edge
    assert "relation" in edge


def test_export_vis():
    results = [
        {"name": "get_followers", "result": [{"username": "alice", "id": "1"}]},
        {"name": "get_people_who_commented", "result": [{"username": "carol", "count": 3}]},
    ]
    graph = build_social_graph(results, target="target_user")
    vis = export_vis(graph)

    assert vis["format"] == "vis"
    assert vis["target"] == "target_user"
    assert len(vis["nodes"]) == 3
    assert len(vis["edges"]) == 2

    node = vis["nodes"][0]
    assert "id" in node
    assert "color" in node
    assert "group" in node
    assert "size" in node

    edge = vis["edges"][0]
    assert "from" in edge
    assert "to" in edge
    assert "arrows" in edge


def test_export_vis_escapes_html():
    results = [
        {"name": "get_followers", "result": [{"username": "<script>alert(1)</script>", "id": "1"}]},
    ]
    graph = build_social_graph(results, target="test_target")
    vis = export_vis(graph)
    node = next(n for n in vis["nodes"] if "<script>" in n["id"])
    assert "&lt;script&gt;" in node["title"]
    assert "<script>" not in node["title"]


def test_build_social_graph_large_dataset():
    # Build graph with 600 nodes
    followers = [{"username": f"user_{i}", "id": str(i)} for i in range(600)]
    results = [{"name": "get_followers", "result": followers}]
    graph = build_social_graph(results, target="main_user")
    assert graph["stats"]["node_count"] == 601
    assert graph["stats"]["edge_count"] == 600
