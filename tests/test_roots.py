from pathlib import Path
import shutil
import subprocess

import pytest

from unslop.roots import ContainerRoot, FileRoot, RootOrigin


def test_container_root_rejects_invalid_construction(tmp_path):
    container = tmp_path / "container"
    container.mkdir()
    file_path = tmp_path / "file"
    file_path.write_text("not a directory", encoding="utf-8")

    with pytest.raises(ValueError, match="absolute"):
        ContainerRoot(Path("container"), RootOrigin.EXPLICIT)
    with pytest.raises(ValueError, match="exist"):
        ContainerRoot(tmp_path / "missing", RootOrigin.EXPLICIT)
    with pytest.raises(ValueError, match="directory"):
        ContainerRoot(file_path, RootOrigin.EXPLICIT)
    with pytest.raises(ValueError, match="canonical"):
        ContainerRoot(container / "..", RootOrigin.EXPLICIT)
    with pytest.raises(ValueError, match="RootOrigin"):
        ContainerRoot(container, "explicit")  # type: ignore[arg-type]


def test_explicit_root_requires_containment(tmp_path):
    container = tmp_path / "container"
    corpus = container / "corpus"
    outside = tmp_path / "outside"
    corpus.mkdir(parents=True)
    outside.mkdir()

    selected = ContainerRoot.explicit(container, containing=corpus)

    assert selected == ContainerRoot(container, RootOrigin.EXPLICIT)
    with pytest.raises(ValueError, match="outside --root"):
        ContainerRoot.explicit(container, containing=outside)


def test_git_discovery_finds_real_worktree(tmp_path):
    if shutil.which("git") is None:
        pytest.skip("Git is not installed")
    worktree = tmp_path / "worktree"
    corpus = worktree / "docs"
    corpus.mkdir(parents=True)
    subprocess.run(
        ["git", "init", "-q", str(worktree)],
        check=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )

    selected = ContainerRoot.discover(containing=corpus)

    assert selected == ContainerRoot(worktree.resolve(), RootOrigin.GIT)


def test_git_discovery_failures_are_optional(tmp_path, monkeypatch):
    corpus = tmp_path / "corpus"
    corpus.mkdir()

    monkeypatch.setattr(
        subprocess,
        "run",
        lambda *args, **kwargs: subprocess.CompletedProcess(args[0], 1, "", ""),
    )
    assert ContainerRoot.discover(containing=corpus) is None

    def missing_git(*args, **kwargs):
        raise FileNotFoundError

    monkeypatch.setattr(subprocess, "run", missing_git)
    assert ContainerRoot.discover(containing=corpus) is None


@pytest.mark.parametrize("output", ["", "relative\n", "/one\n/two\n"])
def test_git_discovery_rejects_malformed_output(tmp_path, monkeypatch, output):
    corpus = tmp_path / "corpus"
    corpus.mkdir()
    monkeypatch.setattr(
        subprocess,
        "run",
        lambda *args, **kwargs: subprocess.CompletedProcess(
            args[0], 0, output, ""
        ),
    )

    assert ContainerRoot.discover(containing=corpus) is None


def test_git_discovery_rejects_inconsistent_output(tmp_path, monkeypatch):
    corpus = tmp_path / "corpus"
    outside = tmp_path / "outside"
    corpus.mkdir()
    outside.mkdir()
    monkeypatch.setattr(
        subprocess,
        "run",
        lambda *args, **kwargs: subprocess.CompletedProcess(
            args[0], 0, f"{outside}\n", ""
        ),
    )

    assert ContainerRoot.discover(containing=corpus) is None


def test_root_selection_precedence(tmp_path, monkeypatch):
    explicit = tmp_path / "explicit"
    corpus = explicit / "git" / "corpus"
    explicit.mkdir()
    corpus.mkdir(parents=True)

    def discovery_must_not_run(cls, *, containing):
        raise AssertionError("explicit selection must precede discovery")

    monkeypatch.setattr(
        ContainerRoot, "discover", classmethod(discovery_must_not_run)
    )
    assert ContainerRoot.for_corpus(
        containing=corpus, explicit=explicit
    ).origin is RootOrigin.EXPLICIT

    git_root = explicit / "git"
    monkeypatch.setattr(
        ContainerRoot,
        "discover",
        classmethod(
            lambda cls, *, containing: cls(git_root.resolve(), RootOrigin.GIT)
        ),
    )
    assert ContainerRoot.for_corpus(containing=corpus).origin is RootOrigin.GIT

    monkeypatch.setattr(
        ContainerRoot,
        "discover",
        classmethod(lambda cls, *, containing: None),
    )
    fallback = ContainerRoot.for_corpus(containing=corpus)
    assert fallback.origin is RootOrigin.FILESYSTEM
    assert fallback.path == Path(corpus.anchor)


