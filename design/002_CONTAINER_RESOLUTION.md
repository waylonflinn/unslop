# Container Root Resolution

> **Status: APPROVED DESIGN; IMPLEMENTATION PENDING (2026-07-23).**
>
> This document specifies how Unslop chooses the root that contains a corpus,
> records a portable `file_root` in generated vocabulary keys, and later
> reconstructs an absolute corpus path from that recorded value.
>
> This design supersedes `001_BASIC_CONCEPT.md` only where that document leaves
> the anchoring of `file_root` implicit. The longest shared parent of the parsed
> files remains the corpus root, and record and `file_set` paths remain relative
> to that corpus root. Scoring, namespace, CSV record, and source-position
> contracts remain governed by `001_BASIC_CONCEPT.md`.

## Objective

Generated vocabulary keys currently record the corpus root as an absolute path:

```text
# /Users/example/Development/sloplight/design/image_store
```

That path is correct on the producing machine but contains a machine-specific
prefix. When a corpus belongs to a stable containing directory, the artifact
should instead record:

```text
# design/image_store
```

The transformation must be reversible. A later command reading the key must be
able to combine the recorded `file_root` with the same kind of containing root
and reconstruct the absolute corpus root without guessing, depending on the
process working directory, or permitting path traversal.

The first automatic container detector is Git. The public and object models are
deliberately broader because Git is a discovery mechanism, not the meaning of
the root.

## Settled decisions

1. Root discovery is based on the **corpus location**, not the directory from
   which `unslop vocab` was invoked.
2. The public override is `--root PATH`, with short form `-R`.
3. An explicit root takes precedence over automatic discovery.
4. Git is the only automatic detector in this implementation.
5. Failed automatic discovery is not an error. Production falls back to an
   absolute `file_root`.
6. Failed or inconsistent **explicit** root selection is an error.
7. A relative stored root requires an explicit or successfully detected
   container root when it is expanded.
8. A missing root for a relative value is an error. The process working
   directory is never an implicit fallback.
9. Relative values must remain inside their container. Empty, noncanonical,
   parent-traversing, and escaping paths are rejected.
10. `read_key()` remains a pure parser. It does not inspect Git, consult the
    working directory, or silently make stored paths absolute.
11. The CSV shape does not change. Absolute versus relative syntax identifies
    whether the stored `file_root` is self-resolving.
12. Existing absolute-root keys continue to parse and resolve directly. No
    compatibility alias or migration layer is required.
13. `Corpus.root` remains absolute. Only its artifact representation may become
    relative.
14. The output CSV's location does not affect producer-side root selection.
15. No detector protocol or detector-class hierarchy is introduced before a
    second real automatic detector exists.

## Vocabulary

### Container

A **container** is an absolute filesystem boundary against which portable paths
can be interpreted. It is not specifically:

- a Docker or operating-system process container;
- an Image Store execution or decision container;
- a Git repository; or
- a Python project.

A Git worktree is the first automatically recognized container. An explicitly
supplied directory is also a container. The terminal containing boundary may be
the root of the filesystem itself.

The qualifier in `ContainerRoot` is intentional. It distinguishes this outer
path boundary from the corpus's `FileRoot`, while describing why the object
exists: it contains the file root and the source paths beneath it.

### ContainerRoot

`ContainerRoot` is the absolute runtime boundary used to validate, shorten, and
expand paths. It owns:

- an absolute, canonical directory path;
- the origin of the selection;
- explicit-root validation;
- automatic root discovery;
- deterministic selection precedence;
- containment checks; and
- contained absolute/relative path conversion.

`ContainerRoot` replaces the earlier proposed name `PathRoot`. `PathRoot` and
`FileRoot` are too easily treated as synonyms in ordinary speech.

`ContainerRoot` also avoids a stateless `RootDetector` class. A class that only
wraps one detection function would be class-per-function design. This class is
justified because it owns state, provenance, invariants, selection, and both
directions of containment-sensitive path behavior.

### FileRoot

`FileRoot` is the serialized base against which every `file_set` and record path
is interpreted. It may be:

