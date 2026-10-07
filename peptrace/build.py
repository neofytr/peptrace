# this file turns the parsed peps into the graph; lexicon.py has what to look for, and
# this file decides what becomes a node and what becomes an edge

import math
import re
from collections import Counter, defaultdict
from datetime import date

from . import lexicon
from .graph import Graph
from .parse import load_dir, pep_refs, plain, strip_code_blocks

MIN_IDEA_WORDS = 20       # lmao anything shorter is a heading or a throwaway line, not an actual idea
MAX_CONCEPTS = 8          # per pep. past 8 it's just stuff the pep mentions in passing
MIN_CONCEPT_HITS = 3
BULLET = r"^(-|\*|\d+\.|#\.)\s+"


def slug(name):
    return re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_")


def pep_id(number):
    return f"pep:{number}"


def first_sentence(text, limit=90):
    text = " ".join(text.split())
    m = re.match(r"(.{15,}?[.:;!?])(\s|$)", text)   # 15+ chars so "e.g." doesn't end it
    sentence = m.group(1) if m else text
    if len(sentence) > limit:
        sentence = sentence[:limit].rsplit(" ", 1)[0] + "..."
    return sentence


def split_blocks(body):
    # this is for rejected sections that have no subsections; one idea per bullet,
    # or one per paragraph if there are no bullets
    lines = strip_code_blocks(body).splitlines()
    bullet_starts = [i for i, line in enumerate(lines) if re.match(BULLET + r"\S", line)]

    blocks = []
    if len(bullet_starts) >= 2:
        bullet_starts.append(len(lines))
        for start, end in zip(bullet_starts, bullet_starts[1:]):
            # this keeps the indented lines that continue the bullet and stops at the next normal paragraph
            kept = [lines[start]]
            for line in lines[start + 1:end]:
                if line.strip() and not line[0].isspace():
                    break
                kept.append(line)
            blocks.append(" ".join(x.strip() for x in kept))
    else:
        for para in re.split(r"\n\s*\n", "\n".join(lines)):
            blocks.append(" ".join(x.strip() for x in para.splitlines()))

    ideas = []
    for block in blocks:
        block = re.sub(BULLET, "", block).strip()
        if len(block.split()) >= MIN_IDEA_WORDS:
            ideas.append(block)
    return ideas


def rejected_ideas(pep):
    # every rejected idea in the pep as (title, text)
    ideas = []
    for sec in pep.sections:
        if sec.level != 0 or sec.kind != "rejected":
            continue
        subsections = [s for s in pep.children(sec.index) if s.level == 1]
        if subsections:
            # the intro text above the subsections is usually just framing, skip it.
            # pep 677's intro for example is a list of requirements, not alternatives
            for s in subsections:
                text = plain(strip_code_blocks(pep.full_body(s.index)))
                if len(text.split()) >= MIN_IDEA_WORDS:
                    title = re.sub(r"^\d+\.\s*", "", plain(s.title)).strip(" *?")   # pep 604 numbers its headings
                    ideas.append((title, " ".join(text.split())))
        else:
            for block in split_blocks(sec.body):
                ideas.append((first_sentence(plain(block)), plain(block)))
    return ideas


def concept_hits(pep):
    hits = Counter(lexicon.match_concepts(pep.text))
    # if the title or abstract names a concept, that's what the pep is actually about,
    # so those hits get counted 4 more times on top of the normal count
    for name, n in lexicon.match_concepts(pep.title + "\n" + pep.abstract()).items():
        hits[name] += 4 * n
    return hits


