"""Command-line front-ends for vocabulary production and key inspection.

`unslop vocabulary` (alias `unslop vocab`) scans files or directories and
writes a generated key. `unslop show` renders that machine-oriented CSV as an
aligned table including all artifact metadata.
"""

from __future__ import annotations

import argparse
from dataclasses import replace
import os
from pathlib import Path

from .keyfile import FIELDS, KeyMetadata, VocabularyKey, read_key, write_key
from .vocabulary import ScanOptions, VocabularyRecord, scan_text


SUPPORTED_INPUTS = {".md", ".txt"}


def build_parser() -> argparse.ArgumentParser:
    """Build the complete Unslop argument parser.

    Returns:
        Parser containing the `vocabulary`, `vocab`, and `show` commands.
    """
    parser = argparse.ArgumentParser(prog="unslop")
    subparsers = parser.add_subparsers(dest="command", required=True)

    vocabulary = subparsers.add_parser(
        "vocabulary",
        aliases=["vocab"],
        help="harvest vocabulary definitions from Markdown",
    )
    vocabulary.add_argument("inputs", nargs="+", type=Path)
    vocabulary.add_argument("--output", "-o", required=True, type=Path)
    vocabulary.add_argument("--identifier-threshold", "-i", type=int, default=3)
    vocabulary.add_argument("--definition-threshold", "-d", type=int, default=3)
    vocabulary.add_argument("--require-capitalization", "-c", action="store_true")
    vocabulary.add_argument("--require-number", "-n", action="store_true")
    vocabulary.add_argument("--require-size", "-s", type=int)
    vocabulary.add_argument("--include-single-letter", action="store_true")
    vocabulary.add_argument("--namespace-id", default="")
    vocabulary.add_argument("--recursive", "-r", action="store_true")
    vocabulary.add_argument("--force", "-f", action="store_true")
    vocabulary.add_argument("--verbose", "-v", action="store_true")
    vocabulary.set_defaults(func=_run_vocabulary)

    show = subparsers.add_parser("show", help="show a vocabulary CSV for humans")
    show.add_argument("path", type=Path)
    show.set_defaults(func=_run_show)
    return parser


def main(argv: list[str] | None = None) -> int:
    """Parse arguments and run one Unslop command.

    Filesystem and artifact-validation failures are reported as standard
    argparse errors.

    Args:
        argv: Arguments excluding the executable name. Uses process arguments
            when omitted.

    Returns:
        `0` when the selected command completes successfully.

    Raises:
        SystemExit: For help, invalid arguments, or command failures.
    """
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return args.func(args)
    except (OSError, ValueError) as error:
        parser.error(str(error))
    return 2


def entrypoint() -> None:
    """Run the CLI and terminate the process with its status.

    Raises:
        SystemExit: Always, carrying the status returned by `main`.
    """
    raise SystemExit(main())


def _expand_inputs(inputs: list[Path], recursive: bool) -> list[Path]:
    """Resolve, deduplicate, and order supported input documents.

    Directory inputs are flat unless recursion is requested. Only `.md` and
    `.txt` files are admitted.

    Args:
        inputs: Files and directories supplied by the user.
        recursive: Whether directory traversal includes descendants.

    Returns:
        Unique absolute file paths sorted lexicographically.

    Raises:
        ValueError: If an input is missing, a file type is unsupported, or no
            documents are found.
    """
    files: set[Path] = set()
    for supplied in inputs:
        path = supplied.resolve()
        if path.is_file():
            if path.suffix.lower() not in SUPPORTED_INPUTS:
                raise ValueError(f"unsupported input type: {supplied}")
            files.add(path)
        elif path.is_dir():
            iterator = path.rglob("*") if recursive else path.glob("*")
            files.update(
                candidate.resolve()
                for candidate in iterator
                if candidate.is_file() and candidate.suffix.lower() in SUPPORTED_INPUTS
            )
        else:
            raise ValueError(f"input does not exist: {supplied}")
    if not files:
        raise ValueError("no .md or .txt input files found")
    return sorted(files, key=lambda path: str(path))


def _namespace_name(path: Path) -> str:
    """Derive a long namespace name by stripping every file extension.

    Args:
        path: Output artifact path.

    Returns:
        Filename with all suffixes removed.
    """
    name = path.name
    while Path(name).suffix:
        name = Path(name).stem
    return name