def test_contained_path_conversion_round_trips_and_maps_root_to_dot(tmp_path):
    container_path = tmp_path / "container"
    nested = container_path / "docs" / "corpus"
    nested.mkdir(parents=True)
    container = ContainerRoot(container_path, RootOrigin.EXPLICIT)

    relative = container.relative_path(nested)

    assert relative == Path("docs/corpus")
    assert container.absolute_path(relative) == nested
    assert container.relative_path(container_path) == Path(".")
    assert container.absolute_path(Path(".")) == container_path


def test_contained_path_conversion_rejects_traversal_and_symlink_escape(tmp_path):
    container_path = tmp_path / "container"
    outside = tmp_path / "outside"
    container_path.mkdir()
    outside.mkdir()
    container = ContainerRoot(container_path, RootOrigin.EXPLICIT)

    with pytest.raises(ValueError, match="relative"):
        container.absolute_path(outside)
    with pytest.raises(ValueError, match="escapes"):
        container.absolute_path(Path("../outside"))

    link = container_path / "escape"
    try:
        link.symlink_to(outside, target_is_directory=True)
    except OSError:
        pytest.skip("symlinks are unavailable")
    with pytest.raises(ValueError, match="escapes"):
        container.absolute_path(Path("escape"))
    with pytest.raises(ValueError, match="contained"):
        container.relative_path(link)


@pytest.mark.parametrize("value", [".", "docs", "design/image_store"])
def test_file_root_parses_canonical_relative_values(value):
    root = FileRoot.parse(value)

    assert str(root) == value
    assert not root.is_absolute


def test_file_root_parses_canonical_absolute_value(tmp_path):
    value = str(tmp_path.resolve())
    root = FileRoot.parse(value)

    assert str(root) == value
    assert root.is_absolute
    assert root.absolute_path() == tmp_path.resolve()


def test_absolute_file_root_parsing_does_not_resolve_symlinks(tmp_path):
    target = tmp_path / "target"
    target.mkdir()
    link = tmp_path / "link"
    try:
        link.symlink_to(target, target_is_directory=True)
    except OSError:
        pytest.skip("symlinks are unavailable")

    root = FileRoot.parse(str(link))

    assert root.absolute_path() == link


@pytest.mark.parametrize(
    "value",
    [
        "",
        "docs\nother",
        "./docs",
        "docs/",
        "docs//other",
        "../docs",
        "a/../b",
        "/a/../b",
    ],
)
def test_file_root_rejects_invalid_values(value):
    with pytest.raises(ValueError):
        FileRoot.parse(value)


def test_relative_file_root_requires_container(tmp_path):
    root = FileRoot.parse("docs")

    with pytest.raises(ValueError, match="requires a container root"):
        root.absolute_path()

    container = ContainerRoot(tmp_path.resolve(), RootOrigin.EXPLICIT)
    assert root.absolute_path(container_root=container) == tmp_path / "docs"


def test_file_root_representation_depends_on_container_origin(tmp_path):
    corpus = tmp_path / "container" / "docs"
    corpus.mkdir(parents=True)
    explicit = ContainerRoot(tmp_path / "container", RootOrigin.EXPLICIT)
    git = ContainerRoot(tmp_path / "container", RootOrigin.GIT)
    filesystem = ContainerRoot.filesystem(containing=corpus)

    assert str(
        FileRoot.from_corpus_root(corpus, container_root=explicit)
    ) == "docs"
    assert str(FileRoot.from_corpus_root(corpus, container_root=git)) == "docs"
    assert str(
        FileRoot.from_corpus_root(corpus, container_root=filesystem)
    ) == str(corpus)