- absolute, when no portable container was selected; or
- relative to a `ContainerRoot`.

It owns validation of the stored representation and knows whether a
`ContainerRoot` is required to produce an absolute path.

### Corpus root

`Corpus.root` remains the absolute longest shared parent of every parsed source
file. It is the filesystem truth used for discovery and exact source reads.
It must not be made relative to implement this feature.

### Relationship

```text
ContainerRoot
└── FileRoot
    └── file_set path or Definition.path
```

For a Git-contained Image Store corpus:

```text
ContainerRoot.path = /Users/example/Development/sloplight
FileRoot           = design/image_store
Definition.path    = requirements/01_catalog.md
```

The corresponding source path is:

```text
/Users/example/Development/sloplight
    / design/image_store
    / requirements/01_catalog.md
```

## Command surface

Add the following option to `unslop vocabulary` and its `unslop vocab` alias:

```text
--root PATH, -R PATH
```

Consumer-facing help text:

```text
base against which portable source paths are recorded
```

Future commands that read keys use the same option names with operation-specific
help text:

```text
base against which portable source paths are interpreted
```

The name is intentionally broad. The functionality is fundamental, and callers
should not need a new flag if automatic containment later expands beyond Git.
The implementation should use the more specific local name `container_root` so
it is not confused with `Corpus.root`.

`-R` is distinct from the existing lowercase `-r`:

- `-r` means recursive input discovery.
- `-R` supplies the path root.

### Explicit root behavior

When `--root` is supplied:

1. Resolve it to an absolute canonical path. A relative CLI argument is
   interpreted relative to the invocation directory because the user supplied
   that path explicitly.
2. Require it to exist.
3. Require it to be a directory.
4. Require it to contain `Corpus.root`.
5. Record `Corpus.root` relative to it.

An invalid explicit root is a command error. It must not silently fall back to
Git or to an absolute value.

Recommended error meanings:

```text
root does not exist: <path>
root is not a directory: <path>
corpus root is outside --root: <corpus-root>
```

### Automatic producer behavior

Without `--root`, the producer selects a container in this fixed order:

1. Git worktree containing `Corpus.root`.
2. Filesystem root as the terminal conceptual container.

The filesystem fallback preserves the `FileRoot` as an **absolute** path. It
does not strip the leading filesystem anchor. This retains the syntax that
makes the value self-resolving and avoids turning a machine-specific absolute
path into an indistinguishable unanchored relative path.

Examples:

| Corpus location | Selected origin | Recorded `file_root` |
|---|---|---|
| `/work/repo/design/image_store` in Git worktree `/work/repo` | `git` | `design/image_store` |
| `/work/repo` in Git worktree `/work/repo` | `git` | `.` |
| `/data/corpus` outside a recognized container | `filesystem` | `/data/corpus` |
| `/data/corpus` with `--root /data` | `explicit` | `corpus` |

The corpus and the output CSV may be in different directories. Root detection
must still use the corpus.

## Git discovery

Git discovery asks Git for the worktree containing the corpus root:

```text
git -C <corpus-root> rev-parse --show-toplevel
```

Use Git rather than walking parents for a `.git` directory. Git correctly
handles linked worktrees, submodules, `.git` files, environment configuration,
and its own definition of the current worktree.

Discovery requirements:

- Invoke Git without a shell.
- Suppress ordinary failure diagnostics.
- Treat a missing executable, nonzero exit, empty output, malformed path, or
  unusable returned directory as no discovery.
- Canonicalize the returned path.
- Verify that the returned directory contains the corpus root.
- Do not treat an automatic discovery failure as a CLI error.

A root returned by Git but not containing the corpus is inconsistent evidence
and must not be used.

## Public object model

Create a neutral root-model module:

```text
src/unslop/roots.py
```

It must depend only on the Python standard library. `keyfile.py`,
`producer.py`, and `cli.py` may depend on it; it must not import from those
modules.

### RootOrigin

```python
from enum import Enum


class RootOrigin(str, Enum):
    EXPLICIT = "explicit"
    GIT = "git"
    FILESYSTEM = "filesystem"
```

