"""Discover and score vocabulary in Markdown source.

Each scan uses one Markdown parser configuration for both definition and
occurrence discovery. Parsed structure decides which content is eligible;
reported positions always address the exact decoded source supplied by the
caller.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
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
class SourceSpan:
    """An exact, end-exclusive span in decoded source text.

    Attributes:
        begin: Zero-based Unicode-character offset where the span begins.
        end: Exclusive Unicode-character offset where the span ends.
        line: One-based line containing `begin`.
    """

    begin: int
    end: int
    line: int

    def __post_init__(self) -> None:
        """Validate coordinate ordering and units."""
        if self.begin < 0:
            raise ValueError("source span begin must not be negative")
        if self.end < self.begin:
            raise ValueError("source span end must not precede begin")
        if self.line < 1:
            raise ValueError("source span line must be at least 1")


@dataclass(frozen=True)
class SourceDocument:
    """Exact decoded source and its raw-coordinate system.

    `text` is retained without newline normalization. The document owns the
    line index used to create and validate every reported source span.

    Attributes:
        path: Source identity copied into discovered occurrences.
        text: Exact decoded source text.
    """

    path: Path
    text: str
    _lines: tuple[int, ...] = field(init=False, repr=False, compare=False)

    def __post_init__(self) -> None:
        """Build the immutable line index."""
        object.__setattr__(self, "_lines", tuple(_line_starts(self.text)))

    def span(self, begin: int, end: int) -> SourceSpan:
        """Create a validated span in this document.

        Args:
            begin: Zero-based beginning offset.
            end: Exclusive ending offset.

        Returns:
            Span carrying the corresponding one-based line.

        Raises:
            ValueError: If either offset lies outside the document.
        """
        if end > len(self.text):
            raise ValueError("source span extends beyond the document")
        return SourceSpan(begin=begin, end=end, line=self.line_number(begin))

    def line_number(self, offset: int) -> int:
        """Return the one-based line containing a character offset.

        Args:
            offset: Character offset from zero through the document length.

        Returns:
            One-based source line.

        Raises:
            ValueError: If `offset` lies outside the document.
        """
        if offset < 0 or offset > len(self.text):
            raise ValueError("source offset lies outside the document")
        return _line_number(self._lines, offset)

    def extract(self, span: SourceSpan) -> str:
        """Return the exact source addressed by a span.

        Args:
            span: Coordinates in this document.

        Returns:
            Exact decoded substring.

        Raises:
            ValueError: If the span extends beyond the document or carries an
                inconsistent line number.
        """
        if span.end > len(self.text):
            raise ValueError("source span extends beyond the document")
        if self.line_number(span.begin) != span.line:
            raise ValueError("source span line does not match its beginning")
        return self.text[span.begin : span.end]


class DefinitionPosition(Enum):
    """Structural Markdown position carrying definition evidence."""

    BARE = "bare"
    HEADING = "heading"
    LIST_ITEM = "list"
    LIST_CONTINUATION = "list_continuation"
    TABLE_FIRST_CELL = "table"
    TABLE_OTHER_CELL = "table_other"

    @property
    def eligible(self) -> bool:
        """Whether an opening identifier may define vocabulary here."""
        return self not in {
            DefinitionPosition.LIST_CONTINUATION,
            DefinitionPosition.TABLE_OTHER_CELL,
        }

    @property
    def score(self) -> int:
        """Definition evidence contributed by this position."""
        if self in {
            DefinitionPosition.HEADING,
            DefinitionPosition.LIST_ITEM,
            DefinitionPosition.TABLE_FIRST_CELL,
        }:
            return 2
        return 0


@dataclass(frozen=True)
class DefinitionCriteria:
    """Preconditions and score thresholds for definition discovery.

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

    def __post_init__(self) -> None:
        """Validate criteria that have an intrinsic lower bound."""
        if self.require_size is not None and self.require_size < 1:
            raise ValueError("require_size must be at least 1")


@dataclass(frozen=True)
class Occurrence:
    """An identifier occurrence at an exact source position.

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

    def __post_init__(self) -> None:
        """Validate the flattened source coordinates."""
        SourceSpan(begin=self.begin, end=self.end, line=self.line)

    @property
    def span(self) -> SourceSpan:
        """Return this occurrence's coordinates as a value object."""
        return SourceSpan(begin=self.begin, end=self.end, line=self.line)


@dataclass(frozen=True)
class Definition(Occurrence):
    """A scored vocabulary definition, behaviorally also an occurrence.

    Attributes:
        identifier_score: Score produced by the identifier heuristics.
        definition_score: Score produced by the definition heuristics.
    """

    identifier_score: int
    definition_score: int


@dataclass(frozen=True)
class _ScannedOccurrence:
    """Internal occurrence with definition-relevant structural attributes."""

    identifier: str
    begin: int
    end: int
    opens_block: bool
    bold: bool


