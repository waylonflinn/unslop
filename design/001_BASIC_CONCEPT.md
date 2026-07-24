# Image Store — Vocabulary Extraction (tool spec)

> **Status: PRODUCTION PRODUCER BUILT (2026-07-22); consumer and rewrite
> remain deferred.** Command surface, CSV format, namespace mechanics,
> parser policy, and raw-source position units are settled for Production.
> Implements next-step 1 of `PROCESS_STRATEGIES.md`
> §Rebuild (build the translation key) and feeds next-step 3 (the
> consistency/coverage harness). Scoring rules were measured against
> `TRANSLATION_KEY.csv` — the hand-verified 164-row key covering every ID
> the 15 unit sheets cite — before being written down; §Validation records
> the numbers and is the regression target. *(carried)* = the user's
> original spec; *(amended)* = changed on measured evidence; *(new)* =
> added in review. Remaining open items are **flagged, not filled** (P1).
>
> **Moved 2026-07-22** out of the design corpus into the standalone Unslop
> repository, next to the implementation it specifies. A compatibility
> symlink remains at `scripts/vocab/VOCAB_EXTRACTION.md` in the Sloplight
> repository for traceability. Paths below resolve against two
> roots, in the spec's own `file_root` sense: bare corpus documents
> (`ROADMAP.md`, `PARTITIONS.md`, `VOCABULARY.md`, `TRANSLATION_KEY.csv`,
> `PATH_AUDIT.md`, `requirements/…`, `partitions/…`, `00_hypothesis/…`)
> against **`design/image_store/`**; the roadmap-layer documents
> (`PROCESS.md`, `PROCESS_STRATEGIES.md`, `CONTAINER_STRATEGIES.md`,
> `VERBS.md`, `unit/…`) against **`design/image_store/roadmap/`**. The
> key and the audit deliberately stay in the corpus — they are project
> data, not tooling, and neither is roadmap-specific. Making this
> declaration mechanical rather than prose is the tool's own job
> (§Namespace mechanics).
>
> **Superseded in part 2026-07-23.** The ratified
> `003_VOCABULARY_PIPELINE.md` now governs the producer split into
> `identify`, `define`, and `merge`; occurrence-inventory and
> defined-vocabulary schemas; exact exclusions; definition deduplication;
> manual supplements; merge behavior; and file-set-derived default namespace
> membership. This document remains authoritative for the shared scanner,
> scoring, source positions, and validation baseline. The optional
> definition-source tie-break experiment is isolated in
> `004_DEFINITION_SOURCE_SCORING.md` and is not Production behavior.

## Purpose

Two jobs against one artifact, with opposite failure economics:

| | **Producer** — build the key | **Consumer** — check a document |
|---|---|---|
| Reads | a corpus | one document + the key |
| Finds | *defining* usages | *occurrences* |
| Runs | rarely; output is reviewed and committed | constantly (Step 0, each compile) |
| Optimize | **recall** — a missed definition silently corrupts every later lookup | **precision** — a noisy report goes unread (gap D) |

Same knobs, opposite defaults — which is why they are two commands, not
one with a mode switch.

## Architecture *(new)*

**One library, two thin front-ends.** The library carries markdown parsing,
tokenization, identifier scoring, definition scoring, and key I/O. The
front-ends only differ in scan scope, join direction, and sink.

Sharing the tokenizer and identifier scorer is a **correctness
constraint, not code hygiene**: if the producer sees `DC7` inside
`DC7-knob` and the consumer sees `DC7-knob`, the join fails silently and
emits phantom "undefined reference" reports. Likewise a consumer with a
lower `--identifier-threshold` flags tokens the producer never
considered defining.

Definition scoring lives in the library, not the producer: the consumer
needs it too, at document scope, to answer "is this token glossed *within
this container*?" — the term-closure check inherited from the remediation
history.

**A third operation is deferred:** in-place expansion that rewrites a
document with glosses applied (Solution B step 2, `CONTAINER_STRATEGIES.md`).
Not built now, but the API must support it — see §Positions.

## Commands

> **Implemented snapshot; pipeline superseded 2026-07-23.** The commands in
> this section describe the 2026-07-22 producer. The successor command and
> artifact contracts are in `003_VOCABULARY_PIPELINE.md`.

