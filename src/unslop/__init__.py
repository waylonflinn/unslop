"""Mechanical consistency tools for prose corpora.

The public API exposes Markdown vocabulary discovery, definition scoring,
raw-source positions, and generated-key CSV persistence. The command-line
interface adds corpus traversal and human-readable key rendering.
"""

from .keyfile import KeyMetadata, VocabularyKey, read_key, write_key
from .vocabulary import (
    ScanOptions,
    VocabularyOccurrence,
    VocabularyRecord,
    find_occurrences,
    markdown_parser,
    scan_text,
)

__version__ = "0.1.0"

__all__ = [
    "KeyMetadata",
    "ScanOptions",
    "VocabularyKey",
    "VocabularyOccurrence",
    "VocabularyRecord",
    "find_occurrences",
    "markdown_parser",
    "read_key",
    "scan_text",
    "write_key",
]