`RootOrigin` records runtime provenance for validation, diagnostics, and
deterministic tests. It is **not serialized** in the current CSV format.

### ContainerRoot

The public interface is:

```python
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class ContainerRoot:
    path: Path
    origin: RootOrigin

    @classmethod
    def explicit(
        cls,
        path: Path,
        *,
        containing: Path,
    ) -> "ContainerRoot":
        """Create and validate a caller-selected container root."""

    @classmethod
    def discover(
        cls,
        *,
        containing: Path,
    ) -> "ContainerRoot | None":
        """Discover the highest-precedence portable container."""

    @classmethod
    def filesystem(
        cls,
        *,
        containing: Path,
    ) -> "ContainerRoot":
        """Return the filesystem anchor containing an absolute path."""

    @classmethod
    def for_corpus(
        cls,
        *,
        containing: Path,
        explicit: Path | None = None,
    ) -> "ContainerRoot":
        """Select explicit, discovered, then filesystem containment."""

    def contains(self, path: Path) -> bool:
        """Return whether an absolute path is contained by this root."""

    def relative_path(self, path: Path) -> Path:
        """Return a contained absolute path relative to this root."""

    def absolute_path(self, relative: Path) -> Path:
        """Expand a relative path without allowing root escape."""
```

Construction invariants:

- `path` is absolute.
- `path` is canonical.
- `path` exists and is a directory.
- `origin` is a `RootOrigin`.

`explicit()` validates `containing` and raises `ValueError` for an invalid
selection. `discover()` returns `None` when no portable container is found.
`filesystem()` uses the platform filesystem anchor containing the supplied
absolute path. On Windows, drive and UNC anchors must be preserved rather than
assuming a single `/`.

`for_corpus()` owns the producer's deterministic precedence:

```text
explicit → discovered Git worktree → filesystem
```

`relative_path()` requires an absolute, contained input. `absolute_path()`
requires a canonical relative input. Both reject paths that escape the
container, including escape through an existing symlink resolved outside the
root.

### FileRoot

The public interface is:

```python
@dataclass(frozen=True)
class FileRoot:
    value: str

    @classmethod
    def parse(cls, value: str) -> "FileRoot":
        """Parse and validate a serialized file root."""

    @classmethod
    def from_corpus_root(
        cls,
        corpus_root: Path,
        *,
        container_root: ContainerRoot,
    ) -> "FileRoot":
        """Record an absolute corpus root under its selected container."""

    @property
    def is_absolute(self) -> bool:
        """Return whether the stored value is self-resolving."""

    def absolute_path(
        self,
        *,
        container_root: ContainerRoot | None = None,
    ) -> Path:
        """Return the absolute corpus root represented by this value."""

    def __str__(self) -> str:
        """Return the canonical serialized value."""
```

Stored-value invariants:

- The value is not empty.
- The value contains no newline.
- An absolute value is a native absolute path.
- A relative value uses `/` separators in the artifact.
- `.` is the canonical relative representation of the container itself.
- Other relative values have no leading `./`, trailing slash, duplicate
  separator, empty component, or `..` component.
- A relative value cannot escape its supplied `ContainerRoot`, including
  through symlinks.

`from_corpus_root()` behaves by origin:

- `EXPLICIT` and `GIT` record a canonical relative value.
- `FILESYSTEM` records the original canonical absolute corpus root.

If `absolute_path()` holds an absolute value, it returns that path without
requiring or consulting a container. If it holds a relative value, a
`ContainerRoot` is required; omission raises `ValueError`.

Recommended failure meanings:

```text
file_root must not be empty
file_root must be a canonical absolute or POSIX-relative path
file_root must not contain '..'
relative file_root requires a container root
path escapes container root: <path>
```

### KeyMetadata

Change:

```python
file_root: str
```

to:

```python
file_root: FileRoot
```

`KeyMetadata` remains the owner of artifact-level namespace and source-set
metadata. The stronger field type prevents consumers from interpreting the
stored value through ad hoc string operations.

### VocabularyProducer

Extend the public method:

