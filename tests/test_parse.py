import tempfile
from pathlib import Path

from peptrace.parse import load_dir, parse_pep, plain, split_people, strip_code_blocks

DATA = Path(__file__).resolve().parent.parent / "data" / "peps"

SAMPLE = """\
PEP: 9999
Title: Something Small
Author: Ada Lovelace <ada@example.org>,
        Alan Turing <alan at example.org>
Sponsor: Guido van Rossum <guido@python.org>
Status: Rejected
Type: Standards Track
Topic: Typing
Created: 01-Jan-2030
Replaces: 484, 526
Resolution: `02-Feb-2030 <https://discuss.python.org/t/1>`__

Abstract
========

We propose a thing. It relates to :pep:`484`.

Rejected Ideas
==============

Use a decorator
---------------

A decorator was considered but it has runtime cost and is confusing::

    @thing
    def f(): ...

So we did not do it, see :pep:`526` for the precedent.

Other section
=============

text
"""


def write_sample():
    d = tempfile.mkdtemp()
    p = Path(d, "pep-9999.rst")
    p.write_text(SAMPLE)
    return p


def test_headers_and_people():
    pep = parse_pep(write_sample())
    assert pep.number == 9999
    assert pep.title == "Something Small"
    assert pep.status == "Rejected"
    assert pep.authors == ["Ada Lovelace", "Alan Turing"]
    assert pep.sponsors == ["Guido van Rossum"]
    assert pep.header_peps("replaces") == [484, 526]
    assert pep.resolution() == {"date": "02-Feb-2030", "url": "https://discuss.python.org/t/1"}


def test_sections_levels_and_kinds():
    pep = parse_pep(write_sample())
    titles = [(s.title, s.level, s.kind) for s in pep.sections]
    assert titles == [
        ("Abstract", 0, "abstract"),
        ("Rejected Ideas", 0, "rejected"),
        ("Use a decorator", 1, "rejected"),
        ("Other section", 0, "other"),
    ]
    i = [s.title for s in pep.sections].index("Rejected Ideas")
    assert [s.title for s in pep.children(i)] == ["Use a decorator"]
    assert "runtime cost" in pep.full_body(i)
    assert pep.abstract().startswith("We propose a thing. It relates to PEP 484")


def test_plain_and_code_stripping():
    assert plain(":pep:`484` and ``code`` and `link <http://x>`_ and :py:class:`typing.Self`") == \
        "PEP 484 and code and link and typing.Self"
    body = "intro::\n\n    def f(): ...\n    return 1\n\nafter"
    assert strip_code_blocks(body).split() == ["intro:", "after"]


def test_split_people_handles_odd_spellings():
    assert split_people("A B <a@b>, C D (c at d), E F") == ["A B", "C D", "E F"]


def test_real_corpus_parses():
    peps = load_dir(DATA)
    assert len(peps) >= 40
    for p in peps:
        assert p.number and p.title and p.status, p.path
        assert p.sections, p.path
    by_num = {p.number: p for p in peps}
    assert by_num[563].header_peps("superseded-by") == [649, 749]
    assert any(s.kind == "rejected" for s in by_num[647].sections)


def test_overlines_dont_leak_into_the_previous_section():
    # some peps put a row of *** above a title as well as below it. that top row used
    # to end up glued to the end of whatever section came before
    d = tempfile.mkdtemp()
    p = Path(d, "pep-9998.rst")
    p.write_text("PEP: 9998\nTitle: x\nStatus: Draft\n\nFirst\n=====\n\nsome text\n\n******\nSecond\n******\n\nmore\n")
    pep = parse_pep(p)
    assert [s.title for s in pep.sections] == ["First", "Second"]
    assert pep.sections[0].body == "some text"
