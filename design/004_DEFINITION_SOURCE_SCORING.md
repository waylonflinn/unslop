# Definition Source Scoring

> **Status: EXPERIMENT PROPOSED (2026-07-23); not part of the ratified
> Production selection rule.** This document isolates a possible tie-breaker
> for `define`. `003_VOCABULARY_PIPELINE.md` remains complete without it:
> absent an explicitly enabled and validated source score, tied maximum
> definition scores are errors.

## Hypothesis

Documents such as `VOCABULARY.md` and `REQUIREMENTS.md` contain unusually dense
clusters of definition-shaped occurrences. That corpus-level evidence may
distinguish a term's founding definition from a restatement when the two
occurrences have the same term-level definition score.

Call the resulting evidence a **definition-source score**. The name describes
what is measured without declaring a permanent “definition file” category.

## Proposed role

The score may be consulted only after ordinary definition scoring ties:

1. highest term-level `definition_score`;
2. among those tied rows, highest definition-source score;
3. unique winner required;
4. any remaining tie is an error.

It must not:

- rescue a row below the definition threshold;
- override a higher term-level definition score;
- prefer a file by name, path, or manually curated rank;
- break a remaining tie by input or filesystem order;
- make an invalid multi-definition namespace appear valid.

## Candidate evidence

For each source document, count occurrences that are structurally eligible as
possible definitions and record the total number of scanned text lines or
admitted identifier occurrences. Candidate measurements include:

- raw count of possible definitions;
- possible definitions per scanned line;
- possible definitions per admitted identifier occurrence;
- a length-smoothed density that prevents tiny files with one heading from
  dominating.

The experiment should begin with the smallest metric that separates known
definition sources without increasing wrong selections. No formula is
ratified here.

The calculation must use the same parser, tokenizer, source alignment,
identifier criteria, exclusions, and definition-position rules as `identify`
and `define`. A parallel heuristic scanner would make the signal incomparable.

## Risks

The mechanism can compound both good and bad tuning:

- a false-positive identifier that looks definition-shaped raises its file's
  score and may then cause another false selection;
- long reference documents may win by raw count despite low definition
  density;
- short files may win by density on too little evidence;
- generated ledgers and summaries may look definition-dense while containing
  restatements rather than founding definitions;
- changing identifier or definition thresholds changes the source score,
  making the tie-breaker less stable than a term-local score;
- using selected definitions to score the file and then using the file score
  to select definitions would be circular.

The score therefore must be computed from pre-selection possible-definition
evidence, not from `define` winners.

## Current baseline

The 2026-07-23 Image Store run produced 157 definition rows representing 116
distinct identifiers. Twenty-nine identifiers had multiple candidate rows:

- 13 had a unique maximum term-level definition score;
- 16 remained tied at the maximum.

The tied set included `CHECK`, `CON1`, `GATE`, `I1`–`I4`, `ID`, `IN7`,
`KEEL`, `LINEAGE`, `PARITY`, `R1`, `SKEL`, `VERIFY`, and `VIEW-A`.

This baseline is evidence for running the experiment, not evidence that source
scoring is correct. Every proposed formula must be evaluated against the
actual intended definition for the tied identifiers.

## Experiment

1. Freeze a known-good occurrence inventory in the 003 format.
2. Label the intended winning source position, or legitimate unresolved
   ambiguity, for every tied identifier.
3. Record per-file raw counts, normalized densities, and candidate formula
   scores without changing selection.
4. Replay `define` with each candidate score as the sole second tie-breaker.
5. Compare:
   - correctly resolved ties;
   - incorrectly resolved ties;
   - ties left unresolved;
   - stability under plausible identifier and definition threshold changes;
   - effects on documents outside the Image Store corpus.
6. Prefer leaving a tie as an error over selecting the wrong definition.

The experiment should report per-term evidence, not only an aggregate accuracy
number, so a high-volume source cannot conceal a systematic semantic mistake.

## Acceptance criteria

Definition-source scoring may move into 003 only after:

- the formula and all normalization constants are explicit;
- it improves correctly resolved ties on a labeled validation set;
- it produces no known incorrect automatic winner;
- it is deterministic across input order and platforms;
- it remains stable across the supported direct-corpus and inventory-fed
  `define` paths;
- focused tests cover tiny files, long files, generated restatement ledgers,
  exclusions, and remaining ties;
- the Image Store comparison documents the before-and-after selections.

If no candidate meets these conditions, `define` keeps the simpler rule:
term-level unique maximum or error.

## Non-goals

This experiment does not:

- automatically classify files as authoritative;
- introduce filename or directory conventions;
- replace namespace file-set curation;
- resolve true homographs;
- permit more than one definition per identifier in a namespace;
- extract glosses;
- weaken duplicate rejection in `merge`.

