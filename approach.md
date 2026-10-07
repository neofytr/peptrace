# approach

i picked domain A, the python typing peps, and went after the first problem in the brief; you want to propose some typing feature and you have no easy way of knowing if someone already tried it, what happened to it, or what people are going to say when you post it. the reason i went with this one is that the answer is pretty much never in one place. an idea's history is usually split between the pep that finally shipped it, some older pep that rejected an earlier version of it, and a couple of rejected ideas sections in other peps that bring it up on the side. you need the links between all of those to answer anything, so a graph made sense here

the other two situations in the brief (some behaviour looks arbitrary and you want to know why, or a team wants to understand how a feature got designed) fall out of the same graph anyway; `examples/why_future_annotations.txt` is one of those

## the data

49 peps; every file in python/peps that has `Typing` in its `Topic:` header, pinned to one commit which is written down in `data/SOURCE`. i let the pep editors pick the subset instead of picking it myself, since their tagging is what the python people already use and it means anyone can rebuild the exact same set. the files are copied into the repo so the build works offline and gives the same thing every time

i went with typing over concurrency or syntax because typing has way more rejected alternatives written down. 42 of the 49 peps have a rejected ideas / rejected alternatives / objections section, and they cite each other around 400 times. concurrency has some deeper single debates but only about a third as many peps

peps are rst files with a strict header block and that helped a lot; `Requires`, `Replaces`, `Superseded-By`, `Status` and `Resolution` are facts i can turn straight into edges without interpreting anything. so the backbone of the graph is certain and only the stuff on top of it is inferred

## entities

`pep` has the number, title, status, type, created date, target python version, resolution link and date, and the abstract. status changes how the graph treats a pep; a final one is something you design within, a rejected one means go read the resolution before trying again, a draft is someone you should talk to, and a superseded one means the current design is somewhere else

`person` is authors and sponsors. the brief asks who the right people are, and for peps the sponsor is honestly often a better answer than the author

`concept` is 40 topics a pep or an idea can be about, like generics, variance, narrowing, annotation evaluation, read-only items, intersections etc. each one has a short description and a list of regexes. i spent more time on this than on anything else; the list isn't derived from the data, i wrote it from what i know about typing and then kept fixing it while reading the output. concepts are nodes and not just tags because a new input gets mapped onto the same concept nodes the peps were mapped onto, and that shared vocabulary is the only reason something new can be compared with old decisions at all

`feature` is 40 actual names the type system has (`TypeGuard`, `ParamSpec`, `ReadOnly`, the `type` statement, `X | Y`), each tied to the pep that added it. i kept these separate from concepts for two reasons; they're identifiers so they get matched case sensitively, and ownership is a fact. exactly one pep introduced `TypeGuard` and every other pep that names it is just using it. that's where the `introduces` and `uses` edges come from, and it's a pretty strong signal when someone names a feature in their proposal

`alternative` is a rejected idea, 197 of them. each one is a subsection of a rejected ideas section, or a bullet / paragraph when the section has no subsections. it keeps the author's own title and the text explaining why it lost. imo these are the most useful nodes in the whole graph since each one is a decision with the reasoning attached, written by the person who made it

`reason` is 13 buckets for why ideas get rejected; backwards compatibility, complexity, insufficient demand, already expressible, implementation cost, runtime cost, ambiguity, readability, inconsistency, out of scope, naming, unsafe and community split. each one is a set of regexes matched against an alternative's text. i got the buckets by reading about forty rejected ideas sections and writing down the arguments that kept coming back

## relationships

these come straight from the headers so i trust them completely:

- `pep -authored-> person`, `pep -sponsored-> person`
- `pep -requires-> pep`, `pep -replaces-> pep`, `pep -superseded_by-> pep`

these are inferred from the body text with my rules:

- `pep -references-> pep`, with a count and a breakdown of which kind of section each reference sits in (motivation, rationale, rejected, spec and so on). a reference from inside a rejected ideas section means the two peps got weighed against each other, which is a different thing from a citation in the spec. i kept one edge type with the breakdown as an attribute because every more specific label i tried, i couldn't really defend
- `pep -about-> concept`, with hit counts and a salience score. hits in the title and abstract get counted 4 more times, since if a concept is named there that's what the pep is about. salience is tf-idf over the 49 peps so `subtyping` (in nearly every pep) counts for less than `buffers` (in one). each pep keeps its top 8 concepts
- `pep -introduces-> feature` and `pep -uses-> feature`
- `pep -rejected-> alternative`, `alternative -because-> reason`, `alternative -concerns-> concept`, `alternative -mentions-> feature`, `alternative -references-> pep`

