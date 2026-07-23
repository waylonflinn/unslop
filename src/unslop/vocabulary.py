"""Discover and score vocabulary in Markdown source.

The scanner uses one Markdown parser configuration for both definition and
occurrence discovery. Parsed structure decides which content is eligible;
reported positions always address the exact decoded source supplied by the
caller.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import html
import re

from markdown_it import MarkdownIt


_CANDIDATE_RE = re.compile(
    r"(?<![A-Za-z0-9])"
    r"(?:[A-Za-z][A-Za-z0-9]*\.)?"
    r"[A-Za-z]+(?:\d+[a-d]?)?(?:-[A-Z]+(?:\d+[a-d]?)?)*"
    r"(?![A-Za-z0-9])"
)
_WORD_RE = re.compile(r"[A-Za-z][A-Za-z0-9'-]*")
_PAIRED_HTML_RE = re.compile(
    r"<(?P<tag>[A-Za-z][\w:-]*)\b[^>]*>.*?</(?P=tag)\s*>", re.DOTALL
)
_HTML_TAG_RE = re.compile(r"</?[A-Za-z][^>]*>")
_AUTOLINK_RE = re.compile(r"<(?:https?://|mailto:)[^>]+>")
_IMAGE_RE = re.compile(r"!\[[^\]]*\](?:\([^)]*\)|\[[^\]]*\])")
_LINK_RE = re.compile(r"(?<!!)\[[^\]]*\]\((?P<destination>[^)]*)\)")
_VOID_HTML_TAGS = {
    "area",
    "base",
    "br",
    "col",
    "embed",
    "hr",
    "img",
    "input",
    "link",
    "meta",
    "param",
    "source",
    "track",
    "wbr",
}
_STATUS_SEPARATOR_RE = re.compile(
    r"^(?:\*\*|__)?\s*(?:✅|⚑|⚠️?)?\s*[:\-—]"
)


def markdown_parser() -> MarkdownIt:
    """Create the Markdown parser used by every vocabulary operation.

    Returns:
        A new CommonMark-compatible parser with table support enabled.
    """
    return MarkdownIt().enable("table")


@dataclass(frozen=True)
class ScanOptions:
    """Filtering and scoring thresholds for definition discovery.

    Required attributes are applied before scoring. All requested requirements
    must hold for a candidate to enter scoring.

    Attributes:
        identifier_threshold: Minimum identifier score to retain. Defaults to
            the measured Production threshold of `3`.
        definition_threshold: Minimum definition score to retain. Defaults to
            the measured Production threshold of `3`.
        require_capitalization: Whether candidates must satisfy the
            capitalization attribute.
        require_number: Whether candidates must end in a numeric suffix,
            optionally followed by a lowercase `a` through `d`.
        require_size: Maximum identifier length, or `None` for no size
            requirement.
        include_single_letter: Whether single-letter candidates are eligible.
    """

    identifier_threshold: int = 3
    definition_threshold: int = 3
    require_capitalization: bool = False
    require_number: bool = False
    require_size: int | None = None
    include_single_letter: bool = False


@dataclass(frozen=True)
class VocabularyRecord:
    """A scored vocabulary definition at an exact source position.

    Attributes:
        identifier: Identifier text exactly as it appears in source.
        identifier_score: Score produced by the identifier heuristics.
        definition_score: Score produced by the definition heuristics.
        path: Source path supplied by the caller or normalized by a front-end.
        line: One-based source line containing the identifier.
        begin: Zero-based Unicode-character offset of the identifier.
        end: Exclusive Unicode-character offset of the identifier.
    """

    identifier: str
    identifier_score: int
    definition_score: int
    path: str
    line: int
    begin: int
    end: int


@dataclass(frozen=True)
class VocabularyOccurrence:
    """An unscored identifier occurrence at an exact source position.

    Attributes:
        identifier: Identifier text exactly as it appears in source.
        path: Source path supplied by the caller.
        line: One-based source line containing the identifier.
        begin: Zero-based Unicode-character offset of the identifier.
        end: Exclusive Unicode-character offset of the identifier.
    """

    identifier: str
    path: str
    line: int
    begin: int
    end: int


@dataclass(frozen=True)
class _Context:
    """Structural Markdown position associated with an inline occurrence."""

    position_kind: str


@dataclass(frozen=True)
class _Occurrence:
    """Internal occurrence with definition-relevant structural attributes."""

    identifier: str
    begin: int
    end: int
    opens_block: bool
    bold: bool


def scan_text(
    text: str, path: Path, options: ScanOptions | None = None
) -> list[VocabularyRecord]:
    """Find and score vocabulary definitions in exact decoded source text.

    Candidates must open an eligible Markdown position and satisfy all required
    attributes before scoring. Results preserve document order. `begin` and
    `end` are zero-based Unicode-character offsets into `text`; `end` is
    exclusive and `line` is one-based.

    Args:
        text: Exact decoded Markdown source. Newline characters are part of the
            coordinate system and must not be normalized after scanning.
        path: Source identity copied into each result.
        options: Filtering and scoring configuration. Uses Production defaults
            when omitted.

    Returns:
        One record per admitted definition, in source order.
    """
    # Skipped from docstring:
    # - Parser/source alignment mechanics: callers only depend on raw positions.
    options = options or ScanOptions()
    line_starts = _line_starts(text)
    records: list[VocabularyRecord] = []

    for occurrence, context in _source_occurrences(text):
        if not occurrence.opens_block or context.position_kind in {
            "table_other",
            "list_continuation",
        }:
            continue
        attributes = _identifier_attributes(occurrence.identifier)
        if not _meets_requirements(attributes, options):
            continue
        identifier_score = _identifier_score(attributes)
        if identifier_score < options.identifier_threshold:
            continue
        definition_score = _definition_score(text, occurrence, context)
        if definition_score < options.definition_threshold:
            continue
        records.append(
            VocabularyRecord(
                identifier=occurrence.identifier,
                identifier_score=identifier_score,
                definition_score=definition_score,
                path=str(path),
                line=_line_number(line_starts, occurrence.begin),
                begin=occurrence.begin,
                end=occurrence.end,
            )
        )

    return records


def find_occurrences(text: str, path: Path) -> list[VocabularyOccurrence]:
    """Find unscored identifiers admitted by the shared inline policy.

    Ordinary text, link labels, and inline code are included. Link destinations
    and titles, images, code blocks, and raw HTML are excluded. No identifier or
    definition threshold is applied.

    Args:
        text: Exact decoded Markdown source.
        path: Source identity copied into each occurrence.

    Returns:
        Identifier occurrences in source order with raw-source coordinates.
    """
    line_starts = _line_starts(text)
    return [
        VocabularyOccurrence(
            identifier=occurrence.identifier,
            path=str(path),
            line=_line_number(line_starts, occurrence.begin),
            begin=occurrence.begin,
            end=occurrence.end,
        )
        for occurrence, _context in _source_occurrences(text)
    ]


def _source_occurrences(text: str) -> list[tuple[_Occurrence, _Context]]:
    """Associate admitted inline occurrences with Markdown position context.

    Args:
        text: Exact decoded Markdown source.

    Returns:
        Occurrences paired with their heading, table, list, or bare context in
        document order.
    """
    tokens = markdown_parser().parse(text)
    line_starts = _line_starts(text)
    found: list[tuple[_Occurrence, _Context]] = []

    heading = False
    list_item_inlines: list[bool] = []
    in_table = False
    table_column = -1

    for token in tokens:
        if token.type == "heading_open":
            heading = True
        elif token.type == "heading_close":
            heading = False
        elif token.type == "list_item_open":
            list_item_inlines.append(False)
        elif token.type == "list_item_close":
            list_item_inlines.pop()
        elif token.type == "table_open":
            in_table = True
        elif token.type == "table_close":
            in_table = False
        elif token.type == "tr_open":
            table_column = -1
        elif token.type in {"th_open", "td_open"}:
            table_column += 1
        elif token.type == "inline" and token.map and token.children:
            if heading:
                context = _Context("heading")
            elif in_table and table_column == 0:
                context = _Context("table")
            elif in_table:
                context = _Context("table_other")
            elif list_item_inlines and not list_item_inlines[-1]:
                context = _Context("list")
                list_item_inlines[-1] = True
            elif list_item_inlines:
                context = _Context("list_continuation")
            else:
                context = _Context("bare")

            start_line, end_line = token.map
            source_begin = line_starts[start_line]
            source_end = (
                line_starts[end_line] if end_line < len(line_starts) else len(text)
            )
            source = text[source_begin:source_end]
            occurrences = _inline_occurrences(
                token.children,
                source,
                source_begin,
                only_first_line=context.position_kind
                in {"list", "list_continuation"},
            )
            for occurrence in occurrences:
                found.append((occurrence, context))
    return found


def _line_starts(text: str) -> list[int]:
    """Build zero-based character offsets for every source line.

    Args:
        text: Exact decoded source.

    Returns:
        Offsets containing `0` followed by the position after each newline.
    """
    starts = [0]
    starts.extend(match.end() for match in re.finditer(r"\n", text))
    return starts


def _line_number(line_starts: list[int], offset: int) -> int:
    """Convert a character offset to a one-based line number.

    Args:
        line_starts: Sorted zero-based line-start offsets.
        offset: Character offset to locate.

    Returns:
        One-based line number containing `offset`.
    """
    import bisect

    return bisect.bisect_right(line_starts, offset)


def _excluded_source_ranges(source: str) -> list[tuple[int, int]]:
    """Locate raw inline ranges excluded by the vocabulary policy.

    Args:
        source: Raw source slice for one inline Markdown token.

    Returns:
        Sorted, zero-based, end-exclusive ranges for HTML, images, autolinks,
        and link destinations or titles.
    """
    ranges: list[tuple[int, int]] = []
    for pattern in (_PAIRED_HTML_RE, _HTML_TAG_RE, _AUTOLINK_RE, _IMAGE_RE):
        ranges.extend((match.start(), match.end()) for match in pattern.finditer(source))
    for match in _LINK_RE.finditer(source):
        ranges.append(match.span("destination"))
    return sorted(ranges)


def _inside(offset: int, ranges: list[tuple[int, int]]) -> bool:
    """Return whether an offset falls within any end-exclusive range.

    Args:
        offset: Zero-based offset to test.
        ranges: Start/end pairs in the same coordinate system.

    Returns:
        `True` when any range contains `offset`.
    """
    return any(start <= offset < end for start, end in ranges)


def _inline_occurrences(
    children, source: str, source_begin: int, *, only_first_line: bool = False
) -> list[_Occurrence]:
    """Map eligible parsed identifiers back to raw-source positions.

    Args:
        children: Inline tokens produced by markdown-it.
        source: Exact source slice covered by the parent inline token.
        source_begin: Character offset where `source` begins in the document.
        only_first_line: Whether only the first physical line can open a
            definition position, as required for list items.

    Returns:
        Eligible occurrences with document-relative positions and structural
        attributes used by definition scoring.
    """
    # Skipped from docstring:
    # - Cursor alignment and HTML-depth tracking are implementation details.
    semantic: list[tuple[str, bool, bool]] = []
    html_depth = 0
    strong_depth = 0
    at_line_start = True
    for child in children:
        if child.type == "html_inline":
            raw = child.content.strip()
            if raw.startswith("</"):
                html_depth = max(0, html_depth - 1)
            else:
                tag_match = re.match(r"<([A-Za-z][\w:-]*)", raw)
                tag_name = tag_match.group(1).lower() if tag_match else ""
                if (
                    not raw.endswith("/>")
                    and not raw.startswith("<!--")
                    and tag_name not in _VOID_HTML_TAGS
                ):
                    html_depth += 1
            continue
        if html_depth:
            continue
        if child.type == "strong_open":
            strong_depth += 1
            continue
        if child.type == "strong_close":
            strong_depth = max(0, strong_depth - 1)
            continue
        if child.type in {"softbreak", "hardbreak"}:
            at_line_start = not only_first_line
            continue
        if child.type in {"text", "code_inline"}:
            for match in _CANDIDATE_RE.finditer(child.content):
                semantic.append((match.group(0), at_line_start, bool(strong_depth)))
                at_line_start = False

    excluded = _excluded_source_ranges(source)
    raw_candidates = [
        match
        for match in _CANDIDATE_RE.finditer(source)
        if not _inside(match.start(), excluded)
    ]
    occurrences: list[_Occurrence] = []
    raw_index = 0
    for identifier, opens_block, bold in semantic:
        while (
            raw_index < len(raw_candidates)
            and raw_candidates[raw_index].group(0) != identifier
        ):
            raw_index += 1
        if raw_index == len(raw_candidates):
            continue
        match = raw_candidates[raw_index]
        occurrences.append(
            _Occurrence(
                identifier=identifier,
                begin=source_begin + match.start(),
                end=source_begin + match.end(),
                opens_block=opens_block,
                bold=bold,
            )
        )
        raw_index += 1
    return occurrences


@dataclass(frozen=True)
class _IdentifierAttributes:
    """Normalized identifier properties consumed by requirements and scoring."""

    identifier: str
    scored_part: str
    capitalized: bool
    number_suffix: bool
    size: int
    single_letter: bool


def _identifier_attributes(identifier: str) -> _IdentifierAttributes:
    """Derive scoring attributes from an identifier.

    Args:
        identifier: Unmodified identifier text, optionally namespace-qualified.

    Returns:
        Properties for the unqualified identifier portion.
    """
    scored_part = identifier.rsplit(".", 1)[-1]
    without_suffix = re.sub(r"(?<=\d)[a-d]$", "", scored_part)
    letters = "".join(character for character in without_suffix if character.isalpha())
    return _IdentifierAttributes(
        identifier=identifier,
        scored_part=scored_part,
        capitalized=bool(letters) and letters.isupper(),
        number_suffix=bool(re.search(r"\d+(?:[a-d])?$", scored_part)),
        size=len(scored_part),
        single_letter=len(scored_part) == 1 and scored_part.isalpha(),
    )


def _meets_requirements(
    attributes: _IdentifierAttributes, options: ScanOptions
) -> bool:
    """Test pre-scoring requirements against identifier attributes.

    Args:
        attributes: Derived identifier properties.
        options: Active scan requirements.

    Returns:
        `True` when every requested requirement is satisfied.
    """
    if attributes.single_letter and not options.include_single_letter:
        return False
    if options.require_capitalization and not attributes.capitalized:
        return False
    if options.require_number and not attributes.number_suffix:
        return False
    if options.require_size is not None and attributes.size > options.require_size:
        return False
    return True


def _identifier_score(attributes: _IdentifierAttributes) -> int:
    """Score capitalization, length, and numeric suffix evidence.

    Args:
        attributes: Derived identifier properties.

    Returns:
        Additive identifier score. Single-letter capitals receive the special
        score `1`.
    """
    if attributes.single_letter and attributes.capitalized:
        return 1
    score = 2 if attributes.capitalized else 0
    if attributes.size <= 3:
        score += 3
    elif attributes.size <= 5:
        score += 2
    elif attributes.size <= 7:
        score += 1
    if attributes.number_suffix:
        score += 2
    return score


def _definition_score(
    text: str,
    occurrence: _Occurrence,
    context: _Context,
) -> int:
    """Score whether an opening occurrence behaves like a definition.

    Position, bold emphasis, a following separator, and a substantive trailing
    phrase contribute independent evidence.

    Args:
        text: Exact decoded Markdown source.
        occurrence: Opening identifier occurrence to score.
        context: Markdown position containing the occurrence.

    Returns:
        Additive definition score, or `0` for a non-opening occurrence.
    """
    if not occurrence.opens_block:
        return 0

    score = 2 if context.position_kind in {"heading", "table", "list"} else 0
    source_end = text.find("\n", occurrence.end)
    if source_end < 0:
        source_end = len(text)
    after = text[occurrence.end:source_end]

    if occurrence.bold:
        score += 1
    if _STATUS_SEPARATOR_RE.match(after):
        score += 1

    readable_after = html.unescape(re.sub(r"[`*_#|]", " ", after))
    if len(_WORD_RE.findall(readable_after)) >= 2:
        score += 1
    return score