**Producer — `unslop vocabulary` (alias: `unslop vocab`)**
Scans a corpus, emits the key.

**Consumer** *(provisional: `decode` — `needs-rename`)*
Scans one document, joins against the key, reports each reference as
resolved / undefined / ambiguous. Deferred `--rewrite` sink.

**Human view — `unslop show FILE.csv`**
Renders an aligned table plus all metadata from the generated artifact's
comment header. The CSV itself stays canonical and unpadded: leading spaces
are data to common Python and Node CSV parsers, so human alignment belongs
in this separate view.

### Flags *(carried, except as noted)*

Shared:

| Flag | Meaning |
|---|---|
| `--identifier-threshold N` / `-i N` *(renamed 2026-07-21; was `--filter`/`-f`)* | minimum identifier score; **default 3** (producer-measured; consumer default TBD — §Open) |
| `--verbose` / `-v` | also show matches below the threshold, on a second line |
| `--recursive` / `-r` | recurse into subdirectories |
| `--force` / `-f` *(new; short form freed by the rename, 2026-07-21)* | permit overwriting/truncating an existing output file |
| `--root PATH` / `-R PATH` *(new, 2026-07-23)* | base against which portable source paths are recorded or interpreted; see `002_CONTAINER_RESOLUTION.md` |

Producer only:

| Flag | Meaning |
|---|---|
| `--output FILE` / `-o FILE` *(new, 2026-07-21)* | output file. **Required** for now — a default name may come later. Production accepts `.csv`; a missing or unrecognized extension is an **error**, never a guess |
| `--definition-threshold N` / `-d N` | minimum definition score; **default 3** |
| `--require-capitalization` / `-c` | discard candidates without the capitalization attribute before scoring; all stated requirements must hold when present |
| `--require-number` / `-n` | discard candidates without the number-suffix attribute before scoring |
| `--require-size N` / `-s N` | discard candidates longer than `N` characters before scoring |
| `--include-single-letter` | |
| `--namespace-id ID` *(new, 2026-07-22)* | optional human-approved namespace ID; omission leaves the generated header field empty for adjudication |

Producer takes input filenames or a directory (then `.md` and `.txt`)
as its positional arguments; the output file is named by
`--output`/`-o` *(decided 2026-07-21, reversing a same-day
final-positional-argument ruling — positionals stay reserved for
inputs)*. Alongside the file it prints the console report: identifiers
found on a single line sorted by definition score with score, then a
summary — count and average score.

Directory traversal canonicalizes paths, collapses duplicate inputs, and
sorts the full file list lexicographically. The longest common parent path
shared by every parsed file is the absolute corpus root; all record paths and
`file_set` entries are relative to it. The serialized `file_root` is relative
to an explicit or detected container root when one is available, and otherwise
remains absolute. `design/002_CONTAINER_RESOLUTION.md` governs selection,
serialization, and expansion. Directory inputs are flat unless `--recursive`
is present.

## Identifier detection

Run a markdown parser (the one FIT uses, since this may fold into that
project) and score the **parsed text token**, not a whitespace slice —
effectively every definition writes the ID as `**IN1`, and 63% of the
1,086 reference occurrences in the unit sheets touch punctuation or markup
(`(B-Q7)`, `DC7-knob`, `U7/CA7`, `L1–L4`, `MR5-Light`). A
whitespace-bounded rule sees ~36% of references and no definitions at all.

Production obtains the parser only through the shared library factory,
currently `MarkdownIt().enable("table")`. Both producer and future consumer
must use that factory. Included inline content: ordinary text, link-label
text, and inline code. Excluded: link destinations and titles, images,
fenced/indented code blocks, and raw HTML (attributes and contained text).

Scoring *(carried; tier boundary corrected 2026-07-21)*: all caps **2**;
short, tiered — ≤3 chars **3**, ≤5 **2**, ≤7 **1**; number suffix **2**.
Single-letter all-caps identifiers score **1**. A retest showed recall
indifferent between a ≤2 and ≤3 top tier; 3 is the original spec's value
and the one the worked examples below assume. Exact cutoffs and suffix
handling are **tuning knobs**: expect them to move during
post-implementation testing against recall *and* precision — the rules
here are the measured starting point, not a settled contract.

