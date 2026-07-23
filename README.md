# Unslop

Unslop provides mechanical cleanup and consistency tools for prose corpora.
Its first production operation discovers vocabulary definitions in Markdown,
scores the evidence that each candidate is an identifier and a definition, and
writes a reviewable CSV key with exact source positions.

The generated key is deliberately mechanical. Human or LLM review can assign
namespaces, choose precedence, add hand-seeded entries, and otherwise adjudicate
the result without obscuring what the producer found.

## Status

Available now:

- `unslop vocabulary` (alias `unslop vocab`) — generate a vocabulary-key CSV.
- `unslop show` — render a generated key and its comment-header metadata for
  human inspection.
- Python APIs for reusable document analysis, corpus production, and key I/O.

The vocabulary consumer, path-reference checks, gloss extraction, grouped
output, and rewrite support remain deferred. See
[001_BASIC_CONCEPT.md](design/001_BASIC_CONCEPT.md) for the full design,
validation evidence, and open decisions. Portable root selection is specified
in [002_CONTAINER_RESOLUTION.md](design/002_CONTAINER_RESOLUTION.md).

## Installation

Unslop requires Python 3.10 or newer.

```bash
python3 -m venv .venv
.venv/bin/pip install -e .
```

This installs the `unslop` command.

## Generate a vocabulary key

Scan explicit files:

```bash
unslop vocabulary docs/requirements.md docs/roadmap.md \
  --output requirements.csv
```

Scan a directory recursively:

```bash
unslop vocab docs/ --recursive --output requirements.csv
```

Directory scans are flat unless `--recursive` is present. Inputs are limited to
`.md` and `.txt` files, resolved to unique documents, and sorted
lexicographically. Their longest common parent remains the absolute corpus root;
record paths and the recorded file set are relative to that corpus root.

When the corpus is in a Git worktree, Unslop records the corpus root relative
to the worktree so the key can move with its repository. Outside Git, the
serialized `file_root` remains absolute. Override automatic selection with an
explicit containing directory:

```bash
unslop vocab docs/ --recursive \
  --root /workspace \
  --output requirements.csv
```

`--root` has the short form `-R`; lowercase `-r` remains `--recursive`.
Explicit roots must exist, be directories, and contain the corpus. Root
selection follows explicit root, then the Git worktree containing the corpus,
then absolute filesystem fallback. It does not depend on the invocation
directory or output-file location.

Use `--namespace-id` when a human-approved short ID is already known:

```bash
unslop vocab docs/ --recursive \
  --namespace-id REQ \
  --output requirements.csv
```

The namespace ID is optional. When omitted, the generated header leaves it
empty for later adjudication.

Useful filters:

| Option | Effect |
|---|---|
| `--identifier-threshold N`, `-i N` | Minimum identifier score; default `3`. |
| `--definition-threshold N`, `-d N` | Minimum definition score; default `3`. |
| `--require-capitalization`, `-c` | Discard candidates lacking the capitalization attribute. |
| `--require-number`, `-n` | Discard candidates lacking a numeric suffix. |
| `--require-size N`, `-s N` | Discard candidates longer than `N` characters. |
| `--include-single-letter` | Admit single-letter candidates. |
| `--root PATH`, `-R PATH` | Base against which portable source paths are recorded. |
| `--verbose`, `-v` | Also report definitions below the identifier threshold. |
| `--force`, `-f` | Overwrite an existing output file. |

## Inspect a generated key

The stored CSV remains canonical and unpadded for Python, pandas, Node, and
other CSV consumers. Use `show` for aligned human-readable output:

```bash
unslop show requirements.csv
```

The display includes the file root, namespace ID and name, complete input file
set, and every record column.

## Generated-key format

Every key begins with two comment lines followed by ordinary CSV:

```csv
# docs
# REQ,requirements,requirements.md,roadmap.md
identifier,identifier_score,definition_score,path,line,begin,end
CA1,7,4,requirements.md,12,418,421
```

- The output filename, with all extensions removed, supplies the long namespace
  name.
- `file_root` is either a canonical absolute path or a canonical path relative
  to an explicit or detected container root. `.` represents the container
  itself.
- `line` is one-based.
- `begin` and `end` are zero-based Unicode-character offsets into the exact
  decoded source; `end` is exclusive.
- Source files are read without newline translation, so CRLF and non-ASCII text
  retain stable positions.
- One row represents one definition, not one distinct identifier.

For pandas, skip the metadata comments while reading records:

```python
import pandas as pd

records = pd.read_csv("requirements.csv", comment="#")
```

Use `unslop.keyfile.read_key` when the header metadata is also needed.
`read_key()` parses `file_root` as a `FileRoot` without inspecting Git or the
process working directory. An absolute value resolves directly. Resolving a
relative value requires a matching `ContainerRoot`; copied keys cannot infer
their original checkout from the relative text alone.

## Python API

```python
from pathlib import Path

from unslop import (
    ContainerRoot,
    DefinitionCriteria,
    FileRoot,
    SourceDocument,
    VocabularyScan,
)

path = Path("requirements.md")
text = path.open("r", encoding="utf-8", newline="").read()
document = SourceDocument(path=path, text=text)
scan = VocabularyScan(document)
definitions = scan.definitions(DefinitionCriteria())
occurrences = scan.occurrences

container = ContainerRoot.explicit(
    Path("/workspace"),
    containing=Path("/workspace/docs"),
)
corpus_root = FileRoot.parse("docs").absolute_path(container_root=container)
```

One `VocabularyScan` supplies both definition and occurrence views without
reparsing the document. For a file-backed corpus, use `Corpus.discover()` and
`VocabularyProducer.produce()` to build a `VocabularyKey` in memory.
`read_key` and `write_key` provide typed access to generated CSV artifacts.
The generated [API documentation](docs/index.md) contains the complete public
interface.

## Development

Install the editable package and its development dependency group:

```bash
.venv/bin/pip install --group dev -e .
```

Run the tests:

```bash
.venv/bin/pytest -q
```

Generate API documentation:

```bash
PYTHONPATH=src .venv/bin/griffonner generate griffonner/pages/unslop \
  --output docs \
  --template-dir griffonner
```

The documentation is generated from source docstrings. Edit docstrings, page
descriptors, or templates rather than editing files under `docs/` directly.

## Repository layout

```text
.
├── AGENTS.md                 Agent orientation and engineering invariants
├── ARCHITECTURE.md           Object design and refactoring guide
├── DOCUMENTATION.md          Code documentation guidelines
├── README.md                 User and contributor guide
├── design/
│   ├── 001_BASIC_CONCEPT.md      Vocabulary design, evidence, and open decisions
│   └── 002_CONTAINER_RESOLUTION.md  Portable root-selection design
├── docs/                     Generated API documentation
├── griffonner/               Documentation pages and templates
├── src/unslop/
│   ├── producer.py           Corpus discovery and key production
│   ├── roots.py              Root selection, containment, and serialization
│   ├── vocabulary.py         Source analysis and scoring
│   └── keyfile.py            Generated-key model and CSV persistence
└── tests/                    Behavioral contract tests
```
