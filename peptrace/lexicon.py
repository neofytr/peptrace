# this file is basically the whole schema. if the graph knows something about typing,
# it's because there's a regex for it in here
#
# CONCEPTS  what a pep or a rejected idea is about (generics, narrowing, ...)
# FEATURES  actual names you can import or write, plus the pep that added each one
# REASONS   why ideas get shot down. matched against the rejected ideas text
#
# if a pattern has a capital letter in it it's an identifier like
# Self or Final, so it's matched case sensitively; lowercase patterns match anything
# that way "Self" the type doesn't fire on every method that has a self param

import re

CONCEPTS = {
    "generics": {
        "desc": "parameterised types, TypeVar, Generic",
        "terms": [r"\bgenerics?\b", r"TypeVar\b", r"\bGeneric\b", r"type parameters?", r"type variables?"],
    },
    "variance": {
        "desc": "covariance / contravariance / invariance of type parameters",
        "terms": [r"\b(co|contra|in)varian(t|ce)", r"\bvariance\b", r"bivariant"],
    },
    "protocols": {
        "desc": "structural subtyping, static duck typing",
        "terms": [r"\bprotocols?\b", r"structural (sub)?typ", r"duck typ", r"runtime_checkable"],
    },
    "typeddict": {
        "desc": "dict shapes with a fixed key set",
        "terms": [r"TypedDict", r"typed dict", r"\btotal=", r"extra_items", r"closed="],
    },
    "callables": {
        "desc": "typing callable objects and callbacks",
        "terms": [r"\bCallable\b", r"callable types?", r"\bcallbacks?\b", r"callback protocol"],
    },
    "paramspec": {
        "desc": "forwarding a function's whole parameter list",
        "terms": [r"ParamSpec", r"parameter specification", r"\bConcatenate\b", r"\*\*P\b"],
    },
    "variadic_generics": {
        "desc": "generics over an arbitrary number of types, array shapes",
        "terms": [r"TypeVarTuple", r"variadic", r"\bUnpack\b", r"\*Ts\b", r"array shape"],
    },
    "literals": {
        "desc": "types made of specific values",
        "terms": [r"\bLiteral\b", r"literal types?", r"LiteralString", r"literal strings?"],
    },
    "unions": {
        "desc": "union and optional types, the | operator",
        "terms": [r"\bUnion\b", r"union types?", r"\bOptional\b", r"X \| Y", r"types\.UnionType", r"\bunions?\b"],
    },
    "narrowing": {
        "desc": "refining a type inside a branch, user defined type guards",
        "terms": [r"narrow", r"TypeGuard", r"TypeIs", r"type guards?", r"\bisinstance\b", r"TypeNarrower"],
    },
    "annotation_evaluation": {
        "desc": "when annotations are evaluated, forward references, stringified annotations",
        "terms": [r"__annotations__", r"__annotate__", r"forward ref", r"stringif", r"deferred evaluation",
                  r"laz(y|ily) evaluat", r"from __future__ import annotations", r"annotationlib",
                  r"evaluat\w* (of )?(the )?annotations", r"postponed"],
    },
    "variable_annotations": {
        "desc": "annotating variables and attributes rather than functions",
        "terms": [r"variable annotations?", r"\bClassVar\b", r"annotated assignment", r"type comments?",
                  r"instance variables?", r"class variables?"],
    },
    "final": {
        "desc": "names and classes that must not be reassigned or subclassed",
        "terms": [r"\bFinal\b", r"@final", r"\bfinal (qualifier|decorator|class|name|variable)", r"subclass(ed|ing)? prevent",
                  r"reassign", r"\bconst\b", r"cannot be (changed|modified|overridden|subclassed)"],
    },
    "override": {
        "desc": "marking methods that override a base method",
        "terms": [r"@override", r"\boverrid(e|es|ing|den)\b"],
    },
    "read_only": {
        "desc": "read only items and attributes, immutability",
        "terms": [r"ReadOnly", r"read-only", r"read only", r"immutab", r"\bfrozen\b", r"mutat"],
    },
    "required_items": {
        "desc": "which TypedDict keys must be present",
        "terms": [r"\bRequired\b", r"NotRequired", r"potentially[- ]missing", r"optional (key|item|field)s?",
                  r"required (key|item|field)s?", r"marked (as )?(optional|required)", r"individual(ly)? (key|item)s?"],
    },
    "type_aliases": {
        "desc": "naming a type, the type statement",
        "terms": [r"type alias", r"TypeAlias\b", r"TypeAliasType", r"\btype statement", r"\balias(es)?\b"],
    },
    "inline_types": {
        "desc": "declaring a type where it is used instead of naming it first",
        "terms": [r"\binline\b", r"\banonymous\b", r"literal syntax", r"directly in (an |the )?annotation", r"one-off",
                  r"without (declaring|defining|naming) a"],
    },
    "self_type": {
        "desc": "the type of self, methods returning the enclosing class",
        "terms": [r"\bSelf\b", r"self type", r"return(s|ing)? (an instance of )?(self|the (sub)?class)"],
    },
    "annotated_metadata": {
        "desc": "attaching extra data to a type with Annotated",
        "terms": [r"\bAnnotated\b", r"\bmetadata\b"],
    },
    "deprecation": {
        "desc": "marking things as deprecated in the type system",
        "terms": [r"deprecat"],
    },
    "dataclass_like": {
        "desc": "libraries that synthesise __init__ from fields",
        "terms": [r"dataclass_transform", r"dataclass-like", r"\bdataclass", r"\battrs\b", r"pydantic", r"field specifier"],
    },
    "type_defaults": {
        "desc": "default values for type parameters",
        "terms": [r"type (parameter )?defaults?", r"default (type|for (a |the )?type)", r"default=", r"defaults? for TypeVar"],
    },
    "builtin_generics": {
        "desc": "subscripting builtins like list[int] instead of typing.List",
        "terms": [r"standard collections", r"__class_getitem__", r"typing\.List\b", r"GenericAlias",
                  r"builtin (generic|collection|type)s?", r"built-in (generic|collection|type)s?"],
    },
    "distribution": {
        "desc": "shipping type information, stubs, py.typed",
        "terms": [r"\bstubs?\b", r"py\.typed", r"typeshed", r"distribut", r"packag", r"\.pyi\b"],
    },
    "governance": {
        "desc": "who decides typing questions and how",
        "terms": [r"typing council", r"governance", r"steering council", r"typing-sig", r"typing spec(ification)?\b",
                  r"conformance"],
    },
    "runtime_cost": {
        "desc": "what typing constructs cost at import or call time",
        "terms": [r"runtime (cost|overhead|behavio|penalty)", r"import time", r"startup", r"\boverhead\b",
                  r"performance", r"memory (usage|footprint)", r"slow(er|s)?\b"],
    },
    "intersections": {
        "desc": "a type that satisfies several types at once",
        "terms": [r"intersection", r"\bA ?& ?B\b", r"\bIntersection\b"],
    },
    "subtyping": {
        "desc": "assignability, consistency, gradual typing, Any",
        "terms": [r"subtyp", r"assignab", r"consisten(t|cy)", r"gradual", r"\bAny\b", r"\bobject\b", r"\bNever\b", r"\bNoReturn\b"],
    },
    "overloads": {
        "desc": "multiple signatures for one function",
        "terms": [r"@overload", r"\boverloads?\b", r"\boverloaded\b"],
    },
    "buffers": {
        "desc": "the buffer protocol in the type system",
        "terms": [r"buffer protocol", r"\bBuffer\b", r"__buffer__", r"\bbytes-like"],
    },
    "kwargs": {
        "desc": "typing **kwargs and keyword arguments precisely",
        "terms": [r"\*\*kwargs", r"keyword arguments?", r"\bkwargs\b"],
    },
    "class_hierarchy": {
        "desc": "multiple inheritance, base class constraints, mro",
        "terms": [r"disjoint", r"solid base", r"multiple inheritance", r"\bmro\b", r"base class(es)?", r"\bsubclass"],
    },
    "type_forms": {
        "desc": "values that represent types, introspecting type expressions",
        "terms": [r"TypeForm", r"TypeExpr", r"type expressions?", r"type forms?", r"\bget_type_hints\b", r"introspect"],
    },
    "documentation": {
        "desc": "docstrings and documenting typed APIs",
        "terms": [r"docstrings?", r"\bDoc\(", r"documentation"],
    },
    "syntax": {
        "desc": "new grammar, tokens, parser changes",
        "terms": [r"new syntax", r"\bgrammar\b", r"\bparser\b", r"\btokens?\b", r"\bsoft keyword", r"\bsyntax\b"],
    },
    "type_checkers": {
        "desc": "the tools that consume annotations",
        "terms": [r"\bmypy\b", r"pyright", r"\bpyre\b", r"pytype", r"type ?checkers?"],
    },
    "decorators": {
        "desc": "decorator based designs",
        "terms": [r"\bdecorators?\b"],
    },
    "enums": {
        "desc": "enum members as types",
        "terms": [r"\benums?\b", r"\bEnum\b", r"enumeration"],
    },
    "other_languages": {
        "desc": "prior art in TypeScript, Rust, Kotlin etc",
        "terms": [r"TypeScript", r"\bRust\b", r"\bKotlin\b", r"\bScala\b", r"\bJava\b", r"\bSwift\b", r"\bDart\b", r"\bC#", r"\bHaskell\b"],
    },
}