```python
VocabularyProducer.produce(
    corpus,
    *,
    criteria=None,
    namespace_id="",
    namespace_name,
    container_root: ContainerRoot | None = None,
)
```

The producer does not invoke Git. It receives an already selected
`ContainerRoot`.

When `container_root` is omitted by a library caller, the producer uses
`ContainerRoot.filesystem(containing=corpus.root)`, preserving the current
absolute metadata behavior. This keeps a direct library call deterministic and
free of implicit external-process discovery.

The CLI is responsible for calling `ContainerRoot.for_corpus()` and passing the
result.

## Persistence

The first CSV comment line remains:

```text
# <file_root>
```

No new column, comment line, schema version, or origin tag is introduced.

`write_key()` serializes with:

```python
str(key.metadata.file_root)
```

`read_key()` constructs:

```python
FileRoot.parse(serialized_file_root)
```

It does not attempt to make the value absolute.

Existing absolute artifacts remain valid. Relative artifacts gain a documented
anchor contract. Because there are no external consumers and the old value is a
valid `FileRoot`, no compatibility wrapper or string alias should be retained.

`unslop show` continues to print the serialized value. It does not need a root
option because display does not resolve source files.

## Future reader behavior

The vocabulary consumer remains deferred, but its root behavior is settled now
so the producer does not emit an immediately obsolete format.

For a command that reads a vocabulary key:

1. Parse the key without filesystem discovery.
2. If `FileRoot.is_absolute`, use `FileRoot.absolute_path()` directly.
3. If `--root`/`-R` is supplied, construct an explicit `ContainerRoot` and use
   it.
4. Otherwise attempt automatic discovery from the vocabulary key's parent
   directory, not from the process working directory.
5. If the stored value is relative and no suitable container is found, report
   an error requiring `--root`.
6. Validate the reconstructed root before reading any source path.

If a relative key has been copied to `/tmp`, no algorithm can infer which
checkout contains `design/image_store`. The caller must provide `--root`.

Recommended error:

```text
relative file_root requires --root or a detected container root
```

The future consumer must also validate each `file_set` and record path when
joining it to the absolute file root. That second-level containment belongs to
the consumer design and is not implemented by this producer change.

## Determinism

Portable output is useful only if root choice is stable and explainable.

### Current precedence

Producer selection is fixed:

```text
explicit --root
    ↓
Git worktree containing the corpus
    ↓
absolute filesystem fallback
```

Reader selection for a relative root is fixed:

```text
explicit --root
    ↓
supported container discovered from the key location
    ↓
error
```

The current working directory is absent from both sequences.

### Required properties

- The same corpus and explicit arguments produce the same `file_root`
  regardless of invocation directory.
- Output-file placement does not change producer selection.
- Explicit input always wins and is validated strictly.
- Detector order is declared and tested.
- A detector may return a root only when that root contains the subject path.
- Failed optional detection does not alter unrelated command behavior.
- Relative-path expansion never selects among multiple candidate roots by
  filesystem existence alone.
- No result depends on unordered filesystem traversal.

### Expansion beyond Git

The broad `--root` command surface and `ContainerRoot` model permit future
support for other repository, workspace, mount, or container-defining
patterns. They do not make new automatic detection semantics free.

Before adding a second automatic detector:

1. Identify a real use case and its authoritative boundary marker.
2. Define its `RootOrigin`.
3. Specify its precedence relative to Git and filesystem fallback.
4. Preserve Git's current precedence unless this design is explicitly revised.
5. Test environments in which more than one detector matches.
6. Test producer and reader round trips under the same detector.
7. Test relocation and explicit-root recovery.
8. Reassess whether runtime provenance remains sufficient or the artifact must
   serialize an anchor kind.

Adding a detector ahead of an existing detector can change previously stable
output and is therefore a format-semantic change even if the CSV bytes have no
new field. It must not happen accidentally.

Do not introduce a `RootDetector` protocol, abstract base class, or one-class-
per-detector hierarchy in this implementation. `ContainerRoot.discover()` owns
the single Git mechanism and ordered policy. Extract detector strategies only
when a second implementation demonstrates independent variation.