stuff i left out on purpose; open issues sections (only five peps have one), the discussion threads (that's a whole other data source), the typing spec itself, and any kind of "builds on" edge. i really wanted that last one but i couldn't find a rule that got it right reliably from the text, and i'd take a missing edge over a wrong one

## how it is built

`parse.py` reads the rst without docutils; pep files are regular enough that a few rules cover all of them. a title is a line with an underline under it that's at least as long, the underline character decides the level (in the order the characters first show up), and the header block is just "Key: value" lines with indented continuation lines. every top level section gets put into one of ten kinds with a regex on its title, and subsections just take their parent's kind

`build.py` does two passes. the first one makes the pep and person nodes and the header edges, because every pep number has to exist before anything can link to it. the second does everything that comes out of the text; concepts, references by section, feature ownership and the rejected ideas

pulling out the rejected ideas took the most judgement calls. if the rejected section has subsections, each subsection is one idea and the intro text above them gets skipped since it's usually just framing (in pep 677 it's a list of requirements). if there are no subsections then bullets become ideas, and if there are no bullets either then paragraphs do. code blocks get dropped first and anything under twenty words is thrown out because it's a heading or a one liner. a paragraph style idea uses its first sentence as the title. this does lose some structure in the long sections; pep 526 gives 17 ideas and a few of those are really one idea split over a few paragraphs. i was fine with that to keep the author's own words

tradeoffs i made:

- regexes over a hand written lexicon, no statistical extraction. the brief asked for this but i'd have done it anyway for something this small; when the output is wrong i can point at the exact rule that did it. the cost is that it misses phrasings i didn't think of. the examples caught two gaps while i was building it ("lazily evaluated" and "marked optional" weren't in the lexicon) and each fix was one line
- a pattern is case sensitive only if it has a capital letter in it, so `Self` is an identifier and `self` isn't but `narrowing` matches anywhere. one rule, no per term flags
- no stemming and no synonyms other than what's in the lexicon; plain word overlap is only a secondary signal
- one json file for the knowledge state plus a graphml export. a graph database wouldn't add anything at a few hundred nodes

## what happens when a new input comes in

the input goes through the same lexicon; concept hits, feature names, any pep numbers it mentions, and its content words (with a hand written stopword list to take out the noise)

each pep gets a score from:

- concept overlap, weighted by how central that concept is to the pep and by the concept's idf
- a fixed bonus if the input names a feature the pep introduced, and a smaller one if the pep only uses it
- a bonus if the input names the pep outright
- a small bonus for words shared with the title and abstract

concept counts from the input are capped at 3, so writing "narrowing" ten times doesn't make the input ten times more about narrowing

rejected ideas get scored differently and this took me the longest to get right. my first version just counted overlap and the pep's own topic drowned out everything else; every idea in pep 647 is about narrowing, so "narrowing" in the input lit all of them up the same, and the one actually titled "Decorator Syntax" lost to longer ideas that just had more hits. i fixed it in two steps. first, every concept or word hit gets divided by how many sibling ideas in the same pep share it, so a word that most of a pep's ideas share is basically that pep's topic and counts for very little, while a word only one idea uses counts in full. second, word weights are idf over all 197 ideas with a floor, so "class" and "import" are worth nothing and "const" or "angle" are worth a lot. after that, ideas inside the top three peps get a small bonus since those are the ones you should read first

from the best hits it walks the graph to collect:

- lineage; `requires`, `replaces` and `superseded_by` in both directions for the top peps, how many peps cite each one, and which peps bring it up inside their rejected ideas
- likely objections; the `because` reasons on the matched ideas weighted by match score, plus a little weight for every reason found anywhere in the top peps' rejected ideas, all turned into shares
- in flight proposals; draft, deferred or accepted peps that scored at all
- people; authors and sponsors of the top peps, ranked

then it picks a verdict. the rules run in this order and the first one that holds wins:

1. `overlaps_dead_pep` if the top pep is rejected, withdrawn or superseded and matched strongly; if it got superseded the output names what replaced it
2. `in_flight` if a draft scores within 80% of the top pep
3. `considered_before` if the best rejected idea scores high enough on its own (the bonus doesn't count) and belongs to one of the nearby peps, or scores really high no matter where it's from; the output lists why it got rejected
4. `extends_existing` if the top pep matched strongly
5. `thin_prior_art` otherwise, or `uncharted` if nothing matched at all

the order is on purpose; a dead pep on top has to beat a draft right behind it. the callable syntax example is exactly that case, pep 677 (rejected) is on top and pep 821 (a draft about Callable) is close behind it. every item in the output also lists the concepts, names or words behind its score so you can see why it said what it said

all the thresholds were tuned by hand against the stuff in `examples/` lmao, so nothing fancy there

## what i'd build next

pull the objections from the actual discussions. rejected ideas sections are written by the pep author after everything's decided, so what you get is the author's summary of an objection and not the objection itself. the discuss.python.org threads linked from `Discussions-To` have the real arguments and who made them. with `person -objected-> alternative` edges from those threads the people section could tell you who's going to push back on you, and not just who wrote the peps. this would be the biggest improvement and most of the work is getting the data, the model already has a place to put it

put time on the edges. `references` edges have no dates right now so the graph can't tell you which way an idea moved between a 2014 pep and a 2024 one. the created dates are already on the nodes so this is mostly about using them in the lineage walk

match reasons per sentence. right now reasons get matched against an idea's whole text, so an idea that got rejected for one reason but mentions another one in passing gets both. only matching sentences near stuff like "rejected", "decided against" or "the problem with" would make the objection shares more honest

report lexicon gaps. when an input ends up as `thin_prior_art` it could print the words that matched nothing, so the lexicon grows from what people actually ask and not from me guessing

one thing i wouldn't do is swap the lexicon for an embedding model. right now when it says something weird you can trace it back to a rule and an edge, and being able to check it like that is a big part of why anyone could act on what it tells them
