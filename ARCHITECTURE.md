# Architecture and Object Design

This document governs structural design in Unslop: how responsibilities become
objects, how objects relate, and how to refactor toward that model without
losing behavior. [001_BASIC_CONCEPT.md](design/001_BASIC_CONCEPT.md) remains
authoritative for vocabulary behavior, scoring, and output semantics.
[DOCUMENTATION.md](DOCUMENTATION.md) governs how the resulting public contracts
are documented.

## Objective

Object-oriented design is a means of placing behavior beside the state and
rules it governs. It is not a requirement to turn every function into a class.

Good structure should make the following questions easy to answer:

- Which object owns this rule?
- Where is this invariant enforced?
- Can invalid state be constructed?
- Which changes remain local?
- Can the object be understood and tested without knowing its implementation?
- Would a plain function or immutable value be simpler?

The desired result is a small set of objects whose names and relationships
explain the system.

## Principles

### Model responsibilities, not data containers

A class should represent a coherent role in the domain and enforce the rules of
that role. Avoid passive bags of fields whose decisions live in unrelated
callers.

Value objects are not an exception. A small immutable object is useful when it
gives a concept a name and protects its invariants. `SourceSpan`, for example,
owns the ordering and units of a source range even though its data is small.

### Encapsulate invariants

Keep state valid by construction. Prefer meaningful operations over exposing
fields for callers to coordinate manually.

An object should reject states that cannot participate correctly in the
system. `Corpus` therefore rejects empty, relative, duplicated, unordered, or
out-of-root file sets. `SourceDocument` owns its line index so callers cannot
silently calculate positions under a different newline interpretation.

### Keep responsibilities cohesive

A class should have one focused reason to change. A useful test is whether its
methods operate on the same state under the same rules. If different methods
use unrelated subsets of state, the class probably contains several concepts.

Conversely, do not split one stateful operation into a chain of stateless
classes merely to make each class short. Separation should follow distinct
responsibilities, not line counts.

### Minimize coupling through capabilities

Callers should depend on the smallest behavior they need, not on internal data
or a concrete implementation chosen elsewhere. Keep interfaces narrow and
make dependency direction explicit.

Do not introduce a protocol, abstract base class, repository, strategy, or
factory before there is a real axis of variation or a second implementation.
An abstraction grounded only in anticipated growth is another dependency to
maintain.

### Tell objects what to do

Prefer asking an object to perform an operation over extracting its state and
reimplementing its decisions elsewhere. `SourceDocument.extract(span)` can
validate the span against the document; direct slicing cannot.

This principle also makes ownership visible. One object should clearly own
each decision, mutation, and lifecycle.

### Separate domain policy from infrastructure

Domain rules should not inherently know about argument parsing, console
formatting, or CSV mechanics. Infrastructure should adapt domain objects rather
than duplicate their policy.

In Unslop:

- `vocabulary.py` owns source interpretation and scoring.
- `producer.py` owns file-backed corpus production.
- `keyfile.py` owns canonical CSV persistence.
- `cli.py` adapts command arguments and renders results.

### Preserve useful functions

Pure calculations and stateless formatting often belong in functions. A class
is justified when it owns identity, state, invariants, a lifecycle, or a
coherent collection of behavior. Class-per-function design adds ceremony
without adding a model.

### Abstract from evidence

Extract an abstraction after examples reveal the stable shared idea. Similar
code is evidence to investigate, not proof that the code has the same
responsibility.

Prefer the abstraction that permits deletion. If an abstraction only adds an
interface and forwarding implementation, it has probably not found a concept
yet.

## Textbook Concepts and SOLID

The four common object-oriented concepts are mechanisms and properties, not a
complete design method:

- **Encapsulation** matters because it preserves invariants, not because fields
  have getters and setters.
- **Inheritance** expresses behavioral refinement when a subtype can honor the
  full parent contract. Code reuse alone does not justify it.
- **Polymorphism** lets callers rely on a capability while different objects
  fulfill it. Method overriding and overloading are language mechanisms, not
  the design goal.
- **Abstraction** hides a stable decision or completes a useful concept. Hiding
  complexity speculatively merely relocates it.

SOLID is useful as shared review vocabulary when applied with evidence:

- **Single Responsibility:** seek cohesion and one focused reason to change.
- **Open/Closed:** isolate demonstrated axes of variation; do not manufacture
  extension points for imagined futures.
