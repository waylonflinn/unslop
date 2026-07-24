# Vocabulary Pipeline

> **Status: DESIGN RATIFIED (2026-07-23); implementation pending.**
> This document supersedes the producer command, artifact-layer,
> deduplication, exclusion, and default-namespace decisions in
> `001_BASIC_CONCEPT.md`. The shared Markdown interpretation, source-coordinate
> contract, identifier and definition scoring rules, and measured validation
> target remain governed by 001. Container-root behavior remains governed by
> `002_CONTAINER_RESOLUTION.md`. Optional definition-source scoring is isolated
> in `004_DEFINITION_SOURCE_SCORING.md` and is not required by this pipeline.

## Objective

Separate vocabulary construction into independently measurable stages:

```text
corpus
  → identify
  → occurrence inventory
  → define
  → defined vocabulary
  → manual glossing
  → merge manual supplement
  → canonical namespace vocabulary
```

This split makes the two statistical problems independently tunable.
`identify` measures whether the tool found the right identifier occurrences.
`define` measures whether it selected the right defining occurrence for each
identifier. Manual intervention is reserved for facts not recoverable from the
source, currently `S1` and `S2`.

The pipeline replaces a dedicated adjudication layer. It does not encode
source-specific precedence rules or silently resolve semantic conflicts.

## Shared interpretation

`identify` and `define` use the same parser, tokenizer, identifier scorer,
source alignment, and corpus discovery machinery. Neither command may
reconstruct Markdown interpretation in its front-end.

The raw-position contract from 001 applies throughout:

- `begin` and `end` are zero-based Unicode-character offsets.
- `end` is exclusive.
- `line` is one-based.
- `source[begin:end] == identifier`.
- exact source reads preserve newline sequences.

An inventory is evidence, not an authority. When `define` consumes an
inventory, it reopens the named source and validates every row before using
the span. Missing files, changed source, invalid paths, mismatched spans, or
metadata that does not describe the supplied corpus are errors.

## Exclusions

Both `identify` and `define` accept an exclusion CSV containing an
`identifier` column.

- Matching is exact and case-sensitive.
- An excluded identifier is discarded before stage-specific scoring and
  output.
- Exclusions not present in the input are harmless.
- Extra columns may be ignored; a missing `identifier` column is an error.
- Exclusion order and duplicate exclusion rows do not affect output.

The exclusion file is explicit project configuration. Unslop does not ship or
silently apply a corpus-specific stoplist.

## `identify`

`identify` emits an un-deduplicated occurrence inventory: one row for every
identifier occurrence that satisfies the identifier criteria.

It does not:

- group or deduplicate by identifier;
- apply definition thresholds;
- select a preferred occurrence;
- infer a namespace;
- extract a gloss.

Rows are deterministically ordered by canonical file path, then `begin`, then
`end`, then identifier. Repeated identifiers and repeated text in one file
remain repeated rows.

### Inventory schema

The canonical CSV fields are:

```text
identifier,identifier_score,path,line,begin,end
```

The artifact retains the two-line metadata header defined in 001 and 002:
`file_root` on the first line, then namespace ID, long namespace name, and the
complete `file_set` on the second. The namespace ID remains optional and is
never silently minted.

The inventory is a stable boundary. A human or test fixture may remove rows to
construct a known-good identity set, provided every remaining row and the
artifact metadata still validate against the source corpus.

## `define`

`define` accepts either:

1. corpus inputs, which it passes through the shared occurrence-discovery
   machinery; or
2. one occurrence inventory in the `identify` format.

These input forms must produce the same result when they describe the same
occurrence set. Supplying an inventory allows identifier discovery to be
curated and frozen while definition selection is tuned independently.

For each admitted occurrence, `define` computes definition evidence using the
source context and the scoring rules in 001. It discards rows below the
definition threshold, groups the survivors by exact identifier, and selects
the unique highest-scoring occurrence.

Selection is:

1. highest `definition_score`;
2. unique winner required.

A tie at the highest definition score is an error naming the identifier and
all tied source positions. Input ordering, path ordering, and “first seen”
must never break the tie. Optional definition-source scoring may eventually
insert one evidence-based tie-break step as specified by 004; until that
experiment is ratified and enabled explicitly, a tied maximum remains an
error.

