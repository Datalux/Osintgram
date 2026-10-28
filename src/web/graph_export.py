"""Social Network Graph exporter for Osintgram.

Constructs directed relationship graphs from OSINT scan results (followers,
following, tagged accounts, commenters, mutual connections).

Exports to:
  - GEXF (Graph Exchange XML Format) for Gephi and network analysis tools.
  - JSON (nodes and edges) for D3.js, Cytoscape, and Vis.js.
"""
import html
import json
import time
from typing import Any, Dict, List, Optional, Set, Tuple


def build_social_graph(results: List[Dict[str, Any]], target: str) -> Dict[str, Any]:
    """Build a graph of nodes and directed edges from collected Osintgram results."""
    target_clean = (target or "target").lstrip("@").lower()
    nodes: Dict[str, Dict[str, Any]] = {}
    edges: Dict[Tuple[str, str, str], Dict[str, Any]] = {}

    def add_node(username: str, label: str = "", category: str = "account", pk: Optional[str] = None):
        u = username.lstrip("@").lower().strip()
        if not u:
            return u
        if u not in nodes:
            nodes[u] = {
                "id": u,
                "label": label or u,
                "category": category,
                "pk": str(pk or ""),
                "in_degree": 0,
                "out_degree": 0,
            }
        elif category == "target":
            nodes[u]["category"] = "target"
        return u

    def add_edge(source: str, target: str, relation: str, weight: float = 1.0):
        src = source.lstrip("@").lower().strip()
        tgt = target.lstrip("@").lower().strip()
        if not src or not tgt or src == tgt:
            return
        key = (src, tgt, relation)
        if key not in edges:
            edges[key] = {
                "id": f"e_{len(edges)}",
                "source": src,
                "target": tgt,
                "relation": relation,
                "weight": weight,
            }
            if src in nodes:
                nodes[src]["out_degree"] += 1
            if tgt in nodes:
                nodes[tgt]["in_degree"] += 1
        else:
            edges[key]["weight"] += weight

    # Primary target node
    add_node(target_clean, label=f"@{target_clean}", category="target")

    for item in results:
        name = item.get("name") or ""
        res = item.get("result")
        if not res:
            continue

        # 1. Followers
        if name == "get_followers" and isinstance(res, list):
            for u in res:
                uname = u.get("username")
                if uname:
                    add_node(uname, label=u.get("full_name") or uname, category="follower", pk=u.get("id"))
                    add_edge(uname, target_clean, "follows")

        # 2. Following
        elif name == "get_followings" and isinstance(res, list):
            for u in res:
                uname = u.get("username")
                if uname:
                    add_node(uname, label=u.get("full_name") or uname, category="following", pk=u.get("id"))
                    add_edge(target_clean, uname, "follows")

        # 3. Commenters
        elif name in ("get_people_who_commented", "get_comment_data"):
            comment_items = res if isinstance(res, list) else res.get("comments", []) if isinstance(res, dict) else []
            for c in comment_items:
                uname = c.get("username") or (c.get("user") or {}).get("username")
                if uname:
                    cnt = float(c.get("count") or c.get("comments_count") or 1)
                    add_node(uname, category="commenter")
                    add_edge(uname, target_clean, "commented", weight=cnt)

        # 4. Tagged by user
        elif name == "get_people_tagged_by_user" and isinstance(res, list):
            for t in res:
                uname = t.get("username")
                if uname:
                    cnt = float(t.get("posts_count") or t.get("count") or 1)
                    add_node(uname, category="tagged_by_target")
                    add_edge(target_clean, uname, "tagged", weight=cnt)

        # 5. Who tagged user
        elif name == "get_people_who_tagged" and isinstance(res, list):
            for t in res:
                uname = t.get("username")
                if uname:
                    cnt = float(t.get("posts_count") or t.get("count") or 1)
                    add_node(uname, category="tagged_target")
                    add_edge(uname, target_clean, "tagged", weight=cnt)

        # 6. Profile comparison
        elif name == "compare_with" and isinstance(res, dict):
            other = res.get("other_user") or res.get("other_username") or "compared_target"
            add_node(other, category="compared_target")
            for mutual in res.get("common_followers", []):
                m_uname = mutual.get("username") if isinstance(mutual, dict) else str(mutual)
                if m_uname:
                    add_node(m_uname, category="mutual_connection")
                    add_edge(m_uname, target_clean, "follows")
                    add_edge(m_uname, other, "follows")
            for mutual in res.get("common_followings", []):
                m_uname = mutual.get("username") if isinstance(mutual, dict) else str(mutual)
                if m_uname:
                    add_node(m_uname, category="mutual_connection")
                    add_edge(target_clean, m_uname, "follows")
                    add_edge(other, m_uname, "follows")

    # Mark mutual follows
    for (src, tgt, rel) in list(edges.keys()):
        if rel == "follows" and (tgt, src, "follows") in edges:
            if src in nodes:
                nodes[src]["mutual_with_target"] = True
            if tgt in nodes:
                nodes[tgt]["mutual_with_target"] = True

    return {
        "target": target_clean,
        "nodes": list(nodes.values()),
        "edges": list(edges.values()),
        "stats": {
            "node_count": len(nodes),
            "edge_count": len(edges),
        },
    }


