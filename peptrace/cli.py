import argparse
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from .build import build
from .graph import Graph
from .reason import Reasoner

ROOT = Path(__file__).resolve().parent.parent
PEPS_DIR = ROOT / "data" / "peps"
KNOWLEDGE_DIR = ROOT / "knowledge"
PEPS_REPO = "https://github.com/python/peps"


def load_graph(path):
    path = Path(path)
    if not path.exists():
        sys.exit(f"{path} not found, run `python -m peptrace build` first")
    return Graph.from_json(path)


def cmd_fetch(args):
    # this pulls a fresh copy of python/peps and copies over the ones tagged with the topic
    tmp = tempfile.mkdtemp()
    subprocess.run(["git", "clone", "--depth", "1", "-q", PEPS_REPO, tmp], check=True)
    sha = subprocess.run(["git", "-C", tmp, "rev-parse", "HEAD"],
                         capture_output=True, text=True, check=True).stdout.strip()

    PEPS_DIR.mkdir(parents=True, exist_ok=True)
    copied = 0
    for path in sorted(Path(tmp, "peps").glob("pep-*.rst")):
        header = path.read_text(encoding="utf-8").split("\n\n", 1)[0]
        for line in header.splitlines():
            if line.startswith("Topic:") and args.topic.lower() in line.lower():
                shutil.copy(path, PEPS_DIR / path.name)
                copied += 1
                break

    (ROOT / "data" / "SOURCE").write_text(
        f"source: {PEPS_REPO}\ncommit: {sha}\nfilter: Topic header contains \"{args.topic}\"\n")
    shutil.rmtree(tmp, ignore_errors=True)
    print(f"copied {copied} peps at {sha[:10]}")


def cmd_build(args):
    source = ROOT / "data" / "SOURCE"
    note = source.read_text().strip().replace("\n", "; ") if source.exists() else ""
    g = build(args.peps, note)

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    g.to_json(out / "graph.json")
    g.to_graphml(out / "graph.graphml")
    for name, count in g.meta["counts"].items():
        print(f"{count:5d}  {name}")
    print(f"wrote {out / 'graph.json'} and graph.graphml")


def cmd_ask(args):
    text = Path(args.file).read_text() if args.file else " ".join(args.text)
    if not text.strip():
        sys.exit("give me a proposal, either as arguments or with -f file")
    result = Reasoner(load_graph(args.graph)).ask(text, k=args.k)
    if args.json:
        print(json.dumps(result, indent=2, ensure_ascii=False))
    else:
        print(render(result))


def cmd_show(args):
    reasoner = Reasoner(load_graph(args.graph))
    if args.number not in reasoner.peps:
        sys.exit(f"PEP {args.number} is not in the graph")
    print(json.dumps(reasoner.show(args.number), indent=2, ensure_ascii=False))


def cmd_stats(args):
    print(json.dumps(load_graph(args.graph).meta, indent=2))


def render(result):
    # the human readable version of the json file
    out = []
    verdict = result["verdict"]
    out.append(f"verdict: {verdict['label'].upper()}")
    out.append(f"  {verdict['why']}")

    concepts = list(result["input"]["concepts"].items())[:8]
    out.append("")
    out.append("read as: " + ", ".join(f"{c}({n})" for c, n in concepts))
    if result["input"]["features"]:
        out.append("names:   " + ", ".join(result["input"]["features"]))

    out.append("")
    out.append("prior art")
    for p in result["prior_art"]:
        gave_us = f"  (gave us {', '.join(p['introduces'])})" if p["introduces"] else ""
        out.append(f"  PEP {p['pep']:<4} {p['status']:<10} {p['score']:>5}  {p['title']}")
        out.append(f"           via {', '.join(p['matched'])}{gave_us}")

    if result["rejected_before"]:
        out.append("")
        out.append("already considered and rejected")
        for idea in result["rejected_before"]:
            reasons = f" [{', '.join(idea['because'])}]" if idea["because"] else ""
            out.append(f"  PEP {idea['pep']} > {idea['idea']}{reasons}")
            out.append(f"      {idea['excerpt']}")

    if result["likely_objections"]:
        out.append("")
        out.append("objections you will likely face")
        for o in result["likely_objections"]:
            out.append(f"  {o['reason']:<24} {int(o['share'] * 100):>3}%  {o['meaning']}")
            out.append(f"      e.g. {'; '.join(o['seen_in'][:2])}")

    if result["lineage"]:
        out.append("")
        out.append("lineage")
        for row in result["lineage"]:
            rest = ", ".join(f"{k} {v}" for k, v in row.items() if k != "pep")
            out.append(f"  PEP {row['pep']}: {rest}")

    if result["in_flight"]:
        out.append("")
        out.append("open proposals in this area")
        for p in result["in_flight"]:
            out.append(f"  PEP {p['pep']} ({p['status']}) {p['title']}")

    if result["people"]:
        out.append("")
        out.append("people who have shaped this area")
        for person in result["people"]:
            parts = []
            if person["authored"]:
                parts.append("authored " + ", ".join(str(n) for n in person["authored"]))
            if person["sponsored"]:
                parts.append("sponsored " + ", ".join(str(n) for n in person["sponsored"]))
            out.append(f"  {person['name']:<28} {'; '.join(parts)}")

    return "\n".join(out)


def main(argv=None):
    parser = argparse.ArgumentParser(prog="peptrace", description="what the typing PEPs already know about your idea")
    sub = parser.add_subparsers(dest="cmd", required=True)
    default_graph = str(KNOWLEDGE_DIR / "graph.json")

    p = sub.add_parser("fetch", help="refresh data/peps from github (needs git)")
    p.add_argument("--topic", default="Typing")
    p.set_defaults(func=cmd_fetch)

    p = sub.add_parser("build", help="parse data/peps and write knowledge/graph.json")
    p.add_argument("--peps", default=str(PEPS_DIR))
    p.add_argument("--out", default=str(KNOWLEDGE_DIR))
    p.set_defaults(func=cmd_build)

    p = sub.add_parser("ask", help="give it a proposal or a question")
    p.add_argument("text", nargs="*")
    p.add_argument("-f", "--file")
    p.add_argument("-k", type=int, default=6, help="how many peps to return")
    p.add_argument("--json", action="store_true")
    p.add_argument("--graph", default=default_graph)
    p.set_defaults(func=cmd_ask)

    p = sub.add_parser("show", help="dump one pep and everything attached to it")
    p.add_argument("number", type=int)
    p.add_argument("--graph", default=default_graph)
    p.set_defaults(func=cmd_show)

    p = sub.add_parser("stats", help="node and edge counts, plus where the data came from")
    p.add_argument("--graph", default=default_graph)
    p.set_defaults(func=cmd_stats)

    args = parser.parse_args(argv)
    args.func(args)


if __name__ == "__main__":
    main()