- **Liskov Substitution:** require every subtype to preserve the base contract.
- **Interface Segregation:** expose small capabilities so consumers do not
  depend on behavior they do not use.
- **Dependency Inversion:** keep high-level policy independent of low-level
  mechanisms. Introduce an abstraction when it creates a stable boundary, not
  for every dependency automatically.

SOLID diagnoses pressure in a design. It does not replace domain modeling,
ownership, invariants, or judgment.

## Inheritance and Composition

“Is-a” and “has-a” are useful candidate tests, not final decisions.

### Inheritance means behavioral refinement

Use inheritance when a subtype is a behavioral refinement of its base type:

- It satisfies every base invariant.
- It accepts every operation promised by the base.
- It preserves or strengthens the base guarantees.
- Callers do not need to detect or accommodate the subtype.
- The relationship is meaningful beyond sharing implementation.

`Definition` inherits from `Occurrence` because every definition is an
identifier occurrence at an exact source position. It adds scores and stronger
meaning without invalidating any occurrence behavior.

A taxonomic statement alone is insufficient. If the subtype cannot honor the
base contract under all valid operations, the apparent “is-a” relationship is
not suitable for code inheritance.

### Composition means independent variation or ownership

Use composition when one object owns or collaborates with another and their
responsibilities can vary independently. “Has-a” identifies possible
containment; independent meaning and variation justify the design.

Do not prefer composition mechanically. If a relationship is genuinely
substitutive, inheritance may express it more directly and economically.

### Relationship guide

| Evidence | Likely structure |
|---|---|
| One concept strengthens another concept's contract | Inheritance |
| A policy or capability varies independently | Composition |
| Several implementations share only a call shape | No shared base yet |
| Code shares implementation but not meaning | Helper or extracted collaborator |
| A stateless class only forwards to another object | Delete or merge it |
| A stable contract has multiple real implementations | Protocol or abstract base |

The short-lived `VocabularyScanner` illustrated the stateless-forwarder case:
it held no state and only constructed `VocabularyScan`. Moving the zero-to-one
analysis into `VocabularyScan(document)` removed a class and produced a more
truthful API.

## Naming as a Structural Test

Names should express the smallest concept that fully fits. Durable code names
should answer what a thing founds, what it completes, and how it differs from
its siblings.

Use naming in both directions:

1. Derive names from the concrete responsibility and invariants.
2. List the domain's salient concepts and ask which object most fully
   represents each one.

When both directions converge, the name is strong. Persistent naming
difficulty is evidence that the object boundary may be wrong.

Examples from this refactor:

- `VocabularyRecord` described storage; `Definition` describes the domain
  object.
- `_Context` was too broad; `DefinitionPosition` states exactly which context
  matters.
- `ScanOptions` described a mechanism; `DefinitionCriteria` describes the
  admission rules.
- `VocabularyScan` earns the scan name because it performs and retains the
  complete analysis.

Avoid vague suffixes such as `Manager`, `Processor`, `Handler`, or `Service`
unless the role truly cannot be named more precisely.

## Current Object Model

```text
CLI
 ├── Corpus.discover(inputs)
 │    └── SourceDocument
 ├── VocabularyProducer.produce(corpus)
 │    ├── VocabularyScan(document)
 │    │    ├── Occurrence
 │    │    └── Definition(Occurrence)
 │    └── VocabularyHarvest
 │         └── VocabularyKey
 │              ├── KeyMetadata
 │              └── Definition...
 └── read_key / write_key
```

### Source model

- `SourceSpan` is an immutable, end-exclusive source range with a one-based
  line.
- `SourceDocument` owns exact decoded text, its source identity, its line
  index, span creation, and validated extraction.

This keeps the raw-coordinate contract in one place and prevents newline or
offset drift.

### Vocabulary analysis

- `DefinitionPosition` represents the Markdown positions that contribute to
  definition eligibility and score.
- `DefinitionCriteria` owns preconditions and thresholds.
- `Occurrence` represents an admitted identifier at a source position.
- `Definition` refines `Occurrence` with identifier and definition scores.
- `VocabularyScan` parses and aligns one document once, then supplies
  occurrence and definition views without reparsing.

The analysis object separates expensive interpretation from policy selection:
the same scan may apply different criteria while retaining one Markdown
interpretation.

