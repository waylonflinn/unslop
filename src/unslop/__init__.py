"""Mechanical consistency tools for prose corpora.

The public API exposes Markdown vocabulary analysis, corpus production,
raw-source positions, and generated-key CSV persistence. The command-line
interface adapts those objects for key generation and human-readable rendering.
"""

from .keyfile import KeyMetadata, VocabularyKey, read_key, write_key
from .producer import Corpus, VocabularyHarvest, VocabularyProducer
from .vocabulary import (
    Definition,
    DefinitionCriteria,
    DefinitionPosition,
    Occurrence,
    SourceDocument,
    SourceSpan,
    VocabularyScan,
    markdown_parser,
)

__version__ = "0.1.0"

__all__ = [
    "Corpus",
    "Definition",
    "DefinitionCriteria",
    "DefinitionPosition",
    "KeyMetadata",
    "Occurrence",
    "SourceDocument",
    "SourceSpan",
    "VocabularyHarvest",
    "VocabularyKey",
    "VocabularyProducer",
    "VocabularyScan",
    "markdown_parser",
    "read_key",
    "write_key",
]
