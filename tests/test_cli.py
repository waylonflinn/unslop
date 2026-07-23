import csv
from pathlib import Path
import shutil
import subprocess

import pytest

from unslop.cli import main
from unslop.keyfile import KeyMetadata, read_key
from unslop.roots import FileRoot


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
    assert key.metadata.file_root == FileRoot.parse(str(tmp_path / "corpus"))
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


def test_read_key_rejects_invalid_serialized_file_root(tmp_path):
    key = tmp_path / "invalid.csv"
    key.write_text(
        "# ../escape\n"
        "# ,requirements,one.md\n"
        "identifier,identifier_score,definition_score,path,line,begin,end\n",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match=r"must not contain '\.\.'"):
        read_key(key)


def test_key_metadata_requires_validated_file_root():
    with pytest.raises(ValueError, match="must be a FileRoot"):
        KeyMetadata(  # type: ignore[arg-type]
            file_root="/absolute-but-unvalidated",
            namespace_id="",
            namespace_name="requirements",
            file_set=("one.md",),
        )


@pytest.mark.parametrize("root_option", ["--root", "-R"])
def test_explicit_root_records_portable_file_root(
    tmp_path, root_option, capsys
):
    source = write(
        tmp_path / "container" / "corpus" / "one.md",
        "- **CA1**: A catalog rule\n",
    )
    output = tmp_path / "requirements.csv"

    assert main(
        [
            "vocab",
            str(source),
            "-o",
            str(output),
            root_option,
            str(tmp_path / "container"),
        ]
    ) == 0

    key = read_key(output)
    assert key.metadata.file_root == FileRoot.parse("corpus")
    assert key.metadata.file_set == ("one.md",)
    assert key.records[0].path == "one.md"
    capsys.readouterr()
    assert main(["show", str(output)]) == 0
    assert "File root:      corpus" in capsys.readouterr().out


@pytest.mark.parametrize(
    ("root_factory", "message"),
    [
        (lambda tmp_path: tmp_path / "missing", "root does not exist"),
        (
            lambda tmp_path: write(tmp_path / "root.txt", "not a directory"),
            "not a directory",
        ),
        (lambda tmp_path: tmp_path / "outside", "outside --root"),
    ],
)
def test_invalid_explicit_root_is_a_command_error(
    tmp_path, root_factory, message, capsys
):
    source = write(
        tmp_path / "container" / "corpus" / "one.md",
        "- **CA1**: A catalog rule\n",
    )
    outside = tmp_path / "outside"
    outside.mkdir()
    root = root_factory(tmp_path)

    with pytest.raises(SystemExit):
        main(
            [
                "vocab",
                str(source),
                "-o",
                str(tmp_path / "requirements.csv"),
                "--root",
                str(root),
            ]
        )

    assert message in capsys.readouterr().err


def test_relative_explicit_root_is_resolved_from_invocation_directory(
    tmp_path, monkeypatch
):
    source = write(
        tmp_path / "container" / "corpus" / "one.md",
        "- **CA1**: A catalog rule\n",
    )
    monkeypatch.chdir(tmp_path)
    output = tmp_path / "requirements.csv"

    assert main(
        [
            "vocab",
            str(source),
            "-o",
            str(output),
            "--root",
            "container",
        ]
    ) == 0

    assert read_key(output).metadata.file_root == FileRoot.parse("corpus")


def test_vocabulary_help_documents_root_option(capsys):
    with pytest.raises(SystemExit) as exit_info:
        main(["vocab", "--help"])

    assert exit_info.value.code == 0
    help_text = capsys.readouterr().out
    assert "--root PATH" in help_text
    assert "-R PATH" in help_text
    assert "base against which portable source paths are recorded" in help_text


def test_git_root_is_detected_from_corpus_and_explicit_root_wins(tmp_path):
    if shutil.which("git") is None:
        pytest.skip("Git is not installed")
    worktree = tmp_path / "worktree"
    source = write(
        worktree / "docs" / "corpus" / "one.md",
        "- **CA1**: A catalog rule\n",
    )
    subprocess.run(
        ["git", "init", "-q", str(worktree)],
        check=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )

    automatic = tmp_path / "automatic.csv"
    explicit = tmp_path / "explicit.csv"
    assert main(["vocab", str(source), "-o", str(automatic)]) == 0
    assert main(
        [
            "vocab",
            str(source),
            "-o",
            str(explicit),
            "--root",
            str(tmp_path),
        ]
    ) == 0

    assert read_key(automatic).metadata.file_root == FileRoot.parse(
        "docs/corpus"
    )
    assert read_key(explicit).metadata.file_root == FileRoot.parse(
        "worktree/docs/corpus"
    )


def test_git_root_selection_is_independent_of_cwd_and_output_path(
    tmp_path, monkeypatch
):
    if shutil.which("git") is None:
        pytest.skip("Git is not installed")
    worktree = tmp_path / "worktree"
    source = write(
        worktree / "docs" / "one.md",
        "- **CA1**: A catalog rule\n",
    )
    subprocess.run(
        ["git", "init", "-q", str(worktree)],
        check=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    first_cwd = tmp_path / "first"
    second_cwd = tmp_path / "second"
    first_cwd.mkdir()
    second_cwd.mkdir()
    first_output = first_cwd / "first.csv"
    second_output = second_cwd / "nested" / "second.csv"

    monkeypatch.chdir(first_cwd)
    assert main(["vocab", str(source), "-o", str(first_output)]) == 0
    monkeypatch.chdir(second_cwd)
    assert main(["vocab", str(source), "-o", str(second_output)]) == 0

    assert read_key(first_output).metadata.file_root == FileRoot.parse("docs")
    assert (
        read_key(second_output).metadata.file_root
        == read_key(first_output).metadata.file_root
    )
