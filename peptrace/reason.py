# you give it a proposal as plain text, it tells you what the graph already knows about it.
#
# i haven't any model or embeddings to do this; the input goes through the same lexicon the graph was built
# with, gets scored against every pep and every rejected idea, and then we walk the graph
# out from the best hits to collect lineage, people and the objections that keep coming up

# every score carries a list of what produced it, so you can always check its work

import math
import re
from collections import Counter, defaultdict

from . import lexicon

TOP_PEPS = 6
TOP_IDEAS = 6
INPUT_CAP = 3          # so that unnecessary repetition is not there
WORD_IDF_FLOOR = 1.5   # words that show up in more than ~1/4 of the ideas end up worth 0
STRONG_IDEA = 4.0      # what an idea has to score by itself before we say "considered before"
STRONG_PEP = 2.0
CONTEXT_BONUS = [1.5, 1.0, 0.5]   # extra for ideas that live inside the top 3 peps
# all of the numbers above were tuned by hand against examples/ lmao so they are nothing fancy

OPEN = {"Draft", "Deferred", "Accepted"}
DEAD = {"Rejected", "Withdrawn", "Superseded"}


def name_of(node_id):
    # "concept:narrowing" -> "narrowing", "pep:647" -> "647"
    return node_id.split(":", 1)[1]


def profile(text):
    return {
        "concepts": lexicon.match_concepts(text),
        "features": lexicon.match_features(text),
        "peps_named": sorted({int(n) for n in re.findall(r"\bPEP[ -]?(\d+)", text, re.I)}),
        "tokens": lexicon.tokens(text),
    }


