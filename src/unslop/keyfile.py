"""Read and write generated vocabulary-key CSV artifacts.

Each artifact begins with two comment lines carrying its file root, namespace,
and complete input file set. The remaining rows form canonical, unpadded CSV
with one row per discovered definition.
"""

from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path

from .vocabulary import VocabularyRecord


FIELDS = (
    "identifier",
    "identifier_score",
    "definition_score",
    "path",
    "line",
    "begin",
    "end",
)


@dataclass(frozen=True)
class KeyMetadata:
    """Artifact-level namespace and source-set metadata.

    Attributes:
        file_root: Base path against which every `file_set` and record path is
            resolved.
        namespace_id: Optional human-approved short namespace identifier. An
            empty string means the generated artifact awaits adjudication.
        namespace_name: Long namespace name derived from the output filename.
        file_set: Lexicographically ordered input paths relative to
            `file_root`.
    """

    file_root: str
    namespace_id: str
    namespace_name: str
    file_set: tuple[str, ...]


@dataclass(frozen=True)
class VocabularyKey:
    """A generated vocabulary key and the metadata needed to interpret it.

    Attributes:
        metadata: Namespace and source-set information from the comment header.
        records: Definition records in deterministic source order.
    """

    metadata: KeyMetadata
    records: tuple[VocabularyRecord, ...]


def write_key(path: Path, key: VocabularyKey) -> None:
    """Write a complete generated vocabulary key as canonical CSV.

    Existing content is truncated immediately. Parent directories must already
    exist. Fields are not padded for display; use `unslop show` for aligned
    human-readable output.

    Args:
        path: Destination `.csv` path.
        key: Metadata and definition records to serialize.

    Returns:
        None.

    Raises:
        OSError: If the destination cannot be opened or written.
    """
    # Skipped from docstring:
    # - csv.writer configuration: canonical field semantics are the contract.
    with path.open("w", encoding="utf-8", newline="") as handle:
        handle.write(f"# {key.metadata.file_root}\n")
        metadata_fields = (
            key.metadata.namespace_id,
            key.metadata.namespace_name,
            *key.metadata.file_set,
        )
        handle.write("# ")
        writer = csv.writer(handle, lineterminator="\n")
        writer.writerow(metadata_fields)
        writer.writerow(FIELDS)
        for record in key.records:
            writer.writerow(
                (
                    record.identifier,
                    record.identifier_score,
                    record.definition_score,
                    record.path,
                    record.line,
                    record.begin,
                    record.end,
                )
            )


def read_key(path: Path) -> VocabularyKey:
    """Load and validate a generated vocabulary-key CSV artifact.

    The two comment-header lines and exact Production column order are required.
    Numeric record fields are converted to integers.

    Args:
        path: Generated vocabulary-key CSV to read.

    Returns:
        Parsed metadata and definition records in file order.

    Raises:
        OSError: If the file cannot be opened or read.
        ValueError: If metadata, columns, or numeric fields are malformed.
    """
    with path.open("r", encoding="utf-8", newline="") as handle:
        root_line = handle.readline()
        metadata_line = handle.readline()
        if not root_line.startswith("# ") or not metadata_line.startswith("# "):
            raise ValueError(f"{path}: missing vocabulary key comment header")
        file_root = root_line[2:].rstrip("\r\n")
        metadata_fields = next(csv.reader([metadata_line[2:]]))
        if len(metadata_fields) < 2:
            raise ValueError(f"{path}: malformed vocabulary key metadata header")
        namespace_id, namespace_name, *file_set = metadata_fields
        reader = csv.DictReader(handle)
        if tuple(reader.fieldnames or ()) != FIELDS:
            raise ValueError(f"{path}: unexpected vocabulary key columns")
        records = tuple(
            VocabularyRecord(
                identifier=row["identifier"],
                identifier_score=int(row["identifier_score"]),
                definition_score=int(row["definition_score"]),
                path=row["path"],
                line=int(row["line"]),
                begin=int(row["begin"]),
                end=int(row["end"]),
            )
            for row in reader
        )
    return VocabularyKey(
        metadata=KeyMetadata(file_root, namespace_id, namespace_name, tuple(file_set)),
        records=records,
    )