### Corpus production

- `Corpus` owns the canonical file set, common root, traversal policy, and exact
  source reads.
- `VocabularyProducer` coordinates one scan per document and builds a generated
  key. It does not print or persist.
- `VocabularyHarvest` carries the generated key and below-threshold diagnostic
  evidence.

### Artifact and front-end boundaries

- `VocabularyKey` and `KeyMetadata` model the generated artifact.
- `keyfile.py` translates that model to and from canonical CSV.
- `cli.py` translates command-line arguments into domain objects, enforces
  output-file policy, and renders summaries or human-readable tables.
- `__init__.py` is the deliberate public library surface.

Dependency direction should remain:

```text
cli -> producer -> vocabulary
 |        |
 |        -> keyfile -> vocabulary
 -> keyfile
```

The vocabulary layer must not import the producer, key persistence, or CLI.

## Refactoring Method

### 1. Establish the contract

Write or strengthen tests before moving behavior. Capture:

- Public behavior and ordering.
- Invariants and failure conditions.
- Boundary cases.
- Exact source coordinates where applicable.
- Measured integration targets.

For vocabulary changes, the unit suite is necessary but not sufficient. Run
the Image Store acceptance script and preserve 157 of 159 hand-key identifiers,
with only `S1` and `S2` missing, unless the governing design is deliberately
revised.

### 2. Map the existing responsibilities

Trace state and decisions through the call graph. Identify repeated parameter
groups, duplicated calculations, implicit lifecycles, and rules enforced by
callers.

Do not begin by inventing classes. Begin by identifying ownership.

### 3. Introduce value objects and invariants

Move coherent data and its validation together. Keep construction strict so
later operations can rely on valid state.

### 4. Choose relationships explicitly

Apply behavioral substitutability for inheritance and independent variation
for composition. Record why a relationship exists; do not use inheritance only
to reuse code or composition only because it is the safer slogan.

### 5. Move behavior toward its owner

Replace orchestration that asks for state and decides elsewhere with operations
on the responsible object. Keep edges thin.

### 6. Preserve behavior while changing structure

Avoid mixing scoring, parser, or output changes into a structural refactor.
Run focused tests after each slice and the complete suite after meaningful
changes.

### 7. Keep compatibility only when it serves a consumer

Compatibility aliases, forwarding functions, and deprecated layers have a
maintenance cost. Retain them when known consumers need a migration path.
Delete them when the library is new or all consumers can move together.

### 8. Remove abstractions disproved by the result

Render the API documentation and read it as a consumer. Awkward constructors,
empty classes, private parameters, or repetitive names often expose structural
mistakes that source-level review misses.

### 9. Update all authority surfaces

Update:

- Public exports.
- Tests.
- `AGENTS.md` and this guide when ownership changes.
- README examples.
- Source docstrings and Griffonner inputs.
- Generated documentation.
- External validation scripts that consume the public API.

Then search for stale names and run `git diff --check`.

## Common Failure Modes

- **Anemic domain objects:** data classes whose rules remain in callers.
- **God objects:** one scanner or manager that parses, scores, persists, and
  renders.
- **Class-per-function design:** stateless wrappers with no owned concept.
- **Speculative interfaces:** protocols or base classes created before a real
  second implementation.
- **Implementation inheritance:** subclasses coupled only to reuse private
  machinery.
- **Persistence-shaped domain names:** calling a definition a record because it
  is eventually serialized.
- **Leaky front-ends:** CLI code that reconstructs parser or scoring policy.
- **Compatibility clutter:** old surfaces retained without actual consumers.
- **Dogmatic composition:** replacing an honest subtype with delegation merely
  to avoid inheritance.

## Review Checklist

Before accepting an architectural change, ask:

- Does every class own a coherent responsibility?
- Are its invariants enforced at construction or at the operation boundary?
- Is inheritance behaviorally substitutable?
- Does composition represent genuine ownership or independent variation?
- Is every abstraction supported by present evidence?
- Could any class become a function, or any forwarding class disappear?
- Are domain rules independent of CLI and persistence details?
- Does the public vocabulary describe domain concepts rather than mechanisms?
- Can a consumer use the API without knowing private implementation details?
- Do unit tests and measured corpus validation still pass?
- Are exports, docs, examples, and external scripts synchronized?