def _run_vocabulary(args: argparse.Namespace) -> int:
    """Generate one vocabulary-key CSV from parsed command arguments.

    The common parent of all resolved files becomes the default file root.
    Record paths and file-set entries are relative to that root.

    Args:
        args: Validated vocabulary-command arguments.

    Returns:
        `0` after writing the key and console summary.

    Raises:
        OSError: If an input or output cannot be read or written.
        ValueError: If output or filtering arguments are invalid.
    """
    # Skipped from docstring:
    # - Verbose rescanning mechanics: only the additional report is public.
    if args.output.suffix.lower() != ".csv":
        raise ValueError("output must have a .csv extension")
    if args.output.exists() and not args.force:
        raise ValueError(f"output exists; use --force to overwrite: {args.output}")
    if args.require_size is not None and args.require_size < 1:
        raise ValueError("--require-size must be at least 1")

    inputs = _expand_inputs(args.inputs, args.recursive)
    root = Path(os.path.commonpath([str(path.parent) for path in inputs]))
    options = ScanOptions(
        identifier_threshold=args.identifier_threshold,
        definition_threshold=args.definition_threshold,
        require_capitalization=args.require_capitalization,
        require_number=args.require_number,
        require_size=args.require_size,
        include_single_letter=args.include_single_letter,
    )
    records: list[VocabularyRecord] = []
    for path in inputs:
        text = path.open("r", encoding="utf-8", newline="").read()
        relative = path.relative_to(root).as_posix()
        records.extend(
            replace(record, path=relative)
            for record in scan_text(text, path, options)
        )
    records.sort(key=lambda item: (item.path, item.begin, item.identifier))

    metadata = KeyMetadata(
        file_root=str(root),
        namespace_id=args.namespace_id,
        namespace_name=_namespace_name(args.output),
        file_set=tuple(path.relative_to(root).as_posix() for path in inputs),
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    write_key(args.output, VocabularyKey(metadata, tuple(records)))
    _print_summary(records)

    if args.verbose and args.identifier_threshold > 0:
        lower_options = replace(options, identifier_threshold=0)
        lower: list[VocabularyRecord] = []
        for path in inputs:
            text = path.open("r", encoding="utf-8", newline="").read()
            lower.extend(
                record
                for record in scan_text(text, path, lower_options)
                if record.identifier_score < args.identifier_threshold
            )
        _print_identifier_line("Below threshold", lower)
    return 0


def _print_identifier_line(label: str, records: list[VocabularyRecord]) -> None:
    """Print records in descending definition-score order on one line.

    Args:
        label: Prefix identifying the report.
        records: Definition records to render.

    Returns:
        None.
    """
    ordered = sorted(
        records,
        key=lambda item: (-item.definition_score, item.identifier, item.path),
    )
    rendered = ", ".join(
        f"{item.identifier} ({item.definition_score})" for item in ordered
    ) or "none"
    print(f"{label}: {rendered}")


def _print_summary(records: list[VocabularyRecord]) -> None:
    """Print admitted definitions and their aggregate score summary.

    Args:
        records: Definition records included in the generated key.

    Returns:
        None.
    """
    _print_identifier_line("Identifiers", records)
    average = (
        sum(record.definition_score for record in records) / len(records)
        if records
        else 0.0
    )
    print(
        f"Summary: {len(records)} identifiers; "
        f"average definition score {average:.2f}"
    )


def _run_show(args: argparse.Namespace) -> int:
    """Render a generated vocabulary key for human inspection.

    Header metadata is printed before an aligned table containing every record
    field. Alignment affects display only; stored CSV values remain unpadded.

    Args:
        args: Parsed show-command arguments containing the key path.

    Returns:
        `0` after rendering the complete artifact.

    Raises:
        OSError: If the key cannot be read.
        ValueError: If the artifact is malformed.
    """
    key = read_key(args.path)
    metadata = key.metadata
    print(f"File root:      {metadata.file_root}")
    print(f"Namespace ID:   {metadata.namespace_id or '(unassigned)'}")
    print(f"Namespace:      {metadata.namespace_name}")
    print(f"Files ({len(metadata.file_set)}):")
    for path in metadata.file_set:
        print(f"  {path}")
    print(f"Records ({len(key.records)}):")
    rows = [
        [
            record.identifier,
            str(record.identifier_score),
            str(record.definition_score),
            record.path,
            str(record.line),
            str(record.begin),
            str(record.end),
        ]
        for record in key.records
    ]
    _print_table(list(FIELDS), rows)
    return 0


def _print_table(headers: list[str], rows: list[list[str]]) -> None:
    """Print a left-aligned plain-text table.

    The header and separator are emitted even when `rows` is empty.

    Args:
        headers: Column labels in display order.
        rows: String values with the same column count as `headers`.

    Returns:
        None.
    """
    widths = [len(header) for header in headers]
    for row in rows:
        widths = [max(width, len(value)) for width, value in zip(widths, row)]
    print("  ".join(header.ljust(width) for header, width in zip(headers, widths)))
    print("  ".join("-" * width for width in widths))
    for row in rows:
        print("  ".join(value.ljust(width) for value, width in zip(row, widths)))
