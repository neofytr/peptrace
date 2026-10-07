# peptrace

tells you what the python typing peps already know about your idea

you describe a feature you want to propose, or some behaviour that makes no sense to you, and peptrace looks it up in a knowledge graph built out of the 49 typing peps. it tells you which peps are prior art, which rejected ideas you're about to propose again and why they got rejected, how the related peps replace and supersede each other, and who's been working in that area

there's no llm, no embeddings and no nlp library in here; i wrote the entities, relationships and mapping rules by hand and they all live in `peptrace/lexicon.py`. `approach.md` has the why behind all of it

## layout

```
peptrace/
  parse.py      reads a PEP .rst file: headers, sections, cross references
  lexicon.py    the schema: concepts, features and rejection reasons, all hand written
  build.py      turns parsed PEPs into graph nodes and edges
  graph.py      small property graph with json and graphml export
  reason.py     takes a new input, scores it against the graph, walks it, returns the answer
  cli.py        build / ask / show / stats / fetch
data/peps/      the 49 PEP sources tagged Topic: Typing (data/SOURCE has the commit)
knowledge/      graph.json (the knowledge state) and graph.graphml (for gephi / yEd)
examples/       inputs to try
tests/          pytest
```

## install

python 3.9 or newer, nothing else. pytest only if you want to run the tests

```
git clone https://github.com/neofytr/peptrace
cd peptrace
```

## build or regenerate the knowledge state

```
python -m peptrace build
```

this parses `data/peps/*.rst` and writes `knowledge/graph.json` and `knowledge/graph.graphml`, takes about a second. the `knowledge/` folder in the repo is the output of this exact command so you can skip this if you just want to try it out

to pull fresh pep sources from github (needs git and internet):

```
python -m peptrace fetch          # copies every PEP with "Typing" in its Topic header
python -m peptrace build
```

`data/SOURCE` has the commit of python/peps the data came from

## ask it something

```
python -m peptrace ask "add a Const qualifier so a module level variable cannot be reassigned"
python -m peptrace ask -f examples/intersection_types.txt
python -m peptrace ask --json -f examples/callable_syntax.txt     # same thing as json
python -m peptrace show 563                                        # one PEP and everything attached to it
python -m peptrace stats
```

every file in `examples/` is a proposal or a question. this is what `python -m peptrace ask -f examples/decorator_typeguard.txt` prints (cut down a bit):

```
verdict: EXTENDS_EXISTING
  sits on top of PEP 647 (User-Defined Type Guards, final); its rejected ideas and resolution are the constraints to design within

read as: narrowing(2), decorators(1)
names:   TypeGuard

prior art
  PEP 647  Final       6.76  User-Defined Type Guards
           via narrowing, introduces TypeGuard, words: narrowing, decorators  (gave us TypeGuard)
  PEP 742  Final       4.35  Narrowing types with TypeIs
           via narrowing, uses TypeGuard, words: narrowing, typeguard  (gave us TypeIs)
  PEP 724  Withdrawn    4.2  Stricter Type Guards
           via narrowing, uses TypeGuard, words: typeguard
  ...

already considered and rejected
  PEP 647 > Decorator Syntax [runtime_cost]
      The use of a decorator was considered for defining type guards. The decorator approach is
      inferior because it requires runtime evaluation of the type, precluding forward references...
  PEP 724 > TypeGuard with a second output type [complexity]
      ...

objections you will likely face
  complexity                44%  too hard to understand, teach or specify
      e.g. PEP 724: TypeGuard with a second output type; PEP 647: Conditionally Applying TypeGuard Type
  runtime_cost              30%  import time, memory or call overhead
      e.g. PEP 647: Decorator Syntax
  inconsistency             18%  doesn't fit how the rest of python or other languages do it

lineage
  PEP 647: cited_by 3, discussed_in_rejected_ideas_of [742]
  PEP 742: replaces [724]
  PEP 724: replaced_by [742], cited_by 1, discussed_in_rejected_ideas_of [742]

people who have shaped this area
  Jelle Zijlstra               authored 742, 800; sponsored 724
  Eric Traut                   authored 647, 724
  ...
```

the verdict is one of these:

| label | meaning |
|---|---|
| `considered_before` | some pep has a rejected idea that's close to your input |
| `overlaps_dead_pep` | the closest pep got rejected, withdrawn or superseded |
| `in_flight` | a draft pep is already on the same thing |
| `extends_existing` | a final pep is what you'd be building on top of |
| `thin_prior_art` | only weak overlap |
| `uncharted` | nothing in the typing peps is about these concepts |

every score in the output lists the concepts, feature names or words that gave it, so if an answer looks off you can trace it to a rule in `lexicon.py` and an edge in `knowledge/graph.json`

## the knowledge state

`knowledge/graph.json` is just a list of nodes and edges:

```json
{"id": "pep:647", "type": "pep", "title": "User-Defined Type Guards", "status": "Final", ...}
{"id": "alt:647-1", "type": "alternative", "pep": 647, "title": "Decorator Syntax", "text": "..."}
{"src": "pep:647", "dst": "alt:647-1", "type": "rejected"}
{"src": "alt:647-1", "dst": "reason:runtime_cost", "type": "because", "hits": 1}
{"src": "pep:742", "dst": "pep:724", "type": "replaces"}
{"src": "pep:742", "dst": "pep:647", "type": "references", "count": 3, "sections": {"motivation": 2, "rejected": 1}}
```

node types are `pep`, `person`, `concept`, `feature`, `alternative` and `reason`; edge types are `authored`, `sponsored`, `requires`, `replaces`, `superseded_by`, `references`, `about`, `introduces`, `uses`, `rejected`, `because`, `concerns` and `mentions`. `meta.counts` at the top of the file has the totals, and `knowledge/graph.graphml` is the same graph if you want to open it in gephi or yEd

## tests

```
python -m pytest -q
```

## configuration

none; no env vars and no config file. the thresholds that decide the verdict are the constants at the top of `peptrace/reason.py`