def export_gexf(graph: Dict[str, Any]) -> str:
    """Serialize the social network graph into standard GEXF 1.2 XML format for Gephi."""
    date_str = time.strftime("%Y-%m-%d")
    target = html.escape(graph.get("target", "osintgram"))

    xml = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        '<gexf xmlns="http://www.gexf.net/1.2draft" version="1.2">',
        f'  <meta lastmodifieddate="{date_str}">',
        '    <creator>Osintgram 2.0</creator>',
        f'    <description>Social Network Graph for @{target}</description>',
        '  </meta>',
        '  <graph defaultedgetype="directed" mode="static">',
        '    <attributes class="node">',
        '      <attribute id="0" title="category" type="string"/>',
        '      <attribute id="1" title="in_degree" type="integer"/>',
        '      <attribute id="2" title="out_degree" type="integer"/>',
        '      <attribute id="3" title="mutual_with_target" type="boolean"/>',
        '    </attributes>',
        '    <attributes class="edge">',
        '      <attribute id="0" title="relation" type="string"/>',
        '    </attributes>',
        '    <nodes>',
    ]

    # Gephi colors (r, g, b):
    category_colors = {
        "target": (236, 72, 153),           # Pink accent
        "follower": (91, 82, 240),          # Indigo
        "following": (59, 130, 246),        # Blue
        "commenter": (245, 158, 11),        # Amber
        "tagged_by_target": (16, 185, 129), # Emerald
        "tagged_target": (139, 92, 246),    # Purple
        "mutual_connection": (239, 68, 68), # Red
        "compared_target": (249, 115, 22),  # Orange
    }

    for n in graph.get("nodes", []):
        nid = html.escape(str(n["id"]))
        nlabel = html.escape(str(n.get("label") or nid))
        cat = str(n.get("category", "account"))
        in_d = int(n.get("in_degree", 0))
        out_d = int(n.get("out_degree", 0))
        mutual = "true" if n.get("mutual_with_target") else "false"
        r, g, b = category_colors.get(cat, (120, 120, 120))

        xml.append(f'      <node id="{nid}" label="{nlabel}">')
        xml.append('        <attvalues>')
        xml.append(f'          <attvalue for="0" value="{html.escape(cat)}"/>')
        xml.append(f'          <attvalue for="1" value="{in_d}"/>')
        xml.append(f'          <attvalue for="2" value="{out_d}"/>')
        xml.append(f'          <attvalue for="3" value="{mutual}"/>')
        xml.append('        </attvalues>')
        xml.append(f'        <viz:color xmlns:viz="http://www.gexf.net/1.2draft/viz" r="{r}" g="{g}" b="{b}"/>')
        xml.append('      </node>')

    xml.append('    </nodes>')
    xml.append('    <edges>')

    for e in graph.get("edges", []):
        eid = html.escape(str(e["id"]))
        src = html.escape(str(e["source"]))
        tgt = html.escape(str(e["target"]))
        rel = html.escape(str(e.get("relation", "relates")))
        weight = float(e.get("weight", 1.0))

        xml.append(f'      <edge id="{eid}" source="{src}" target="{tgt}" weight="{weight}">')
        xml.append('        <attvalues>')
        xml.append(f'          <attvalue for="0" value="{rel}"/>')
        xml.append('        </attvalues>')
        xml.append('      </edge>')

    xml.append('    </edges>')
    xml.append('  </graph>')
    xml.append('</gexf>')

    return '\n'.join(xml)
