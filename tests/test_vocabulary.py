from pathlib import Path

from unslop.vocabulary import ScanOptions, find_occurrences, scan_text


def by_identifier(text: str, **kwargs):
    options = ScanOptions(**kwargs)
    return {record.identifier: record for record in scan_text(text, Path("sample.md"), options)}


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

    assert records["B-Q7"].identifier_score == 6
    assert records["B-Q7"].definition_score == 5
    assert records["X4a"].identifier_score == 7
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

    identifiers = {item.identifier for item in find_occurrences(text, Path("sample.md"))}

    assert {"CA1", "DC7", "Q11"} <= identifiers
    assert not {"MR5", "L1", "X4a", "B-Q7", "KEEL", "SKEL"} & identifiers


def test_void_html_excludes_the_tag_but_not_following_text():
    identifiers = {
        item.identifier
        for item in find_occurrences("<br> CA1\n", Path("sample.md"))
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