*(amended)* — two more token shapes, both real and both previously invisible:

- **Internal hyphens.** `B-Q1`…`B-Q9` (the Phase-B partition verdicts in
  `PARTITIONS.md`) are rejected by an `[A-Za-z0-9]+` grammar. Nine IDs, and
  the same omission caused a real misattribution during key construction:
  stripping the `B-` collapses `B-Q7` onto the unrelated `Q7` in
  `requirements/GRILLING_QUEUE.md`. Treat the hyphen as internal and
  **never normalize it away** — the prefix is what disambiguates.
- **Lowercase suffixes.** `X4a`–`X4d` fail *both* "all caps" and "number
  suffix", scoring **2 — below the default filter**. Admit a trailing
  `[a-d]` and let it satisfy the number-suffix rule; the suffix is also
  ignored by the all-caps test (the `X4a` → 7 example assumes this).

Examples: `CA1`, `Q11` → 7 · `X4a` → 7 · `DC12` → 6 · `B-Q7` → 6 ·
`KEEL`, `SKEL` → 4 · `CATALOG`, `INHERIT` → 3 (weak, still admitted).

## Definition detection

The identifier must open a line, a list item, a heading, or a table's
first column.

1. **position** — list item **2**; *(amended)* heading **2**; *(amended)*
   table first column **2**; bare line start **0**
2. surrounded by `**` — **1**
3. followed by `:` `-` `—` — **1**
4. followed by two or more words — **1**

Threshold **3**.

The two position changes are the largest single recall gain — 25 of 43
missed definitions. Headings scored 0, capping them below threshold, which
silently dropped all nine `## B-Qn ✅ —` verdicts plus `X4a`–`X4d`,
`F2`/`F3`, `Q1`–`Q4`, `X3`, `PV0`. Plain table rows (bare ID, no `**`)
reached only 1+0+1 = 2, dropping `L1`–`L13` and `UP1`–`UP5` — 18
definitions in `ROADMAP.md` alone.

Allow intervening status glyphs (`✅`, `⚑`, `⚠️`) before the rule-3
separator: the corpus writes `## B-Q1 ✅ — The nucleus…`.

## Namespaces and precedence *(new)*

Measured: **87 of 159 key identifiers have more than one line scoring ≥3**
(83 across multiple files). That is two different problems, and they need
two different mechanisms.

**~18 are true homographs** — different concepts sharing a token. The
corpus runs two independent `D` numberings (dedup requirements in
`03_deduplication.md`; ordering decisions in `roadmap/ORDERING.md`), two
`C` numberings (roadmap phases in `PROCESS.md`; tagging conventions in
`X3_TAGGING.md`), and three `Q` numberings (B-Q verdicts, C3 research
questions, grilling questions). `unit/007_SIM.md` cites both `D` senses within a
few lines.

→ **Declare the namespace** *(mechanism superseded 2026-07-21 — see
§Namespace mechanics below; the original proposal here was a
`(family × home document) → namespace` config)*. Either way `D5` under
ordering and `D5` under dedup become distinct keys, deterministically.

**~70 are restatements** — one concept stated in several places (`SS1`'s
home in `06_scenes_grouping.md` plus its tagged restatement in
`X3_TAGGING.md`; `PR9` in `INTENT.md` plus its condensed form in
`INTENT_LEDGER.md`).

→ **Source precedence *within* a namespace** collapses these. Branch file
beats `X3_TAGGING`/`GRILLING_QUEUE`; `INTENT.md` beats `INTENT_LEDGER.md`;
`partitions/RISKS.md` is the fuller home for the U and R families.

**Across namespaces nothing collapses.** The consumer reports "`D5` is
ambiguous, two senses" and a human decides. Precedence must never silently
pick a winner across a namespace boundary — that would hide exactly the
collisions this is built to surface.

**Rejected — automatic homograph detection by gloss-text overlap.** Tested:
catches 10 of 12 known homographs but also flags **39 restatements**. Thirty-nine
false positives for ten true positives is the "report full of predictable
spam won't be read" failure gap D warns about. Do not build it.

