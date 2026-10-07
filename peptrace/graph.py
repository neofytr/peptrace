# a tiny property graph; didnt use graphx since i didnt think it would be needed
# for this small scale

import json
from collections import defaultdict
from xml.sax.saxutils import escape


class Graph:
    def __init__(self):
        self.nodes = {}     # id -> {"type": ..., anything else}
        self.edges = []     # {"src": id, "dst": id, "type": ..., anything else}
        self.meta = {}
        self._out = defaultdict(list)
        self._in = defaultdict(list)

    def add_node(self, node_id, node_type, **attrs):
        if node_id in self.nodes:
            self.nodes[node_id].update(attrs)
        else:
            self.nodes[node_id] = {"type": node_type, **attrs}

    def add_edge(self, src, dst, edge_type, **attrs):
        assert src in self.nodes and dst in self.nodes, (src, dst)
        edge = {"src": src, "dst": dst, "type": edge_type, **attrs}
        self.edges.append(edge)
        self._out[src].append(edge)
        self._in[dst].append(edge)

    def out(self, node_id, edge_type=None):
        return [e for e in self._out[node_id] if edge_type is None or e["type"] == edge_type]

    def inc(self, node_id, edge_type=None):
        return [e for e in self._in[node_id] if edge_type is None or e["type"] == edge_type]

    def of_type(self, node_type):
        return [(k, v) for k, v in self.nodes.items() if v["type"] == node_type]

    def to_json(self, path):
        counts = defaultdict(int)
        for node in self.nodes.values():
            counts["nodes." + node["type"]] += 1
        for edge in self.edges:
            counts["edges." + edge["type"]] += 1
        self.meta["counts"] = dict(sorted(counts.items()))

        doc = {
            "meta": self.meta,
            "nodes": [{"id": k, **v} for k, v in self.nodes.items()],
            "edges": self.edges,
        }
        with open(path, "w") as f:
            json.dump(doc, f, indent=1, ensure_ascii=False)

    @classmethod
    def from_json(cls, path):
        with open(path) as f:
            doc = json.load(f)
        g = cls()
        g.meta = doc.get("meta", {})
        for node in doc["nodes"]:
            node = dict(node)
            g.add_node(node.pop("id"), node.pop("type"), **node)
        for edge in doc["edges"]:
            edge = dict(edge)
            g.add_edge(edge.pop("src"), edge.pop("dst"), edge.pop("type"), **edge)
        return g

    def to_graphml(self, path):
        def as_text(v):
            if isinstance(v, list):
                return ", ".join(str(x) for x in v)
            if isinstance(v, dict):
                return json.dumps(v, ensure_ascii=False)
            return str(v)

        node_keys = sorted({k for node in self.nodes.values() for k in node})
        edge_keys = sorted({k for edge in self.edges for k in edge if k not in ("src", "dst")})

        lines = ['<?xml version="1.0" encoding="UTF-8"?>',
                 '<graphml xmlns="http://graphml.graphdrawing.org/xmlns">']
        for k in node_keys:
            lines.append(f'  <key id="n_{k}" for="node" attr.name="{k}" attr.type="string"/>')
        for k in edge_keys:
            lines.append(f'  <key id="e_{k}" for="edge" attr.name="{k}" attr.type="string"/>')
        lines.append('  <graph id="peps" edgedefault="directed">')

        for node_id, attrs in self.nodes.items():
            lines.append(f'    <node id="{escape(node_id)}">')
            for k, v in attrs.items():
                lines.append(f'      <data key="n_{k}">{escape(as_text(v))}</data>')
            lines.append("    </node>")

        for i, edge in enumerate(self.edges):
            lines.append(f'    <edge id="e{i}" source="{escape(edge["src"])}" target="{escape(edge["dst"])}">')
            for k, v in edge.items():
                if k not in ("src", "dst"):
                    lines.append(f'      <data key="e_{k}">{escape(as_text(v))}</data>')
            lines.append("    </edge>")

        lines.append("  </graph>")
        lines.append("</graphml>")
        with open(path, "w") as f:
            f.write("\n".join(lines))