## Follow-On — Out of Scope

### Self-contained Git discovery

The approved implementation discovers a Git worktree by running:

```text
git -C <corpus-root> rev-parse --show-toplevel
```

Python must invoke this command directly, without a shell. This approach depends
on an operating-system `git` executable. That dependency is acceptable for the
current implementation: the mechanism is small, well understood, and a system
actively using Git repositories is likely to have Git installed.

If deployment evidence shows that this dependency harms reproducibility,
replace the subprocess implementation with
[Dulwich](https://dulwich.readthedocs.io/en/latest/), a pure-Python Git
implementation. Relevant evidence would include:

- Git repositories being processed on systems without a Git executable.
- Platform or Git-version differences producing inconsistent discovery.
- Packaging requirements that prohibit reliance on external executables.
- Tests that need Git repository discovery without a system Git installation.

Dulwich provides
[`Repo.discover()`](https://www.dulwich.io/api/dulwich.repo.Repo.html), which
can locate a repository from a containing path. A future implementation should
catch `NotGitRepository`, reject bare repositories when a worktree root is
required, extract the worktree path, canonicalize it, and apply the same
containment checks specified for the subprocess implementation.

If adopted, Dulwich should become the single required Git-discovery mechanism,
not an optional fallback alongside the system executable. Two discovery engines
could disagree across environments and undermine the determinism this design is
intended to provide. Adoption would also require updating project dependencies
and the uv lockfile, replacing subprocess-oriented tests, and verifying ordinary
repositories, linked worktrees, submodules, and no-repository fallback.

The following alternatives remain less suitable:

- GitPython delegates most operations to the Git executable and therefore does
  not remove the external dependency.
- pygit2 introduces a native libgit2 dependency and corresponding deployment
  complexity.
- Manual traversal for `.git` directories or files risks incomplete handling of
  linked worktrees, submodules, and other Git layouts.

This follow-on is explicitly out of scope for the present implementation. It
does not change `ContainerRoot`, `RootOrigin.GIT`, `--root`/`-R`, detector
precedence, fallback behavior, or the CSV format, and it adds no Dulwich
dependency now.

## Ownership and dependency direction

After implementation:

```text
cli ────────────────┐
 │                  │
 │                  v
 ├──> producer ──> roots
 │       │          ^
 │       v          │
 └────> keyfile ────┘
          │
          v
      vocabulary
```

More precisely:

- `roots.py` owns `RootOrigin`, `ContainerRoot`, `FileRoot`, Git discovery,
  containment, and root-relative conversion.
- `producer.py` owns the absolute `Corpus` and uses `FileRoot` when constructing
  `KeyMetadata`.
- `keyfile.py` owns CSV parsing and serialization but delegates root validation
  to `FileRoot`.
- `cli.py` owns `--root`, command errors, automatic selection for `vocab`, and
  future command-specific selection inputs.
- `vocabulary.py` remains independent of root detection and persistence.

Export `RootOrigin`, `ContainerRoot`, and `FileRoot` from `unslop.__init__`.

## Test contract

Use tests as the contract before production edits.

### `tests/test_roots.py`

Cover:

- `ContainerRoot` rejects relative, nonexistent, non-directory, and
  noncanonical roots.
- Explicit construction accepts a containing root.
- Explicit construction rejects a corpus outside the root.
- Git discovery finds the worktree containing the supplied path.
- Git discovery failure and missing Git return no discovered root.
- Git output is rejected when it does not contain the supplied path.
- Selection precedence is explicit, then Git, then filesystem.
- Filesystem fallback uses the correct platform anchor.
- Contained absolute-to-relative-to-absolute conversion round-trips.
- A container root maps itself to `.`.
- Parent traversal is rejected.
- Symlink escape is rejected.
- `FileRoot` parses canonical absolute, relative, and `.` values.
- Empty, newline-bearing, noncanonical, and `..` values are rejected.
- An absolute `FileRoot` needs no container.
- A relative `FileRoot` requires a container.
- Filesystem-origin production remains absolute.
- Explicit- and Git-origin production becomes relative.

Tests may isolate Git subprocess outcomes where necessary, but at least one
focused test should exercise a real temporary Git worktree when Git is
available.

### Existing test files

Update:

- `tests/test_producer.py` for absolute library-default behavior and an explicit
  relative container.
- `tests/test_cli.py` for `--root`/`-R`, automatic Git discovery, invalid
  explicit roots, invocation-directory independence, unchanged `file_set` and
  record paths, CSV round trips, and `show`.

Do not alter scoring or parser expectations.

### Integration acceptance

The complete suite must pass:

```bash
.venv/bin/pytest -q
```

The Image Store acceptance harness must still recover 157 of 159 hand-key
identifiers, with only `S1` and `S2` missing:

```bash
cd /Users/waylonflinn/Development/sloplight/scripts/vocab
uv run validate_image_store_vocabulary.py
```

The harness directly calls `VocabularyProducer.produce()` without a container
root, so it should continue to receive absolute metadata while its vocabulary
and source-position behavior remains unchanged.

## Documentation updates required with implementation

Update all authority and consumer surfaces in the same change:

- `design/001_BASIC_CONCEPT.md`
  - Point `file_root` anchoring to this design.
  - Replace the unconditional absolute/default wording with the approved
    container-relative rule.
- `AGENTS.md`
  - Add this document to the required read set for root or key-path changes.
  - Update the generated-key invariant.
  - Add `tests/test_roots.py` to testing ownership.
- `ARCHITECTURE.md`
  - Add the root value objects and `roots.py` to the current object model and
    dependency direction.
- `README.md`
  - Document `--root`/`-R`, Git auto-detection, absolute fallback, and future
    reader anchoring.
  - Update the generated-key example to use a relative Git-contained root.
- Source docstrings and `griffonner/pages/unslop/`
  - Document every new public type and non-trivial method under
    `DOCUMENTATION.md`.
  - Add a generated API page for the root model.
- Regenerated `docs/`
  - Regenerate rather than editing generated files manually.

Search afterward for stale claims that `file_root` is always absolute or is
derived without a container.

## Implementation sequence

1. Add failing root-model tests.
2. Implement `RootOrigin`, `ContainerRoot`, and `FileRoot` in `roots.py`.
3. Add persistence round-trip tests and change `KeyMetadata.file_root`.
4. Extend `VocabularyProducer.produce()` with `container_root`.
5. Add CLI tests for `--root`, Git discovery, fallback, and cwd independence.
6. Add the argument and production wiring.
7. Update public exports and source docstrings.
8. Update all authority and consumer documentation listed above.
9. Regenerate API documentation.
10. Run unit, integration, formatting, and stale-reference checks.

This sequence keeps the value-object and path-safety contract ahead of the
front-end behavior that depends on it.

## Non-goals

This implementation does not:

- build the vocabulary consumer;
- add a second automatic container detector;
- serialize `RootOrigin`;
- infer a root from process cwd;
- infer a repository from the output CSV location during production;
- change `Corpus.root`, `Corpus.file_set`, or `Definition.path`;
- change vocabulary parsing, scoring, thresholds, ordering, or source spans;
- add compatibility aliases for string-valued `KeyMetadata.file_root`;
- validate deferred path references inside Markdown;
- relocate source files or vocabulary keys; or
- change overwrite or atomic-write behavior.

## Definition of done

Implementation is complete only when:

- All interfaces and invariants in this document are implemented.
- `unslop vocab` records Git-contained corpora relative to the detected
  worktree.
- `--root`/`-R` overrides discovery and rejects invalid containment.
- Non-contained corpora preserve absolute metadata.
- Absolute and relative `FileRoot` values round-trip to the expected absolute
  corpus path.
- Missing anchors, traversal, and escape are rejected.
- Results do not depend on invocation cwd or output placement.
- Existing key files remain readable.
- The complete test suite passes.
- The Image Store acceptance target remains 157/159 with only `S1` and `S2`
  missing.
- Public documentation is regenerated and internally consistent.
- `git diff --check` passes.