@dataclass(frozen=True)
class VocabularyScan:
    """One reusable vocabulary analysis of a source document.

    The Markdown parse and raw-source alignment happen once. Callers may then
    obtain every admitted occurrence or apply different definition criteria
    without reparsing the document.

    Attributes:
        document: Exact source that was analyzed.
    """

    document: SourceDocument
    _found: tuple[tuple[_ScannedOccurrence, DefinitionPosition], ...] = field(
        init=False, repr=False
    )

    def __post_init__(self) -> None:
        """Parse and align the document once for all later views."""
        object.__setattr__(
            self,
            "_found",
            tuple(_source_occurrences(self.document)),
        )

    @property
    def occurrences(self) -> tuple[Occurrence, ...]:
        """Return every occurrence admitted by the shared inline policy."""
        return tuple(
            Occurrence(
                identifier=occurrence.identifier,
                path=str(self.document.path),
                line=self.document.line_number(occurrence.begin),
                begin=occurrence.begin,
                end=occurrence.end,
            )
            for occurrence, _position in self._found
        )

    def definitions(
        self, criteria: DefinitionCriteria | None = None
    ) -> tuple[Definition, ...]:
        """Select and score definitions from this analysis.

        Args:
            criteria: Preconditions and thresholds. Uses Production defaults
                when omitted.

        Returns:
            Admitted definitions in source order.
        """
        active = criteria or DefinitionCriteria()
        definitions: list[Definition] = []
        for occurrence, position in self._found:
            if not occurrence.opens_block or not position.eligible:
                continue
            shape = _identifier_shape(occurrence.identifier)
            if not _meets_requirements(shape, active):
                continue
            identifier_score = _identifier_score(shape)
            if identifier_score < active.identifier_threshold:
                continue
            definition_score = _definition_score(
                self.document.text, occurrence, position
            )
            if definition_score < active.definition_threshold:
                continue
            definitions.append(
                Definition(
                    identifier=occurrence.identifier,
                    identifier_score=identifier_score,
                    definition_score=definition_score,
                    path=str(self.document.path),
                    line=self.document.line_number(occurrence.begin),
                    begin=occurrence.begin,
                    end=occurrence.end,
                )
            )
        return tuple(definitions)


def _source_occurrences(
    document: SourceDocument,
) -> list[tuple[_ScannedOccurrence, DefinitionPosition]]:
    """Associate admitted inline occurrences with Markdown position context.

    Args:
        document: Exact decoded Markdown source and its line index.

    Returns:
        Occurrences paired with their heading, table, list, or bare context in
        document order.
    """
    text = document.text
    tokens = markdown_parser().parse(text)
    line_starts = document._lines
    found: list[tuple[_ScannedOccurrence, DefinitionPosition]] = []

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
                position = DefinitionPosition.HEADING
            elif in_table and table_column == 0:
                position = DefinitionPosition.TABLE_FIRST_CELL
            elif in_table:
                position = DefinitionPosition.TABLE_OTHER_CELL
            elif list_item_inlines and not list_item_inlines[-1]:
                position = DefinitionPosition.LIST_ITEM
                list_item_inlines[-1] = True
            elif list_item_inlines:
                position = DefinitionPosition.LIST_CONTINUATION
            else:
                position = DefinitionPosition.BARE

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
                only_first_line=position
                in {
                    DefinitionPosition.LIST_ITEM,
                    DefinitionPosition.LIST_CONTINUATION,
                },
            )
            for occurrence in occurrences:
                found.append((occurrence, position))
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
) -> list[_ScannedOccurrence]:
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
    occurrences: list[_ScannedOccurrence] = []
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
            _ScannedOccurrence(
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
class _IdentifierShape:
    """Normalized identifier properties consumed by requirements and scoring."""

    identifier: str
    scored_part: str
    capitalized: bool
    number_suffix: bool
    size: int
    single_letter: bool


def _identifier_shape(identifier: str) -> _IdentifierShape:
    """Derive scoring attributes from an identifier.

    Args:
        identifier: Unmodified identifier text, optionally namespace-qualified.

    Returns:
        Properties for the unqualified identifier portion.
    """
    scored_part = identifier.rsplit(".", 1)[-1]
    without_suffix = re.sub(r"(?<=\d)[a-d]$", "", scored_part)
    letters = "".join(character for character in without_suffix if character.isalpha())
    return _IdentifierShape(
        identifier=identifier,
        scored_part=scored_part,
        capitalized=bool(letters) and letters.isupper(),
        number_suffix=bool(re.search(r"\d+(?:[a-d])?$", scored_part)),
        size=len(scored_part),
        single_letter=len(scored_part) == 1 and scored_part.isalpha(),
    )


def _meets_requirements(
    shape: _IdentifierShape, criteria: DefinitionCriteria
) -> bool:
    """Test pre-scoring requirements against identifier attributes.

    Args:
        shape: Derived identifier properties.
        criteria: Active definition requirements.

    Returns:
        `True` when every requested requirement is satisfied.
    """
    if shape.single_letter and not criteria.include_single_letter:
        return False
    if criteria.require_capitalization and not shape.capitalized:
        return False
    if criteria.require_number and not shape.number_suffix:
        return False
    if criteria.require_size is not None and shape.size > criteria.require_size:
        return False
    return True


def _identifier_score(shape: _IdentifierShape) -> int:
    """Score capitalization, length, and numeric suffix evidence.

    Args:
        shape: Derived identifier properties.

    Returns:
        Additive identifier score. Single-letter capitals receive the special
        score `1`.
    """
    if shape.single_letter and shape.capitalized:
        return 1
    score = 2 if shape.capitalized else 0
    if shape.size <= 3:
        score += 3
    elif shape.size <= 5:
        score += 2
    elif shape.size <= 7:
        score += 1
    if shape.number_suffix:
        score += 2
    return score


def _definition_score(
    text: str,
    occurrence: _ScannedOccurrence,
    position: DefinitionPosition,
) -> int:
    """Score whether an opening occurrence behaves like a definition.

    Position, bold emphasis, a following separator, and a substantive trailing
    phrase contribute independent evidence.

    Args:
        text: Exact decoded Markdown source.
        occurrence: Opening identifier occurrence to score.
        position: Markdown position containing the occurrence.

    Returns:
        Additive definition score, or `0` for a non-opening occurrence.
    """
    if not occurrence.opens_block:
        return 0

    score = position.score
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
