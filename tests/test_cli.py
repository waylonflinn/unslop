import csv
from pathlib import Path

import pytest

from unslop.cli import main
from unslop.keyfile import read_key


def write(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


@pytest.mark.parametrize("command", ["vocabulary", "vocab"])
def test_vocabulary_command_writes_metadata_and_canonical_csv(tmp_path, command, capsys):
    first = write(tmp_path / "corpus" / "a.md", "- **CA1**: A catalog rule\n")
    second = write(tmp_path / "corpus" / "nested" / "b.md", "## Q11 — A research question\n")
    output = tmp_path / "requirements.csv"

    assert main([command, str(second), str(first), str(first), "-o", str(output)]) == 0

    key = read_key(output)
    assert key.metadata.file_root == str(tmp_path / "corpus")
    assert key.metadata.namespace_id == ""
    assert key.metadata.namespace_name == "requirements"
    assert key.metadata.file_set == ("a.md", "nested/b.md")
    assert [record.identifier for record in key.records] == ["CA1", "Q11"]

    raw_rows = list(csv.reader(output.read_text(encoding="utf-8").splitlines()[2:]))
    assert raw_rows[1][0] == "CA1"
    assert not raw_rows[1][0].startswith(" ")
    assert "2 identifiers" in capsys.readouterr().out


def test_namespace_id_is_optional_but_written_when_supplied(tmp_path):
    source = write(tmp_path / "one.md", "- **CA1**: A catalog rule\n")
    output = tmp_path / "requirements.csv"

    assert main(["vocab", str(source), "-o", str(output), "--namespace-id", "REQ"]) == 0

    assert read_key(output).metadata.namespace_id == "REQ"


def test_show_renders_header_metadata_and_aligned_records(tmp_path, capsys):
    source = write(tmp_path / "one.md", "- **CA1**: A catalog rule\n")
    output = tmp_path / "requirements.csv"
    main(["vocab", str(source), "-o", str(output), "--namespace-id", "REQ"])
    capsys.readouterr()

    assert main(["show", str(output)]) == 0

    shown = capsys.readouterr().out
    assert "File root:" in shown and str(tmp_path) in shown
    assert "Namespace ID:   REQ" in shown
    assert "Namespace:      requirements" in shown
    assert "Files (1):" in shown and "one.md" in shown
    assert "identifier" in shown and "definition_score" in shown and "CA1" in shown


def test_existing_output_requires_force(tmp_path):
    source = write(tmp_path / "one.md", "- **CA1**: A catalog rule\n")
    output = write(tmp_path / "requirements.csv", "keep me")

    with pytest.raises(SystemExit):
        main(["vocab", str(source), "-o", str(output)])
    assert output.read_text() == "keep me"

    assert main(["vocab", str(source), "-o", str(output), "--force"]) == 0
    assert output.read_text().startswith("# ")


def test_directory_scan_is_flat_until_recursive(tmp_path):
    write(tmp_path / "corpus" / "a.md", "- **CA1**: A catalog rule\n")
    write(tmp_path / "corpus" / "nested" / "b.md", "- **Q11**: A research question\n")

    flat = tmp_path / "flat.csv"
    recursive = tmp_path / "recursive.csv"
    main(["vocab", str(tmp_path / "corpus"), "-o", str(flat)])
    main(["vocab", str(tmp_path / "corpus"), "-o", str(recursive), "--recursive"])

    assert [record.identifier for record in read_key(flat).records] == ["CA1"]
    assert [record.identifier for record in read_key(recursive).records] == ["CA1", "Q11"]


def test_verbose_report_uses_below_threshold_harvest(tmp_path, capsys):
    source = write(
        tmp_path / "one.md",
        "- **CA1**: A catalog rule\n"
        "- **LongName**: A low-scoring identifier\n",
    )

    assert main(["vocab", str(source), "-o", str(tmp_path / "key.csv"), "-v"]) == 0

    output = capsys.readouterr().out
    assert "Identifiers: CA1" in output
    assert "Below threshold: LongName" in output