**Recurring-ambiguity economics — upstream fix identified, deferred
*(new, 2026-07-21)*.** The consumer runs constantly, and the corpus cites
homographs routinely (`unit/007_SIM.md` cites both `D` senses within a few
lines) — so the same "two senses" report re-fires on every run:
exactly the predictable-spam failure gap D names, and the adjudicated
layer as specified has nowhere to record a settled resolution. The fix
is **upstream of the tool, in sheet generation**: build the translation
key *before* generating unit sheets (or scope it to the documents
generated prior to them), then require explicit namespace references in
sheets for every non-default namespace — probably admitting additional
references only from a `requirements` namespace. This cannot land before
the tool exists (the key is its output). Consequence to flag in the
governing process document (`PROCESS_STRATEGIES.md`): the existing unit
sheets will need regeneration or amendment under this rule — which
revisits the 2026-07-20 "sheets are not regenerated" decision recorded
there.

### Namespace mechanics *(decided 2026-07-21)*

> **Historical mechanism.** The artifact identity and dotted-reference syntax
> remain inputs to 003, but 003 now governs how `file_set` membership supplies
> a document's default namespace and what makes that membership invalid.

Namespacing is **mostly a process-level activity**; the tool's share is
small and mechanical. The sheet-side syntax anticipated above is now
specified.

**A namespace is a generated-key artifact.** One producer run covers
one namespace: the input file set is the namespace's extent, and the
output artifact records it, in two places:

1. The **base filename, extensions stripped**, is the namespace's long
   name (`requirements.csv` → `requirements`).
2. A **comment header** at the top of the file:

   ```
   # <file_root>
   # <namespace_id>, <namespace_name>, <file_set…>
   ```

   Example (hypothetical), in a file named `requirements.csv`:

   ```
   # design/image_store
   # REQ, requirements, requirements/REQUIREMENTS.md, requirements/X3_TAGGING.md
   ```

   `file_root` is the base all `file_set` paths are relative to. It may be a
   canonical absolute path or a canonical path relative to a containing root,
   as specified by `design/002_CONTAINER_RESOLUTION.md`.
   `namespace_id` is **generated by or approved by a human** — never
   minted silently by the tool. Production accepts it through optional
   `--namespace-id`; when omitted, the field is empty for later review.

**Process-level usage:**

- Every corpus file declares its **default namespace**.
- A **bare ID** belongs to the declaring file's default namespace.
- A reference outside the default namespace is **prefixed with the
  namespace_id and a dot**: `REQ.C2`, `ROAD.C2`.

**What this buys.** The consumer's join becomes
`(namespace, identifier)` and is deterministic: bare → the document's
default, prefixed → the named namespace. The recurring-ambiguity spam
above dissolves by construction — "ambiguous" survives only as an
authoring error (a bare ID matching nothing in its default namespace,
or an unprefixed cross-namespace citation), which is exactly what a
report *should* carry.

**Consequences — flagged, not filled:**

- The tokenizer must admit the dotted form `NSID.ID` and treat the dot
  as internal — split into (namespace_id, identifier), never strip the
  prefix (the `B-` lesson again).
- Reading an existing namespace ID back on regeneration is deferred; pass
  it explicitly when it is already known.
- **In-file default declarations vs. P3.** New documents (sheets,
  amendments) can carry the declaration natively; the historical
  `requirements/` corpus is case-law, never edited in place (P3,
  `PROCESS_STRATEGIES.md`). For those files the declaration may have to
  live externally — note the artifact `file_set`s already induce a
  file → namespace mapping if every corpus file belongs to exactly one
  namespace. Needs adjudication.
- Where the declaration sits in a conforming document (status block,
  per PROCESS.md conventions?) is process-doc territory, not this
  spec's.

## Output

> **Implemented snapshot; artifact model superseded 2026-07-23.** The
> per-definition generated output below describes the existing producer.
> Inventory, defined-vocabulary, manual-supplement, and merge schemas are
> governed by 003.

**Two layers, never one** *(new; "files" → "layers" 2026-07-21 — the
generated layer is one artifact per namespace)* — enforced at the
process level:

- **generated** — the mechanical harvest, **one artifact per
  namespace** (filename = long name, comment header = id + file set;
  §Namespace mechanics). Regenerated freely; overwriting
  an existing file requires `--force`. Production performs a direct
  truncate-and-write when forced; atomic replacement is deferred.
- **adjudicated** — the human layer: namespace assignments, precedence
  exceptions, hand-seeded entries. Never written by the producer.