# name -> (pep that introduced it, other ways people write it)
FEATURES = {
    "TypeVar": (484, []),
    "Generic": (484, []),
    "Union": (484, []),
    "Optional": (484, []),
    "Callable": (484, []),
    "Any": (484, []),
    "cast": (484, [r"typing\.cast"]),
    "overload": (484, [r"@overload"]),
    "NewType": (484, []),
    "TYPE_CHECKING": (484, []),
    "ClassVar": (526, []),
    "Protocol": (544, [r"runtime_checkable"]),
    "__class_getitem__": (560, []),
    "py.typed": (561, [r"py\.typed"]),
    "from __future__ import annotations": (563, [r"__future__ import annotations"]),
    "builtin generics": (585, [r"\blist\[", r"\bdict\[", r"types\.GenericAlias"]),
    "Literal": (586, []),
    "TypedDict": (589, []),
    "Final": (591, [r"@final", r"\bfinal\b"]),
    "Annotated": (593, []),
    "X | Y": (604, [r"types\.UnionType", r"\bint \| str\b", r"X \| Y"]),
    "ParamSpec": (612, [r"Concatenate"]),
    "TypeAlias": (613, []),
    "TypeVarTuple": (646, [r"\bUnpack\b", r"\*Ts\b"]),
    "TypeGuard": (647, []),
    "__annotate__": (649, [r"annotationlib"]),
    "Required": (655, [r"NotRequired"]),
    "Self": (673, []),
    "LiteralString": (675, []),
    "dataclass_transform": (681, []),
    "Buffer": (688, [r"collections\.abc\.Buffer", r"__buffer__"]),
    "type statement": (695, [r"TypeAliasType", r"\btype [A-Z]\w* ?=", r"def \w+\[T\]"]),
    "default=": (696, [r"TypeVar\([^)]*default="]),
    "override": (698, [r"@override"]),
    "deprecated": (702, [r"@deprecated", r"warnings\.deprecated"]),
    "ReadOnly": (705, []),
    "TypeIs": (742, []),
    "TypeForm": (747, [r"TypeExpr"]),
    "extra_items": (728, [r"closed=True"]),
    "disjoint_base": (800, [r"@disjoint_base"]),
}

