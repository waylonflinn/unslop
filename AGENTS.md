# AGENTS.md

## Project

Unslop is a Python 3.10+ toolkit for mechanical cleanup and consistency checks
over prose corpora. The current Production operation builds a vocabulary key
from Markdown or text files. Generated output is evidence for later human or
LLM adjudication; the producer does not silently make semantic decisions such
as namespace assignment or cross-source precedence.

Read `DESIGN.md` before changing vocabulary behavior. It is authoritative for
scoring, namespace mechanics, output semantics, validation targets, and
deferred work.

## Engineering values

- **Excellence:** Prefer behavior that is correct, useful, and durable.
- **Understanding:** Verify parser and corpus behavior rather than relying on
  assumptions about Markdown.
- **Utility:** Optimize the producer for recall and future consumers for
  precision, as specified in `DESIGN.md`.
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
    ├── vocabulary scanning and scoring (`vocabulary.py`)
    └── generated-key CSV persistence (`keyfile.py`)
```

- `vocabulary.py` owns the Markdown parser factory, tokenization, source
  alignment, occurrence discovery, identifier scoring, and definition scoring.
- `keyfile.py` owns the generated CSV schema and its two-line metadata header.
- `cli.py` owns traversal, argument validation, artifact metadata derivation,
  console summaries, and the human-readable `show` view.
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
- CLI file reads use `newline=""`; do not normalize newlines before scanning.

Every position change must be tested with source slicing. Include CRLF and
non-ASCII cases when changing source alignment.

### Definition and identifier scoring

Scoring rules and thresholds are measured starting points, not intuition-driven
constants. Changes require tests and a corpus comparison against the validation
target in `DESIGN.md`.

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
- Put traversal, CLI, CSV metadata, overwrite, and `show` tests in
  `tests/test_cli.py`.
- Assert raw positions by slicing the original string with `begin:end`.
- Preserve the measured corpus target: 157 of 159 hand-key identifiers, with
  only `S1` and `S2` intentionally hand-seeded, unless `DESIGN.md` is explicitly
  revised on new evidence.
- Keep output-order assertions deterministic.

After meaningful changes, run the complete suite and regenerate documentation
when public source locations or docstrings changed.

## Documentation

Source docstrings follow PEP 257 and Google style. Documentation is written for
consumers who cannot see the implementation.

Document:

- What a public class or function does.
- Argument meaning and constraints.
- Return contents and coordinate units.
- Surprising behavior, exclusions, and failure conditions.
- Outcome-focused algorithm behavior when needed for correct use.

Avoid private implementation references in public docstrings. Complex private
functions may document meaningful internal contracts. For non-trivial methods,
include `Args:` and `Returns:`; include `Raises:` when failures are part of the
consumer contract.

When a relevant detail was considered but deliberately excluded, leave a
reviewable comment immediately after the docstring:

```python
# Skipped from docstring:
# - <detail>: <reason it is not part of the consumer contract>.
```

Generated files under `docs/` are not documentation sources. Change docstrings,
files under `griffonner/pages/unslop/`, or templates under
`griffonner/unslop/`, then regenerate.

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
Sloplight checkout. The Sloplight repository retains only a compatibility
symlink at `scripts/vocab/VOCAB_EXTRACTION.md` for design traceability.
