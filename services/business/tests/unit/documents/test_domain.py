import pytest

from business.contexts.documents.domain.patch import (
    ChangeKind,
    PatchTargetInvalid,
    ReplaceText,
    VersionConflict,
    apply,
    diff,
    ensure_current,
    word_diff,
)
from business.contexts.documents.domain.structure import Section, SectionKind, chunk_sections
from business.contexts.documents.domain.text import normalize, query_terms


def sec(i: int, text: str, kind: SectionKind = SectionKind.PARAGRAPH) -> Section:
    return Section(f"s{i}", i, kind, f"¶{i}", text)


def test_normalizer_unifies_apostrophes_and_cyrillic() -> None:
    assert normalize("To‘lov  MUDDATI") == normalize("toʻlov muddati") == "to'lov muddati"
    assert normalize("Тўлов муддати") == "to'lov muddati"
    assert query_terms("to‘lov muddati?") == ["to'lov", "muddati"]


def test_chunks_do_not_cross_headings_and_respect_size() -> None:
    sections = [sec(0, "1. To‘lov", SectionKind.HEADING), sec(1, "a" * 500), sec(2, "b" * 500),
                sec(3, "2. Javobgarlik", SectionKind.HEADING), sec(4, "c")]
    chunks = chunk_sections(sections)
    assert [c.section_ids for c in chunks] == [("s0", "s1"), ("s2",), ("s3", "s4")]
    assert chunks[0].locator == "¶0 — ¶1"


def test_d04_only_selected_clause_changes() -> None:
    sections = [sec(1, "To‘lov 15 kun ichida, jarima 15 kun."), sec(2, "Muddat 15 kun.")]
    new = apply([ReplaceText("s1", "15 kun", "30 kun")], sections)
    assert new[0].text == "To‘lov 30 kun ichida, jarima 15 kun."
    assert new[1].text == sections[1].text and sections[0].text.startswith("To‘lov 15")
    changes, unchanged = diff(sections, new)
    assert [(c.section_id, c.change) for c in changes] == [("s1", ChangeKind.CHANGED)]
    assert unchanged == 1


def test_second_occurrence_and_ambiguous_target() -> None:
    sections = [sec(1, "15 kun va 15 kun")]
    assert apply([ReplaceText("s1", "15 kun", "30 kun", 2)], sections)[0].text == "15 kun va 30 kun"
    with pytest.raises(PatchTargetInvalid):
        apply([ReplaceText("s1", "45 kun", "30 kun")], sections)
    with pytest.raises(PatchTargetInvalid):
        apply([ReplaceText("s9", "15 kun", "30 kun")], sections)


def test_word_diff_and_version_conflict() -> None:
    assert word_diff("to‘lov 15 kun", "to‘lov 30 kun") == [("=", "to‘lov"), ("-", "15"), ("+", "30"), ("=", "kun")]
    ensure_current("v1", "v1")
    with pytest.raises(VersionConflict):
        ensure_current("v2", "v1")


def test_diff_added_and_removed() -> None:
    changes, _ = diff([sec(1, "a"), sec(2, "b")], [sec(1, "a"), sec(3, "c")])
    assert {(c.section_id, c.change) for c in changes} == {("s3", ChangeKind.ADDED), ("s2", ChangeKind.REMOVED)}
