from pathlib import Path

import unslop
import unslop.vocabulary as vocabulary
from unslop.vocabulary import (
    Definition,
    DefinitionCriteria,
    Occurrence,
    SourceDocument,
    VocabularyScan,
)


def by_identifier(text: str, **kwargs):
    criteria = DefinitionCriteria(**kwargs)
    document = SourceDocument(path=Path("sample.md"), text=text)
    definitions = VocabularyScan(document).definitions(criteria)
    return {definition.identifier: definition for definition in definitions}


def occurrences(text: str):
    document = SourceDocument(path=Path("sample.md"), text=text)
    return VocabularyScan(document).occurrences


def test_scores_supported_definition_shapes_and_raw_character_positions():
    text = (
        "## **B-Q7** ✅ — The nucleus verdict\n\n"
        "- **X4a**: A lowercase suffix definition\n\n"
        "| ID | Meaning |\n"
        "|---|---|\n"
        "| L1 | A ladder definition |\n\n"
        "**KEEL** — A bare line definition\n"
    )

    records = by_identifier(text)

    assert records["B-Q7"].identifier_score == 7
    assert records["B-Q7"].definition_score == 5
    assert records["X4a"].identifier_score == 8
    assert records["L1"].definition_score == 3
    assert records["KEEL"].definition_score == 3
    for identifier, record in records.items():
        assert text[record.begin : record.end] == identifier
        assert record.line == text.count("\n", 0, record.begin) + 1


def test_inline_policy_includes_text_link_labels_and_code_but_not_other_locations():
    text = (
        "CA1 and [DC7](MR5.md) and `Q11`.\n\n"
        "![L1](X4a.png)\n\n"
        "<span data-id=\"B-Q7\">KEEL</span>\n\n"
        "```text\nSKEL\n```\n"
    )

    identifiers = {item.identifier for item in occurrences(text)}

    assert {"CA1", "DC7", "Q11"} <= identifiers
    assert not {"MR5", "L1", "X4a", "B-Q7", "KEEL", "SKEL"} & identifiers


def test_literal_underscores_do_not_create_fragments_but_emphasis_remains():
    text = (
        "- [PROCESS_NOTES.md](../PROCESS_NOTES.md) — Process C8 notes\n"
        "- _CA1_: A catalog rule\n"
    )
    document = SourceDocument(path=Path("sample.md"), text=text)
    scan = VocabularyScan(document)

    identifiers = {item.identifier for item in scan.occurrences}
    definitions = scan.definitions()

    assert not {"PROCESS", "NOTES.md", "md"} & identifiers
    assert "C8" in identifiers
    assert [item.identifier for item in definitions] == ["CA1"]
    assert document.extract(definitions[0].span) == "CA1"

    qualified_text = "REQ.CA1 is referenced here.\n"
    qualified = occurrences(qualified_text)
    assert qualified[0].identifier == "REQ.CA1"
    assert qualified_text[qualified[0].begin : qualified[0].end] == "REQ.CA1"


def test_void_html_excludes_the_tag_but_not_following_text():
    identifiers = {
        item.identifier
        for item in occurrences("<br> CA1\n")
    }

    assert identifiers == {"CA1"}


def test_require_flags_discard_candidates_before_scoring():
    text = "**ABC**: Two words here\n**Ab1**: Two words here\n**LONG9**: Two words here\n"

    assert set(by_identifier(text, definition_threshold=0, require_capitalization=True)) == {"ABC", "LONG9"}
    assert set(by_identifier(text, definition_threshold=0, require_number=True)) == {"Ab1", "LONG9"}
    assert set(by_identifier(text, definition_threshold=0, require_size=3)) == {"ABC", "Ab1"}


def test_single_letters_require_explicit_opt_in():
    assert "A" not in by_identifier("**A**: Two words here\n", identifier_threshold=0, definition_threshold=0)
    assert "A" in by_identifier(
        "**A**: Two words here\n",
        identifier_threshold=0,
        definition_threshold=0,
        include_single_letter=True,
    )


def test_list_position_applies_only_to_the_opening_line_and_offsets_preserve_crlf():
    text = (
        "Préface\r\n"
        "- **CA1**: A catalog definition\r\n"
        "  Q11 continues with ordinary prose\r\n"
    )

    records = by_identifier(text)

    assert set(records) == {"CA1"}
    assert text[records["CA1"].begin : records["CA1"].end] == "CA1"
    assert records["CA1"].line == 2


def test_strong_definition_can_wrap_the_identifier_and_gloss_together():
    records = by_identifier("**PR1 — Leak freedom is the product.**\n")

    assert records["PR1"].definition_score == 3


def test_only_opening_identifier_in_a_table_first_cell_gets_position_credit():
    text = "| ID | Meaning |\n|---|---|\n| — **CATALOG** (SKEL1) | Empty catalog stage |\n"

    records = by_identifier(text)

    assert "CATALOG" in records
    assert "SKEL1" not in records


def test_scan_object_reuses_one_analysis_for_occurrences_and_definitions():
    text = (
        "CA1 is referenced here.\n"
        "- **Q11**: A research question\n"
        "- **LongName**: A low-scoring identifier\n"
    )
    document = SourceDocument(path=Path("sample.md"), text=text)

    scan = VocabularyScan(document)

    assert {item.identifier for item in scan.occurrences} >= {
        "CA1",
        "Q11",
        "LongName",
    }
    assert [item.identifier for item in scan.definitions()] == ["Q11"]
    permissive = DefinitionCriteria(identifier_threshold=0)
    assert [item.identifier for item in scan.definitions(permissive)] == [
        "Q11",
        "LongName",
    ]


def test_definition_is_an_occurrence_with_a_source_span():
    text = "Préface\r\n- **CA1**: A catalog definition\r\n"
    document = SourceDocument(path=Path("sample.md"), text=text)

    definition = VocabularyScan(document).definitions()[0]

    assert isinstance(definition, Definition)
    assert isinstance(definition, Occurrence)
    assert document.extract(definition.span) == definition.identifier
    assert definition.line == 2


def test_legacy_vocabulary_api_is_absent():
    legacy_names = {
        "ScanOptions",
        "VocabularyOccurrence",
        "VocabularyRecord",
        "find_occurrences",
        "scan_text",
    }

    assert legacy_names.isdisjoint(unslop.__all__)
    assert all(not hasattr(unslop, name) for name in legacy_names)
    assert all(not hasattr(vocabulary, name) for name in legacy_names)