# i put these together after reading through ~40 rejected ideas sections and noting
# which arguments kept coming back
REASONS = {
    "backwards_compatibility": {
        "desc": "would break or change existing code",
        "terms": [r"backwards?[- ]?(in)?compatib", r"break(s|ing)? (existing|current|user|a lot of) code", r"breaking change",
                  r"existing (code|programs|libraries) (would|will|that)", r"not compatible"],
    },
    "complexity": {
        "desc": "too hard to understand, teach or specify",
        "terms": [r"\bcomplex", r"complicated", r"confus", r"hard(er)? to (read|understand|explain|teach|learn)",
                  r"cognitive", r"too (much|many)", r"mental model", r"subtle", r"surpris"],
    },
    "insufficient_demand": {
        "desc": "not enough real use cases to justify it",
        "terms": [r"use cases? (is|are|were)? ?(rare|uncommon|few|limited|not common)", r"\brare(ly)?\b", r"uncommon",
                  r"not (common|needed|necessary|worth)", r"\bniche\b", r"fewer than \d+ ?%", r"\d+ ?% of", r"little (demand|benefit)",
                  r"(no|few|limited) (real|known|compelling) use", r"(not|un)likely to be used"],
    },
    "already_expressible": {
        "desc": "the same thing can be written today",
        "terms": [r"already (possible|expressible|be done|exists|supported|achievable|covered)", r"can (already )?be (expressed|achieved|done|written|handled)( today)?",
                  r"\bredundant\b", r"equivalent to", r"no (new|additional) (expressiv|capabilit)", r"not (strictly )?necessary",
                  r"existing (mechanism|feature|syntax|approach)"],
    },
    "implementation_cost": {
        "desc": "hard or expensive to implement in CPython or checkers",
        "terms": [r"difficult to implement", r"implementation (would|is|was) (be )?(difficult|hard|complex|complicated|costly|significant|non-trivial)",
                  r"(hard|harder|difficult) (for|to) (implement|type checkers)", r"significant (work|effort|changes)", r"burden on (type checkers|implement)",
                  r"require(s|d)? (changes|modif\w+) to (the )?(compiler|interpreter|parser|grammar|cpython)"],
    },
    "runtime_cost": {
        "desc": "import time, memory or call overhead",
        "terms": [r"runtime (cost|overhead|penalty|evaluation|impact)", r"\boverhead\b", r"\bslow(er|s|ness)?\b", r"performance",
                  r"import time", r"memory", r"startup"],
    },
    "ambiguity": {
        "desc": "the syntax or meaning collides with something else",
        "terms": [r"ambigu", r"\bconflict", r"\bclash", r"collid", r"(hard|difficult|impossible) to parse", r"parsing (issue|problem)",
                  r"(could|would|might) (be )?(mis)?interpret", r"already (has|have) (a |another )?meaning", r"overload(s|ed|ing)? the meaning"],
    },
    "readability": {
        "desc": "ugly, noisy or verbose",
        "terms": [r"\bverbose", r"\bnoisy?\b", r"\bugly\b", r"readab", r"\bclutter", r"\bunwieldy", r"\bcumbersome", r"\bawkward",
                  r"visual(ly)? ", r"too long", r"line noise"],
    },
    "inconsistency": {
        "desc": "doesn't fit how the rest of python or other languages do it",
        "terms": [r"inconsisten", r"\bprecedent\b", r"other languages", r"\bconvention", r"not pythonic", r"unlike (the rest|other)",
                  r"differs? from", r"out of (line|step) with", r"asymmetr"],
    },
    "out_of_scope": {
        "desc": "deferred to a separate or future proposal",
        "terms": [r"out of scope", r"separate PEP", r"future PEP", r"\bdefer", r"\blater\b", r"left for (the )?future", r"follow-?up",
                  r"orthogonal", r"independent(ly)? of this", r"beyond (the scope|this)"],
    },
    "naming": {
        "desc": "the spelling or name was the problem",
        "terms": [r"\bnam(e|ing|es)\b", r"\bspelling\b", r"bikeshed", r"\bverb\b", r"\bnoun\b", r"\bterminology\b"],
    },
    "unsafe": {
        "desc": "would let errors through or weaken guarantees",
        "terms": [r"\bunsafe\b", r"unsound", r"type safety", r"false (positive|negative)", r"(allow|let)s? (errors|bugs)", r"\bloophole",
                  r"nonsensical", r"undetect"],
    },
    "community_split": {
        "desc": "no consensus among the people involved",
        "terms": [r"consensus", r"split down the middle", r"disagree", r"contentious", r"controvers", r"mixed (feedback|reception|opinions)",
                  r"(strong|significant) (opposition|pushback|objections?)", r"not (universally|widely) (liked|accepted|supported)"],
    },
}