The consumer reads both and **reports which layer supplied each
resolution**, so an adjudication gone stale against a re-harvested
glossary surfaces instead of rotting silently. This is the same shape as
`CONTAINER_STRATEGIES.md` step 3 — back up the mechanical output before the
judgment steps, so the judgment stays auditable.

Production emits canonical, unpadded CSV. JSONL is deferred. Per-record
fields *(amended 2026-07-21; carried floor was identifier ·
definition score · origin · line)*: `identifier` · `identifier_score` ·
`definition_score` · `path` · `line` · `begin` · `end`.

**One record per definition found, not per identifier** *(decided
2026-07-21)*: `D1` emits two complete records; grouping by identifier
is the consumer's join-time job. This dissolves the multi-definition
keying question, keeps CSV flat (a row *is* the record), and matches
`TRANSLATION_KEY.csv`'s own shape, so regression comparison stays
row-to-row. Two deliberate exclusions: **no `gloss` field yet** — get a
baseline working first, then experiment with the extraction rule
(§Open) — and **no namespace field at the record level** *(rationale
updated 2026-07-21)* — the namespace is carried once, by the artifact
itself (filename + comment header, §Namespace mechanics); the consumer
stamps it at join time, and repeating it per record would be noise. A
**per-identifier
(grouped) mode is wanted eventually** — likely a third layer over the
library API, not a change to this producer interface (§Open).

### Positions *(new)*

Every definition and every occurrence carries its **position** (`begin`
and `end`), not just a line number. Required by the deferred rewrite, and
independently useful for LLM or tool consumption: a targeted "gloss this
span" is a far cheaper and more precise ask than "gloss this document."

**Resolved — source map (2026-07-22).** FIT's markdown-it parser supplies
zero-based, end-exclusive line maps on block/inline containers, but no
character positions on inline children. Production therefore uses parser
structure and line maps to constrain a shared source-aware scanner, which
maps admitted inline identifiers back to the original decoded source.
`begin` and `end` are zero-based Unicode-character offsets into that exact
source (`end` exclusive); `line` is one-based. Files are read without
newline translation, so CRLF and non-ASCII content retain stable spans.

## Validation

Acceptance target against `TRANSLATION_KEY.csv` (159 distinct identifiers,
164 rows — five identifiers legitimately carry two definitions):

| Configuration | Definitions recovered |
|---|---|
| Original scoring, parsed tokens | 119 / 159 |
| + heading = 2, table row = 2 | 144 / 159 |
| + hyphenated and lowercase-suffixed IDs | **157 / 159** |

The two residual misses are `S1`/`S2`, **not reachable by any ID-anchored
rule**: their founding definition (`00_hypothesis/PROMPTS.md` lines 30–31)
is a bare numbered list under a `Scenarios:` caption where the token never
appears — identity is carried by list position alone. Hand-seed them in the
adjudicated file rather than building positional inference that earns its
keep twice. The tool still behaves correctly, reporting them as referenced
but undefined.

**Precision ≈ 98%.** Of 126 definitions found outside the key, 106 are
genuine vocabulary the key does not cover (it is scoped to sheet-cited IDs
only): 26 `VOCABULARY.md` entries and 80 ID-family definitions no sheet
cites. 7 are strength/process vocabulary; 8 are domain or old-corpus terms
(COCO, EXIF, JPEG, HDD; CV1, SIG, SPLIT, HARD). True junk: `An`, `It`,
`in`, `MNW`, `NEXT`.

**Test files.** `requirements/01_catalog.md` and `VOCABULARY.md` are the
happy path — clean bold bullets, clean bold table — and exercise none of
the failing shapes. Keep them as the regression baseline and add
`ROADMAP.md` (four shapes in one file: ladder table, event table,
numbered-bold list, prose blocks; 17 of the 43 original misses),
`PARTITIONS.md` (headings plus hyphenated IDs; 9 misses), and
`roadmap/ORDERING.md` (the D-family homograph counterpart).

## Open — flagged, not filled

