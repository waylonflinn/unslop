# AGENTS.md

## Project

Unslop is a Python 3.10+ toolkit for mechanical cleanup and consistency checks
over prose corpora. The current Production operation builds a vocabulary key
from Markdown or text files. Generated output is evidence for later human or
LLM adjudication; the producer does not silently make semantic decisions such
as namespace assignment or cross-source precedence.

Read `design/001_BASIC_CONCEPT.md` before changing vocabulary behavior. It is
authoritative for scoring, namespace mechanics, output semantics, validation
targets, and deferred work.

Read `design/002_CONTAINER_RESOLUTION.md` before changing root selection,
generated-key path anchoring, or key-path expansion. It is authoritative for
container discovery, containment, and portable `file_root` behavior.

Read [ARCHITECTURE.md](ARCHITECTURE.md) before changing object boundaries,
module ownership, inheritance or composition relationships, or the public
object model.

## Engineering values

- **Excellence:** Prefer behavior that is correct, useful, and durable.
- **Understanding:** Verify parser and corpus behavior rather than relying on
  assumptions about Markdown.
- **Utility:** Optimize the producer for recall and future consumers for
  precision, as specified in `design/001_BASIC_CONCEPT.md`.
- **Economy:** Prefer one shared mechanism over parallel implementations.
- **Honesty:** Report material flaws or design conflicts directly.
- **Iteration:** Deliver the smallest useful tested slice; let measured evidence
  revise the plan.

Do not introduce speculative abstractions. Do preserve abstractions grounded in
known shared behavior—especially the common parser, tokenizer, scoring, and key
I/O paths required by both producer and future consumer operations.

## Architecture

```text
CLI (`src/unslop/cli.py`)
    ├── container-root selection (`roots.py`)
    ├── corpus discovery and key production (`producer.py`)
    │   ├── root serialization (`roots.py`)
    │   ├── vocabulary analysis (`vocabulary.py`)
    │   └── generated-key model (`keyfile.py`)
    └── generated-key CSV persistence and display (`keyfile.py`)
```

- `vocabulary.py` owns the Markdown parser factory, tokenization, source
  alignment, occurrence discovery, identifier scoring, definition scoring,
  source-coordinate objects, and reusable document scans.
- `producer.py` owns corpus traversal, exact source reads, artifact metadata
  derivation, and generated-key production.
- `keyfile.py` owns the generated CSV schema and its two-line metadata header.
- `roots.py` owns root provenance, Git discovery, containment, and conversion
  between runtime container paths and serialized file roots.
- `cli.py` owns argument validation, output-file policy, console summaries, and
  the human-readable `show` view.
- `__init__.py` defines the supported Python library surface.

The command surface currently consists of:

- `unslop vocabulary` with alias `unslop vocab`
- `unslop show FILE.csv`

## Non-negotiable invariants

### Shared Markdown interpretation

All vocabulary operations obtain a parser through `markdown_parser()`, currently
`MarkdownIt().enable("table")`. Do not construct a second parser configuration
in a front-end. Producer/consumer tokenizer drift causes silent join failures.

The admitted inline policy is:

- Include ordinary text, link-label text, and inline code.
- Exclude link destinations and titles, images, fenced or indented code blocks,
  and raw HTML including attributes and contained text.

Change this policy only with focused tests for both parsed content and raw-source
positions.

### Raw-source positions

- `begin` and `end` are zero-based Unicode-character offsets.
- `end` is exclusive.
- `line` is one-based.
- Coordinates address the exact decoded string supplied to the scanner.
- `Corpus` source reads use `newline=""`; do not normalize newlines before
  scanning.

Every position change must be tested with source slicing. Include CRLF and
non-ASCII cases when changing source alignment.

### Definition and identifier scoring

Scoring rules and thresholds are measured starting points, not intuition-driven
constants. Changes require tests and a corpus comparison against the validation
target in `design/001_BASIC_CONCEPT.md`.

Required attributes are preconditions: when a `--require-*` option is present,
candidates missing that attribute are discarded before scoring.

An identifier must open an eligible line, list item, heading, or table-first-cell
position. Wrapped list continuation lines do not inherit list-opening credit.

### Generated keys

- Production output is canonical, unpadded CSV.
- Human alignment belongs only in `unslop show`.
- The first comment line carries `file_root`.
- The second carries namespace ID, long namespace name, and the complete file
  set.
- Namespace ID is optional and never silently minted.
- One CSV record represents one definition. Do not collapse by identifier in the
  producer.
- Record and file-set paths are relative to the longest shared parent of all
  parsed files.
- `Corpus.root` remains absolute. `file_root` is relative only when `--root` or
  Git discovery supplies a containing root; otherwise it remains absolute.
- Relative `file_root` values are canonical POSIX paths, require an explicit or
  detected container when expanded, and must never traverse or escape it.
- Input documents are canonicalized, deduplicated, and sorted
  lexicographically.
- `--force` directly truncates and rewrites. Atomic replacement is deferred.

The producer writes only the generated layer. It must never overwrite or
synthesize the future adjudicated layer.

## Commands

From the repository root:

```bash
python3 -m venv .venv
.venv/bin/pip install --group dev -e .
```

Run tests:

```bash
.venv/bin/pytest -q
```

Run a focused test:

```bash
.venv/bin/pytest \
  tests/test_vocabulary.py::test_inline_policy_includes_text_link_labels_and_code_but_not_other_locations \
  -q
```

Root-model, containment, and Git-discovery tests belong in
`tests/test_roots.py`.

Generate API documentation:

```bash
PYTHONPATH=src .venv/bin/griffonner generate griffonner/pages/unslop \
  --output docs \
  --template-dir griffonner
```

Useful manual checks:

```bash
unslop vocab path/to/corpus --recursive --output /tmp/vocabulary.csv
unslop show /tmp/vocabulary.csv
git diff --check
```

## Testing practice

Use tests as the contract before changing production behavior.

- Put scanner, position, token-policy, and scoring tests in
  `tests/test_vocabulary.py`.
- Put corpus and producer tests in `tests/test_producer.py`.
- Put CLI, CSV metadata, overwrite, and `show` tests in `tests/test_cli.py`.
- Assert raw positions by slicing the original string with `begin:end`.
- Preserve the measured corpus target: 157 of 159 hand-key identifiers, with
  only `S1` and `S2` intentionally hand-seeded, unless
  `design/001_BASIC_CONCEPT.md` is explicitly revised on new evidence.
- Keep output-order assertions deterministic.

After meaningful changes, run the complete suite and regenerate documentation
when public source locations or docstrings changed.

## Documentation

Follow [DOCUMENTATION.md](DOCUMENTATION.md) for consumer-focused docstrings,
review practice, and Griffonner generation.

## Scope boundaries

Implemented:

- Vocabulary producer
- Unscored occurrence API
- CSV key read/write
- Human-readable key display

Deferred unless explicitly requested and designed:

- Vocabulary consumer and namespace-aware joins
- Adjudicated-layer format and mutation
- Gloss extraction
- Per-identifier grouped output
- Path-reference validation
- Document rewriting
- JSONL output

Do not let deferred features leak into Production behavior through partial
flags, undocumented fields, or speculative compatibility layers.

## Repository boundary

This directory is the standalone Unslop repository root. Keep paths relative
to this directory and do not introduce dependencies on the neighboring
Sloplight checkout. Sloplight retains a compatibility symlink at
`scripts/vocab/VOCAB_EXTRACTION.md` for design traceability and the external
acceptance harness at `scripts/vocab/validate_image_store_vocabulary.py`.