class Reasoner:
    def __init__(self, g):
        self.g = g
        self.peps = {}   # pep number -> node id
        for node_id, node in g.of_type("pep"):
            self.peps[int(node["number"])] = node_id

        # same idf as build.py uses, rarer concepts are worth more
        peps_with = Counter(e["dst"] for e in g.edges if e["type"] == "about")
        self.concept_idf = {}
        for concept, n in peps_with.items():
            self.concept_idf[name_of(concept)] = math.log(1 + len(self.peps) / n)

        # each pep's concepts scaled so its strongest one is 1.0, otherwise the long peps win everything
        self.pep_concepts = {}
        self.pep_features = {}
        for num, node_id in self.peps.items():
            about = {name_of(e["dst"]): e["salience"] for e in g.out(node_id, "about")}
            strongest = max(about.values(), default=1.0)
            self.pep_concepts[num] = {c: s / strongest for c, s in about.items()}
            self.pep_features[num] = {name_of(e["dst"]) for e in g.out(node_id)
                                      if e["type"] in ("uses", "introduces")}

        self.idea_words = {}   # idea id -> (words in its title, words in its text)
        ideas_with = Counter()
        for idea_id, idea in g.of_type("alternative"):
            title_words = lexicon.tokens(idea["title"])
            text_words = lexicon.tokens(idea["text"])
            self.idea_words[idea_id] = (title_words, text_words)
            ideas_with.update(title_words | text_words)

        self.word_idf = {}
        for word, n in ideas_with.items():
            self.word_idf[word] = max(math.log(1 + len(self.idea_words) / n) - WORD_IDF_FLOOR, 0.0)

        # if most of a pep's rejected ideas share a word, that word is the pep's topic and
        # doesn't help tell its ideas apart; every idea in pep 647 says "narrowing" for example.
        # so for each pep count how many of its ideas share each word / concept
        self.siblings = defaultdict(Counter)
        for idea_id, idea in g.of_type("alternative"):
            title_words, text_words = self.idea_words[idea_id]
            self.siblings[idea["pep"]].update(title_words | text_words)
            self.siblings[idea["pep"]].update(name_of(e["dst"]) for e in g.out(idea_id, "concerns"))

    def score_peps(self, prof):
        results = []
        for num, node_id in self.peps.items():
            node = self.g.nodes[node_id]
            score = 0.0
            why = []   # (points, reason) so we can show the biggest reasons first

            for concept, n in prof["concepts"].items():
                weight = self.pep_concepts[num].get(concept)
                if weight:
                    points = min(n, INPUT_CAP) * weight * self.concept_idf.get(concept, 1.0)
                    score += points
                    why.append((points, concept))

            for feature in prof["features"]:
                if lexicon.FEATURES[feature][0] == num:
                    score += 3.0
                    why.append((3.0, f"introduces {feature}"))
                elif feature in self.pep_features[num]:
                    score += 0.5
                    why.append((0.5, f"uses {feature}"))

            if num in prof["peps_named"]:
                score += 4.0
                why.append((4.0, "named in input"))

            shared = prof["tokens"] & lexicon.tokens(node["title"] + " " + node["abstract"])
            if shared:
                points = 0.15 * min(len(shared), 8)
                score += points
                why.append((points, "words: " + ", ".join(sorted(shared)[:5])))

            if score > 0:
                why.sort(reverse=True)
                results.append({"pep": num, "score": round(score, 2), "matched": [w for _, w in why[:4]]})

        results.sort(key=lambda r: -r["score"])
        return results

    def score_ideas(self, prof, bonus=None):
        # like score_peps but every hit gets divided by how many sibling ideas in the same pep
        # share it. that way "decorator" counts inside pep 647 and "narrowing" doesn't, which is
        # what we want, the pep level score already took care of the topic
        bonus = bonus or {}
        results = []
        for idea_id, idea in self.g.of_type("alternative"):
            siblings = self.siblings[idea["pep"]]
            score = 0.0
            why = []

            concerns = {name_of(e["dst"]): e["hits"] for e in self.g.out(idea_id, "concerns")}
            shared = [c for c in prof["concepts"] if c in concerns]
            if shared:
                points = 0.5 * sum(min(prof["concepts"][c], INPUT_CAP) * min(concerns[c], 3) / 3
                                   * self.concept_idf.get(c, 1.0) / siblings[c] for c in shared)
                score += points
                why.append((points, "concepts: " + ", ".join(shared[:3])))

            mentions = {name_of(e["dst"]) for e in self.g.out(idea_id, "mentions")}
            for feature in prof["features"]:
                # an idea in the TypeGuard pep mentioning TypeGuard is not news.
                # the same name turning up in some unrelated pep's rejected ideas is
                if feature in mentions and feature not in self.pep_features[idea["pep"]]:
                    score += 1.0
                    why.append((1.0, f"mentions {feature}"))

            title_words, text_words = self.idea_words[idea_id]
            in_title = prof["tokens"] & title_words
            in_text = prof["tokens"] & text_words
            if in_title:
                # the title is the pep author's own one line summary of the idea, so it's worth a lot
                points = 1.5 * sum(self.word_idf[w] / siblings[w] for w in in_title)
                score += points
                why.append((points, "title words: " + ", ".join(sorted(in_title))))
            if in_text:
                points = min(0.15 * sum(self.word_idf[w] / siblings[w] for w in in_text), 3.0)
                score += points
                best = sorted(in_text, key=lambda w: (-self.word_idf[w], w))[:6]   # rarest first, ties alphabetical
                why.append((points, "words: " + ", ".join(best)))

            own_score = score   # the verdict only trusts this part, not the bonus below
            if idea["pep"] in bonus:
                score += bonus[idea["pep"]]
                why.append((bonus[idea["pep"]], f"inside PEP {idea['pep']}"))

            if score > 0:
                why.sort(reverse=True)
                results.append({"id": idea_id, "pep": idea["pep"], "score": round(score, 2),
                                "own_score": round(own_score, 2), "matched": [w for _, w in why[:4]]})

        results.sort(key=lambda r: -r["score"])
        return results

    def lineage(self, num):
        g = self.g
        node_id = self.peps[num]
        row = {"pep": num}

        for edge_type in ("requires", "replaces", "superseded_by"):
            targets = [int(name_of(e["dst"])) for e in g.out(node_id, edge_type)]
            if targets:
                row[edge_type] = targets
        # and the same three edges looking backwards
        for edge_type, label in (("requires", "required_by"), ("replaces", "replaced_by"),
                                 ("superseded_by", "supersedes")):
            sources = [int(name_of(e["src"])) for e in g.inc(node_id, edge_type)]
            if sources:
                row[label] = sources

        refs = g.inc(node_id, "references")
        cited_by = [e for e in refs if e["src"].startswith("pep:")]
        if cited_by:
            row["cited_by"] = len(cited_by)

        # being brought up inside someone's rejected ideas means this pep got weighed against something
        argued_in = set()
        for e in refs:
            if e["src"].startswith("pep:") and "rejected" in e["sections"]:
                argued_in.add(int(name_of(e["src"])))
            elif e["src"].startswith("alt:"):
                argued_in.add(g.nodes[e["src"]]["pep"])
        if argued_in:
            row["discussed_in_rejected_ideas_of"] = sorted(argued_in)
        return row

    def people(self, nums):
        people = {}
        for num in nums:
            for role in ("authored", "sponsored"):
                for e in self.g.out(self.peps[num], role):
                    name = self.g.nodes[e["dst"]]["name"]
                    if name not in people:
                        people[name] = {"name": name, "authored": [], "sponsored": []}
                    people[name][role].append(num)
        # writing a pep counts double compared to sponsoring one
        rows = sorted(people.values(), key=lambda p: -(2 * len(p["authored"]) + len(p["sponsored"])))
        return rows[:6]

    def objections(self, ideas, pep_nums):
        # why the matched ideas were rejected, plus a little weight for every reason
        # that shows up anywhere in the top peps' rejected ideas
        weight = defaultdict(float)
        examples = defaultdict(list)

        for hit in ideas:
            title = self.g.nodes[hit["id"]]["title"]
            for e in self.g.out(hit["id"], "because"):
                reason = name_of(e["dst"])
                weight[reason] += hit["score"]
                examples[reason].append(f"PEP {hit['pep']}: {title}")

        for num in pep_nums:
            for e in self.g.out(self.peps[num], "rejected"):
                label = f"PEP {num}: {self.g.nodes[e['dst']]['title']}"
                for b in self.g.out(e["dst"], "because"):
                    reason = name_of(b["dst"])
                    weight[reason] += 0.3
                    if label not in examples[reason]:
                        examples[reason].append(label)

        total = sum(weight.values()) or 1
        result = []
        for reason, w in sorted(weight.items(), key=lambda kv: -kv[1])[:6]:
            if w / total < 0.03:
                continue
            result.append({"reason": reason, "meaning": lexicon.REASONS[reason]["desc"],
                           "share": round(w / total, 2), "seen_in": examples[reason][:3]})
        return result

    def verdict(self, peps, ideas):
        # first rule that matches wins, so the order here matters
        if not peps:
            return {"label": "uncharted",
                    "why": "none of the typing PEPs are about the concepts in this input; "
                           "either it is outside the typing area or the lexicon has a gap"}

        top = peps[0]
        node = self.g.nodes[self.peps[top["pep"]]]
        status = node["status"].lower()

        # dead pep on top beats everything, even if a draft is close behind
        if node["status"] in DEAD and top["score"] >= STRONG_PEP:
            successors = [name_of(e["dst"]) for e in self.g.out(self.peps[top["pep"]], "superseded_by")]
            if successors:
                why = (f"closest match PEP {top['pep']} ({node['title']}) was superseded by "
                       f"PEP {', '.join(successors)}; the current design lives there")
            else:
                why = (f"closest match PEP {top['pep']} ({node['title']}) is {status}; "
                       f"read its resolution before proposing again")
            return {"label": "overlaps_dead_pep", "evidence": self.peps[top["pep"]], "why": why}

        # a draft that scores close to the best pep is someone already working on this
        for hit in peps[:3]:
            draft = self.g.nodes[self.peps[hit["pep"]]]
            if draft["status"] in OPEN and hit["score"] >= STRONG_PEP and hit["score"] >= 0.8 * top["score"]:
                return {"label": "in_flight", "evidence": self.peps[hit["pep"]],
                        "why": f"PEP {hit['pep']} ({draft['title']}) is {draft['status'].lower()} "
                               f"and covers the same ground; coordinate rather than compete"}

        if ideas:
            best = ideas[0]
            near = {hit["pep"] for hit in peps[:5]}
            # strong idea from one of the nearby peps, or a really strong one from anywhere
            if (best["own_score"] >= STRONG_IDEA and best["pep"] in near) or best["own_score"] >= 2 * STRONG_IDEA:
                title = self.g.nodes[best["id"]]["title"]
                reasons = [name_of(e["dst"]) for e in self.g.out(best["id"], "because")]
                why = f"PEP {best['pep']} explicitly considered and rejected '{title}'"
                if reasons:
                    why += f" citing {', '.join(reasons[:3])}"
                return {"label": "considered_before", "evidence": best["id"], "why": why}

        if top["score"] >= STRONG_PEP:
            return {"label": "extends_existing", "evidence": self.peps[top["pep"]],
                    "why": f"sits on top of PEP {top['pep']} ({node['title']}, {status}); "
                           f"its rejected ideas and resolution are the constraints to design within"}

        return {"label": "thin_prior_art",
                "why": f"weak overlap only (best is PEP {top['pep']} at {top['score']}); the idea is either "
                       f"new to the typing PEPs or phrased in words the lexicon does not know"}

    def ask(self, text, k=TOP_PEPS):
        g = self.g
        prof = profile(text)
        all_peps = self.score_peps(prof)
        peps = all_peps[:k]

        bonus = {}
        for hit, extra in zip(peps, CONTEXT_BONUS):
            bonus[hit["pep"]] = extra
        ideas = self.score_ideas(prof, bonus)[:TOP_IDEAS]
        nums = [hit["pep"] for hit in peps]

        prior_art = []
        for hit in peps:
            node = g.nodes[self.peps[hit["pep"]]]
            prior_art.append({
                "pep": hit["pep"],
                "title": node["title"],
                "status": node["status"],
                "python_version": node["python_version"],
                "score": hit["score"],
                "matched": hit["matched"],
                "introduces": [name_of(e["dst"]) for e in g.out(self.peps[hit["pep"]], "introduces")],
            })

        rejected_before = []
        for hit in ideas:
            idea = g.nodes[hit["id"]]
            excerpt = idea["text"][:300].rsplit(" ", 1)[0]
            if len(idea["text"]) > 300:
                excerpt += "..."
            rejected_before.append({
                "pep": hit["pep"],
                "pep_title": g.nodes[self.peps[hit["pep"]]]["title"],
                "idea": idea["title"],
                "score": hit["score"],
                "matched": hit["matched"],
                "because": [name_of(e["dst"]) for e in g.out(hit["id"], "because")],
                "excerpt": excerpt,
            })

        lineage = []
        for num in nums[:4]:
            row = self.lineage(num)
            if len(row) > 1:   # skip peps with nothing to say beyond their own number
                lineage.append(row)

        in_flight = []
        for hit in all_peps[:12]:
            node = g.nodes[self.peps[hit["pep"]]]
            if node["status"] in OPEN:
                in_flight.append({"pep": hit["pep"], "title": node["title"], "status": node["status"]})

        concepts = dict(sorted(prof["concepts"].items(), key=lambda kv: -kv[1]))
        return {
            "input": {"concepts": concepts, "features": list(prof["features"]), "peps_named": prof["peps_named"]},
            "verdict": self.verdict(peps, ideas),
            "prior_art": prior_art,
            "rejected_before": rejected_before,
            "likely_objections": self.objections(ideas, nums[:3]),
            "lineage": lineage,
            "in_flight": in_flight,
            "people": self.people(nums[:4]),
        }

    def show(self, num):
        # dump one pep and everything hanging off it. handy for poking around the graph
        g = self.g
        node_id = self.peps[num]
        node = g.nodes[node_id]

        rejected = []
        for e in g.out(node_id, "rejected"):
            rejected.append({"idea": g.nodes[e["dst"]]["title"],
                             "because": [name_of(b["dst"]) for b in g.out(e["dst"], "because")]})

        lineage = self.lineage(num)
        del lineage["pep"]

        return {
            "number": node["number"],
            "title": node["title"],
            "status": node["status"],
            "kind": node["kind"],
            "created": node["created"],
            "python_version": node["python_version"],
            "resolved": node["resolved"],
            "resolution": node["resolution"],
            "authors": [g.nodes[e["dst"]]["name"] for e in g.out(node_id, "authored")],
            "sponsors": [g.nodes[e["dst"]]["name"] for e in g.out(node_id, "sponsored")],
            "about": {name_of(e["dst"]): e["salience"] for e in g.out(node_id, "about")},
            "introduces": [name_of(e["dst"]) for e in g.out(node_id, "introduces")],
            "uses": [name_of(e["dst"]) for e in g.out(node_id, "uses")],
            "references": {int(name_of(e["dst"])): e["sections"] for e in g.out(node_id, "references")},
            "referenced_by": sorted(int(name_of(e["src"])) for e in g.inc(node_id, "references")
                                    if e["src"].startswith("pep:")),
            "lineage": lineage,
            "rejected_ideas": rejected,
            "abstract": node["abstract"],
        }
