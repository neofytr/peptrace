# reads a PEP .rst file into something we can poke at

import re
from dataclasses import dataclass
from pathlib import Path

UNDERLINE = re.compile(r"^(=+|-+|\*+|\^+|~+|\"+|'+)\s*$")
PEP_ROLE = re.compile(r":pep:`(\d+)")
EMAIL = re.compile(r"\s*<[^>]*>|\s*\([^)]*\)")

# section title -> rough kind; first match wins so keep "rejected" on top,
# otherwise something like "Rejected Syntax" ends up as spec
SECTION_KINDS = [
    ("rejected", r"reject|alternativ|out-of-scope|other ideas|why not|objection"),
    ("open", r"open (issue|question)s?"),
    ("abstract", r"^abstract|^summary|^overview"),
    ("motivation", r"motivation|problem|background|use cases?"),
    ("rationale", r"rationale|design|goals|terminology"),
    ("compat", r"compatib"),
    ("teaching", r"how to teach"),
    ("spec", r"specification|semantics|syntax|runtime|grammar|behavio"),
    ("impl", r"implementation|performance"),
    ("meta", r"copyright|reference|acknowledg|footnote|appendix|resources|version history|security"),
]


@dataclass
class Section:
    title: str
    level: int
    kind: str      # subsections just copy their parent's kind
    body: str      # only this section's own text, subsections not included
    index: int


@dataclass
class Pep:
    number: int
    title: str
    headers: dict
    sections: list
    path: str = ""

    @property
    def status(self):
        return self.headers.get("status", "")

    @property
    def authors(self):
        return split_people(self.headers.get("author", ""))

    @property
    def sponsors(self):
        return split_people(self.headers.get("sponsor", ""))

    @property
    def text(self):
        return "\n".join(s.title + "\n" + s.body for s in self.sections)

    def header_peps(self, key):
        # Requires / Replaces / Superseded-By are just "649, 749"
        return [int(x) for x in re.findall(r"\d+", self.headers.get(key, ""))]

    def resolution(self):
        # older peps have a bare url here, newer ones do `07-Mar-2023 <url>`__
        value = self.headers.get("resolution", "")
        if not value:
            return {}
        m = re.search(r"`([^<]*)<([^>]+)>`", value)
        if m:
            return {"date": m.group(1).strip(), "url": m.group(2)}
        return {"date": "", "url": value.strip()}

    def children(self, i):
        # everything nested under sections[i]; stops at the next section on the same level or higher
        result = []
        for s in self.sections[i + 1:]:
            if s.level <= self.sections[i].level:
                break
            result.append(s)
        return result

    def full_body(self, i):
        text = self.sections[i].body
        for s in self.children(i):
            text += "\n" + s.title + "\n" + s.body
        return text

    def abstract(self):
        for s in self.sections:
            if s.level == 0 and s.kind == "abstract":
                return plain(self.full_body(s.index)).strip()
        return ""


def split_people(value):
    names = []
    for part in value.split(","):
        name = EMAIL.sub("", part).strip()
        if name:
            names.append(name)
    return names


def kind_of(title):
    for kind, pattern in SECTION_KINDS:
        if re.search(pattern, title.lower()):
            return kind
    return "other"


def parse_headers(lines):
    # "Key: value" lines until the first blank one; long values wrap onto indented lines
    headers = {}
    key = None
    for i, line in enumerate(lines):
        if not line.strip():
            return headers, i + 1
        if line[0].isspace() and key:
            headers[key] += " " + line.strip()
        else:
            key, _, value = line.partition(":")
            key = key.strip().lower()
            headers[key] = value.strip()
    return headers, len(lines)


def is_title(line, next_line):
    # rst title = a line with an underline under it that's at least as long
    return (line.strip() != ""
            and not line[0].isspace()
            and UNDERLINE.match(next_line) is not None
            and len(next_line.rstrip()) >= len(line.rstrip()))


def parse_sections(lines):
    sections = []
    underline_chars = []   # rst has no fixed levels. first char we see is level 0, the next new one level 1, etc
    body = []

    def close_current():
        if sections:
            sections[-1].body = "\n".join(body).strip("\n")
        body.clear()

    i = 0
    while i < len(lines):
        line = lines[i]
        next_line = lines[i + 1] if i + 1 < len(lines) else ""
        if not is_title(line, next_line):
            body.append(line)
            i += 1
            continue

        char = next_line[0]
        if char not in underline_chars:
            underline_chars.append(char)
        level = underline_chars.index(char)

        if body and UNDERLINE.match(body[-1]):
            body.pop()   # that was an overline, not text
        close_current()

        if level == 0:
            kind = kind_of(line)
        elif sections:
            kind = sections[-1].kind
        else:
            kind = "other"
        sections.append(Section(line.strip(), level, kind, "", len(sections)))
        i += 2

    close_current()
    return sections


def parse_pep(path):
    lines = Path(path).read_text(encoding="utf-8").splitlines()
    headers, start = parse_headers(lines)
    return Pep(
        number=int(headers["pep"]),
        title=headers.get("title", "").strip(),
        headers=headers,
        sections=parse_sections(lines[start:]),
        path=str(path),
    )


def load_dir(folder):
    peps = [parse_pep(p) for p in Path(folder).glob("pep-*.rst")]
    peps.sort(key=lambda p: p.number)
    return peps


def pep_refs(text):
    return [int(n) for n in PEP_ROLE.findall(text)]


def plain(text):
    # turn rst markup into readable text. not perfect, good enough for snippets
    text = re.sub(r":pep:`(\d+)`", r"PEP \1", text)
    text = re.sub(r":[\w:]+:`([^`<]+?)(\s*<[^>]+>)?`", r"\1", text)   # :py:class:`x` and :ref:`x <y>`
    text = re.sub(r"`([^`<]+?)\s*<[^>]+>`__?", r"\1", text)           # `text <url>`_
    text = re.sub(r"``([^`]+)``", r"\1", text)
    text = re.sub(r"\*\*?([^*]+)\*\*?", r"\1", text)
    text = re.sub(r"`([^`]+?)`__?", r"\1", text)                      # `anonymous link`__
    text = re.sub(r"\[#?\w+\]_", "", text)                             # footnote markers
    text = re.sub(r"^(\.\. |__ ).*$", "", text, flags=re.M)            # directives and link targets
    text = re.sub(r"::\s*$", ":", text, flags=re.M)
    return text


def strip_code_blocks(text):
    # a line ending in :: starts a code block, it ends at the first line that isn't indented
    out = []
    in_code = False
    for line in text.splitlines():
        if in_code:
            if line.strip() and not line[0].isspace():
                in_code = False
            else:
                continue
        if line.rstrip().endswith("::") or re.match(r"^\s*\.\. code", line):
            in_code = True
            if line.strip() != "::":   # a lone :: is just the marker, nothing to keep
                out.append(re.sub(r"::\s*$", ":", line))
            continue
        out.append(line)
    return "\n".join(out)