- **Consumer command name — `needs-rename`.** Production settled the
  producer as `unslop vocabulary` with alias `unslop vocab`; `decode`
  remains provisional for the consumer. Recorded so these are not
  re-proposed: **`resolve`** is disqualified — `PROCESS_STRATEGIES.md`
  makes *resolution* the forbidden compile-time act (P1), so naming the
  tool after it actively misleads; **`check`** collides with the CHECK unit
  and the ratified `check` verb in `VERBS.md`; `audit`, `trace`, and
  `closure` are all overloaded in this corpus.
- **Output formats — Production settled 2026-07-22.** Production accepts
  CSV only via `--output`'s extension (missing/unrecognized = error); one
  record per definition (grouping is join-time; CSV stays flat); fields
  `identifier · identifier_score · definition_score · path · line ·
  begin · end`; no namespace field in the generated layer. YAML is out —
  bare all-caps tokens like `NO`/`ON` are YAML booleans, the wrong
  hazard for a corpus of short all-caps identifiers. JSONL is deferred.
  Still open: the
  **`gloss` field** (deferred until a baseline runs; the extraction
  rule needs experimentation — the key's `…`-truncated entries show it
  isn't obvious); the adjudicated file's name and format.
- **Path references — a second consumer check, unbuilt** *(new,
  2026-07-22)*. The consumer resolves *identifiers* against the key;
  it could resolve *paths* against the filesystem in the same pass, and
  the corpus needs it: the 2026-07-22 reorganization broke twelve path
  references in live documents, none findable by grepping for a moved
  filename — one pair had resolved correctly for six days and broke
  silently when its file moved one level down. Measured evidence and the
  full classification: `PATH_AUDIT.md`. The shape is the same problem
  this spec already solves for IDs — **a bare reference whose meaning
  depends on an undeclared default** — and the same `file_root`
  declaration probably serves both, which is the argument for one check
  rather than a separate linter. What makes it non-trivial is the false
  positives, all of them legitimate: targets that do not exist *yet*
  (decision records are born at unit execution, so `unit/DECISIONS.md`
  cites fifteen files that will not exist for months); paths spoken in
  the second person (`CHART.md` telling a unit about *its* `research/`,
  from a document that sits elsewhere); deliberately dead paths (a
  before/after move table); and frozen material that is regenerated or
  never edited. Naive file-relative resolution finds all twelve breaks at
  43 false positives — the gap-D failure exactly. With roots declared,
  anticipated targets marked, and frozen or quotes-paths-as-data
  documents excluded, the residue measured 20 findings, all true. Not adjudicated; the producer arm comes
  first.
- **Per-identifier grouped mode.** Wanted alongside the per-definition
  records — probably a third layer over the library API rather than a
  producer flag. Shape and name undecided.
- **Consumer arm untested — thresholds and validation TBD.** No testing
  has run on the consumer side: its `--filter` default, its
  document-scope definition threshold (the term-closure check
  §Architecture assigns it), and a consumer acceptance target (e.g.
  decode a unit sheet → expected resolved/undefined/ambiguous counts)
  are all unchosen. Awaiting a good key generated by the producer — or a
  known-good key built outside the tool. Until then, §Purpose's
  "opposite defaults" is a design intention, not a measured setting.
- **Sheet namespace references.** The recurring-ambiguity fix
  (§Namespaces) obligates the unit sheets to carry explicit namespace
  references — syntax now decided (`NSID.` dot-prefix + per-file
  default declarations, §Namespace mechanics); still needs its entry in
  `PROCESS_STRATEGIES.md` since it revisits the sheets-not-regenerated
  decision, plus the P3 adjudication for the historical `requirements/`
  corpus (in-file declaration vs. case-law; external mapping via the
  artifact file sets is the candidate).
- **Process vs content vocabulary.** The original spec anticipates an LLM
  pass to separate MUST/SHOULD/CORE/BOUNDARY from content vocabulary.
  Measurement says the set is closed and tiny — seven tokens observed
  (`MUST`, `SHOULD`, `MAY`, `CORE`, `IN`, `OUT`, `STRETCH`; `BOUNDARY` and
  `TBD` plausible), stable since the X3 tagging pass. A stoplist would be
  deterministic and auditable where an LLM pass reintroduces exactly the
  nondeterminism Solution B exists to delete. Not adjudicated.
- **Rewrite mode design.** Deferred. The API carries positions for it; the
  sink, conflict handling, and whether it is a flag or a third front-end
  are undecided.