# words that don't help when comparing your input to a rejected idea.
# the second half are words that kept showing up in my test questions and matching junk
STOPWORDS = set("""
a an the and or but if of to in on at for with by from as is are was were be been being this that these those it its
we i you they he she them our your their not no nor so than then there here when where which who whom what why how
can could would should may might must will shall do does did done have has had having into onto over under about
also any all each more most much some such very just only even still yet one two also like use used using make made
type types typing pep peps python code proposal propose proposed want adding add new allow allows allowed
both once value first function return instead meaning written support rather same way thing things example
mean means say write writing let lets get gets need needs case cases
""".split())


def compile_terms(terms):
    compiled = []
    for t in terms:
        flags = 0 if re.search(r"[A-Z]", t) else re.I
        compiled.append(re.compile(t, flags))
    return compiled


def feature_patterns(name, extra):
    # the name itself, not as part of a longer word or dotted path, plus the extra spellings
    exact = r"(?<![\w.])" + re.escape(name) + r"(?![\w])"
    return [re.compile(p) for p in [exact] + extra]


CONCEPT_RE = {name: compile_terms(c["terms"]) for name, c in CONCEPTS.items()}
REASON_RE = {name: compile_terms(r["terms"]) for name, r in REASONS.items()}
FEATURE_RE = {name: feature_patterns(name, extra) for name, (_, extra) in FEATURES.items()}


def count_hits(table, text):
    # name -> how many times its patterns hit. names with 0 hits are left out
    hits = {}
    for name, patterns in table.items():
        n = sum(len(p.findall(text)) for p in patterns)
        if n:
            hits[name] = n
    return hits


def match_concepts(text):
    return count_hits(CONCEPT_RE, text)


def match_features(text):
    return count_hits(FEATURE_RE, text)


def match_reasons(text):
    return count_hits(REASON_RE, text)


def tokens(text):
    return {w for w in re.findall(r"[a-z_][a-z0-9_]{2,}", text.lower()) if w not in STOPWORDS}