def build(peps_dir, source_note=""):
    peps = load_dir(peps_dir)
    known = {p.number for p in peps}

    g = Graph()
    g.meta = {
        "built": date.today().isoformat(),
        "source": source_note,
        "peps": len(peps),
        "schema": {
            "nodes": ["pep", "person", "concept", "feature", "alternative", "reason"],
            "edges": ["authored", "sponsored", "requires", "replaces", "superseded_by", "references",
                      "about", "introduces", "uses", "rejected", "because", "concerns", "mentions"],
        },
    }

    for name, c in lexicon.CONCEPTS.items():
        g.add_node(f"concept:{name}", "concept", name=name, desc=c["desc"])
    for name, r in lexicon.REASONS.items():
        g.add_node(f"reason:{name}", "reason", name=name, desc=r["desc"])
    for name, (introduced_by, _) in lexicon.FEATURES.items():
        g.add_node(f"feature:{name}", "feature", name=name, introduced_by=introduced_by)

    # first pass: pep nodes and people. all peps have to exist before we can link them to each other
    for p in peps:
        res = p.resolution()
        g.add_node(pep_id(p.number), "pep",
                   number=p.number,
                   title=p.title,
                   status=p.status,
                   kind=p.headers.get("type", ""),
                   created=p.headers.get("created", ""),
                   python_version=p.headers.get("python-version", ""),
                   resolution=res.get("url", ""),
                   resolved=res.get("date", ""),
                   discussion=p.headers.get("discussions-to", ""),
                   abstract=" ".join(p.abstract().split())[:600],
                   sections=[s.title for s in p.sections if s.level == 0])
        for name in p.authors:
            g.add_node(f"person:{slug(name)}", "person", name=name)
            g.add_edge(pep_id(p.number), f"person:{slug(name)}", "authored")
        for name in p.sponsors:
            g.add_node(f"person:{slug(name)}", "person", name=name)
            g.add_edge(pep_id(p.number), f"person:{slug(name)}", "sponsored")

    # these three come straight from the headers so they're the only edges we're 100% sure of
    for p in peps:
        for n in p.header_peps("requires"):
            if n in known:
                g.add_edge(pep_id(p.number), pep_id(n), "requires")
        for n in p.header_peps("replaces"):
            if n in known:
                g.add_edge(pep_id(p.number), pep_id(n), "replaces")
        for n in p.header_peps("superseded-by"):
            if n in known:
                g.add_edge(pep_id(p.number), pep_id(n), "superseded_by")

    # second pass: everything we read out of the body text
    hits_by_pep = {p.number: concept_hits(p) for p in peps}
    peps_with = Counter()   # concept -> how many peps mention it at all
    for hits in hits_by_pep.values():
        peps_with.update(hits.keys())

    for p in peps:
        me = pep_id(p.number)

        # tf-idf, otherwise "subtyping" (in basically every pep) beats "buffers" (in one)
        hits = hits_by_pep[p.number]
        salience = {}
        for name, n in hits.items():
            if n >= MIN_CONCEPT_HITS:
                salience[name] = n * math.log(1 + len(peps) / peps_with[name])
        top = sorted(salience.items(), key=lambda kv: -kv[1])[:MAX_CONCEPTS]
        for name, s in top:
            g.add_edge(me, f"concept:{name}", "about", hits=hits[name], salience=round(s, 2))

        # pep -> pep references, remembering which kind of section each one sits in.
        # a reference from "rejected ideas" means something very different from one in the spec
        where = defaultdict(Counter)
        for s in p.sections:
            for n in pep_refs(s.body):
                if n in known and n != p.number:
                    where[n][s.kind] += 1
        for n, kinds in where.items():
            g.add_edge(me, pep_id(n), "references", count=sum(kinds.values()), sections=dict(kinds))

        # only one pep introduced TypeGuard, everyone else just uses it
        for name, n in lexicon.match_features(p.text).items():
            introduced_by = lexicon.FEATURES[name][0]
            if introduced_by == p.number:
                g.add_edge(me, f"feature:{name}", "introduces")
            elif n >= 2 and introduced_by in known:
                g.add_edge(me, f"feature:{name}", "uses", hits=n)

        for i, (title, text) in enumerate(rejected_ideas(p), 1):
            idea = f"alt:{p.number}-{i}"
            g.add_node(idea, "alternative", pep=p.number, title=title, text=text[:1500])
            g.add_edge(me, idea, "rejected")
            for name, n in lexicon.match_reasons(text).items():
                g.add_edge(idea, f"reason:{name}", "because", hits=n)
            for name, n in lexicon.match_concepts(title + "\n" + text).items():
                g.add_edge(idea, f"concept:{name}", "concerns", hits=n)
            for name in lexicon.match_features(text):
                g.add_edge(idea, f"feature:{name}", "mentions")
            # text went through plain() already so :pep:`484` is "PEP 484" by now
            for n in {int(x) for x in re.findall(r"\bPEP (\d+)", text)}:
                if n in known and n != p.number:
                    g.add_edge(idea, pep_id(n), "references")
    return g
