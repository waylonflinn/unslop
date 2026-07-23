"""Build generated vocabulary keys from file-backed prose corpora."""

from __future__ import annotations

from dataclasses import dataclass, replace
import os
from pathlib import Path
from typing import Iterator, Sequence

from .keyfile import KeyMetadata, VocabularyKey
from .roots import ContainerRoot, FileRoot
from .vocabulary import (
    Definition,
    DefinitionCriteria,
    SourceDocument,
    VocabularyScan,
)


SUPPORTED_INPUTS = frozenset({".md", ".txt"})


@dataclass(frozen=True)
class Corpus:
    """A canonical, ordered set of source documents under one file root.

    Attributes:
        root: Longest parent path shared by every source file.
        files: Unique absolute source paths in lexicographic order.
    """

    root: Path
    files: tuple[Path, ...]

    def __post_init__(self) -> None:
        """Enforce the canonical corpus representation."""
        if not self.files:
            raise ValueError("a corpus must contain at least one source file")
        if not self.root.is_absolute() or any(
            not path.is_absolute() for path in self.files
        ):
            raise ValueError("corpus root and files must be absolute paths")
        if self.files != tuple(sorted(set(self.files), key=str)):
            raise ValueError("corpus files must be sorted and unique")
        try:
            for path in self.files:
                path.relative_to(self.root)
        except ValueError as error:
            raise ValueError("every corpus file must be under its root") from error

    @classmethod
    def discover(
        cls, inputs: Sequence[Path], recursive: bool = False
    ) -> Corpus:
        """Resolve input files and directories into a corpus.

        Directory inputs are flat unless recursion is requested. Only Markdown
        and text files are admitted.

        Args:
            inputs: Files and directories supplied by a caller.
            recursive: Whether directory discovery includes descendants.

        Returns:
            Canonical corpus with a common root.

        Raises:
            ValueError: If an input is missing, a file type is unsupported, or
                no documents are found.
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
                    if candidate.is_file()
                    and candidate.suffix.lower() in SUPPORTED_INPUTS
                )
            else:
                raise ValueError(f"input does not exist: {supplied}")
        if not files:
            raise ValueError("no .md or .txt input files found")

        ordered = tuple(sorted(files, key=str))
        root = Path(os.path.commonpath([str(path.parent) for path in ordered]))
        return cls(root=root, files=ordered)

    @property
    def file_set(self) -> tuple[str, ...]:
        """Return source paths relative to the corpus root."""
        return tuple(path.relative_to(self.root).as_posix() for path in self.files)

    def documents(self) -> Iterator[SourceDocument]:
        """Read each source exactly, preserving newline characters.

        Yields:
            Documents in canonical file order, identified relative to `root`.

        Raises:
            OSError: If a source cannot be opened or read.
        """
        for path in self.files:
            with path.open("r", encoding="utf-8", newline="") as handle:
                text = handle.read()
            yield SourceDocument(
                path=Path(path.relative_to(self.root).as_posix()),
                text=text,
            )


@dataclass(frozen=True)
class VocabularyHarvest:
    """A generated key and its optional below-threshold diagnostic evidence.

    Attributes:
        key: Canonical generated vocabulary key.
        below_identifier_threshold: Definitions rejected only by the active
            identifier threshold, ordered by source position.
    """

    key: VocabularyKey
    below_identifier_threshold: tuple[Definition, ...]


class VocabularyProducer:
    """Produce one generated vocabulary key from a corpus."""

    def produce(
        self,
        corpus: Corpus,
        *,
        criteria: DefinitionCriteria | None = None,
        namespace_id: str = "",
        namespace_name: str,
        container_root: ContainerRoot | None = None,
    ) -> VocabularyHarvest:
        """Harvest definitions and build their generated key.

        Each document is parsed once. The retained analysis supplies both the
        admitted records and below-identifier-threshold diagnostics.

        Args:
            corpus: Canonical source corpus.
            criteria: Definition preconditions and thresholds. Uses Production
                defaults when omitted.
            namespace_id: Optional human-approved namespace identifier.
            namespace_name: Long namespace name for the generated artifact.
            container_root: Runtime boundary used to record a portable root.
                When omitted, metadata preserves the absolute corpus root.

        Returns:
            Generated key and diagnostic evidence.
        """
        active = criteria or DefinitionCriteria()
        records: list[Definition] = []
        below: list[Definition] = []
        lower = replace(active, identifier_threshold=0)

        for document in corpus.documents():
            scan = VocabularyScan(document)
            records.extend(scan.definitions(active))
            if active.identifier_threshold > 0:
                below.extend(
                    definition
                    for definition in scan.definitions(lower)
                    if definition.identifier_score < active.identifier_threshold
                )

        records.sort(key=lambda item: (item.path, item.begin, item.identifier))
        below.sort(key=lambda item: (item.path, item.begin, item.identifier))
        selected_root = container_root or ContainerRoot.filesystem(
            containing=corpus.root
        )
        metadata = KeyMetadata(
            file_root=FileRoot.from_corpus_root(
                corpus.root,
                container_root=selected_root,
            ),
            namespace_id=namespace_id,
            namespace_name=namespace_name,
            file_set=corpus.file_set,
        )
        return VocabularyHarvest(
            key=VocabularyKey(metadata, tuple(records)),
            below_identifier_threshold=tuple(below),
        )