The result is valid only when it contains at most one definition for every
identifier. A namespace containing two selected definitions of the same
identifier is invalid. The remedy is to correct the namespace file set,
exclusions, thresholds, or source material—not to let the tool choose
silently.

### Defined-vocabulary schema

The canonical superset fields are:

```text
identifier,identifier_score,definition_score,gloss,path,line,begin,end
```

For mechanically selected rows:

- both scores and all source-position fields are present;
- `gloss` is empty unless supplied by a later manual or LLM step.

`define` does not currently extract or synthesize glosses.

## Manual supplements

Some definitions are not recoverable by an identifier-anchored scan. The
known Image Store cases are `S1` and `S2`: their identities are carried by
list position rather than by an identifier token.

A manual supplement uses the defined-vocabulary schema and represents this
absence faithfully:

- `identifier` and `gloss` are required;
- known `path` and `line` provenance should be recorded;
- `identifier_score`, `definition_score`, `begin`, and `end` may be null;
- no synthetic identifier span or mechanical score is invented.

Null CSV values serialize as empty fields. Manual or LLM glossing remains an
external process; it is not a hidden mode of `define`.

## `merge`

`merge` creates the checked union of two or more vocabulary CSV files. It is a
structural operation, not an adjudicator.

All inputs must:

- use the defined-vocabulary schema;
- declare the same namespace ID and long namespace name;
- have compatible `file_root` values under the container-resolution rules;
- contain individually valid rows.

The output:

- contains every input row exactly once;
- carries the common namespace identity;
- carries the deterministic sorted union of all input `file_set` entries;
- uses paths expressed relative to the resolved common artifact root;
- is deterministically ordered by identifier, then path, then line, then
  `begin`, with null sort fields ordered before non-null values.

Any duplicate identifier is an error, whether the duplicate rows are identical
or conflicting. `merge` does not prefer generated data, manual data, a later
input, a non-null gloss, or a higher score.

## Namespace membership and references

A canonical defined vocabulary is one namespace. Its namespace ID is
human-approved, and its complete `file_set` is the namespace document list.

For source-document defaults:

- membership in exactly one valid canonical vocabulary gives the document that
  vocabulary's namespace as its default;
- membership in no canonical vocabulary requires an explicit in-document
  default-namespace declaration before bare references can be interpreted;
- membership in more than one canonical vocabulary is invalid.

A bare identifier resolves only in the document's default namespace.
Cross-namespace references use `NSID.ID`. There is no global fallback search
through other vocabularies.

This permits historical corpora such as the Image Store requirements set to
derive membership from their canonical vocabulary without editing case-law
documents. Broader authoring surfaces such as the roadmap may instead carry an
explicit default declaration and qualify foreign references.

## Intended command surface

The ratified operations are:

```text
unslop identify INPUT... --output INVENTORY.csv
unslop define INPUT... --output VOCABULARY.csv
unslop define --inventory INVENTORY.csv --output VOCABULARY.csv
unslop merge INPUT.csv... --output VOCABULARY.csv
```

Shared corpus, threshold, requirement, exclusion, namespace, root, recursion,
overwrite, and verbosity flags should retain their current meanings where
applicable. Exact CLI migration and compatibility aliases for the existing
`vocabulary` / `vocab` command are implementation decisions; they do not alter
the artifact contracts above.

## Validation

Implementation proceeds contract-first:

1. inventory tests prove one row per occurrence, stable order, exclusions, and
   exact source slices;
2. direct-corpus and inventory-fed `define` tests prove equivalent results;
3. selection tests cover unique maxima, tied maxima, excluded identifiers,
   invalid inventory spans, and namespace uniqueness;
4. schema tests cover generated rows, manually glossed rows, nullable manual
   evidence, and round trips;
5. merge tests cover metadata compatibility, root rebasing, file-set union,
   deterministic order, and duplicate rejection;
6. the Image Store corpus comparison continues to recover 157 of 159
   hand-key identifiers mechanically, with only `S1` and `S2` supplied
   manually, unless measured evidence explicitly revises 001.

Identifier recall and precision are measured against `identify`; definition
recall and precision are measured against `define`. A combined result must not
hide which stage caused an error.

## Non-goals

This design does not add:

- automatic gloss extraction;
- generic adjudication rules;
- source-name or path-specific precedence;
- silent conflict resolution;
- automatic namespace IDs;
- fuzzy exclusions;
- consumer joins or document rewriting;
- JSONL output.
