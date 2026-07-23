from pathlib import Path

import pytest

from unslop.producer import Corpus, VocabularyProducer
from unslop.vocabulary import DefinitionCriteria


def write(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def test_producer_builds_a_key_and_below_threshold_report(tmp_path):
    first = write(
        tmp_path / "corpus" / "a.md",
        "- **CA1**: A catalog rule\n"
        "- **LongName**: A low-scoring identifier\n",
    )
    second = write(
        tmp_path / "corpus" / "nested" / "b.md",
        "## Q11 — A research question\n",
    )
    corpus = Corpus.discover([second, first, first])

    harvest = VocabularyProducer().produce(
        corpus,
        criteria=DefinitionCriteria(),
        namespace_id="REQ",
        namespace_name="requirements",
    )

    assert corpus.root == tmp_path / "corpus"
    assert corpus.file_set == ("a.md", "nested/b.md")
    assert harvest.key.metadata.namespace_id == "REQ"
    assert harvest.key.metadata.namespace_name == "requirements"
    assert [record.identifier for record in harvest.key.records] == ["CA1", "Q11"]
    assert [
        record.identifier for record in harvest.below_identifier_threshold
    ] == ["LongName"]


def test_corpus_rejects_noncanonical_direct_construction(tmp_path):
    with pytest.raises(ValueError, match="at least one"):
        Corpus(root=tmp_path, files=())

    source = write(tmp_path / "corpus" / "one.md", "- **CA1**: A rule\n")
    with pytest.raises(ValueError, match="sorted and unique"):
        Corpus(root=tmp_path, files=(source, source))
