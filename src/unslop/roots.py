"""Model portable corpus roots and their containing filesystem boundaries."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import os
from pathlib import Path, PurePosixPath
import subprocess


class RootOrigin(str, Enum):
    """Runtime provenance for a selected container root."""

    EXPLICIT = "explicit"
    GIT = "git"
    FILESYSTEM = "filesystem"


@dataclass(frozen=True)
class ContainerRoot:
    """An absolute boundary for validating, shortening, and expanding paths.

    Attributes:
        path: Existing canonical directory that contains represented paths.
        origin: How this runtime boundary was selected.
    """

    path: Path
    origin: RootOrigin

    def __post_init__(self) -> None:
        """Enforce the canonical container representation."""
        if not isinstance(self.path, Path) or not self.path.is_absolute():
            raise ValueError("container root must be an absolute path")
        if not self.path.exists():
            raise ValueError(f"root does not exist: {self.path}")
        if not self.path.is_dir():
            raise ValueError(f"root is not a directory: {self.path}")
        if self.path.resolve() != self.path:
            raise ValueError(f"container root must be canonical: {self.path}")
        if not isinstance(self.origin, RootOrigin):
            raise ValueError("container root origin must be a RootOrigin")

    @classmethod
    def explicit(
        cls,
        path: Path,
        *,
        containing: Path,
    ) -> ContainerRoot:
        """Create and validate a caller-selected container root.

        Relative root paths are resolved against the caller's working
        directory. The selected directory must contain `containing`.

        Args:
            path: Caller-selected container directory.
            containing: Absolute canonical path that must be inside the root.

        Returns:
            Validated explicit container root.

        Raises:
            ValueError: If either path is invalid or containment fails.
        """
        subject = _containing_path(containing)
        root = cls(path.resolve(), RootOrigin.EXPLICIT)
        if not root.contains(subject):
            raise ValueError(f"corpus root is outside --root: {subject}")
        return root

    @classmethod
    def discover(
        cls,
        *,
        containing: Path,
    ) -> ContainerRoot | None:
        """Discover the Git worktree containing an absolute path.

        Git failure, missing Git, malformed output, and inconsistent
        containment all mean that no portable container was discovered.

        Args:
            containing: Absolute canonical corpus or key location.

        Returns:
            Git worktree root, or `None` when discovery is unavailable.

        Raises:
            ValueError: If `containing` is not absolute and canonical.
        """
        subject = _containing_path(containing)
        try:
            result = subprocess.run(
                ["git", "-C", str(subject), "rev-parse", "--show-toplevel"],
                check=False,
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
                text=True,
            )
        except OSError:
            return None
        if result.returncode != 0:
            return None
        output = result.stdout.rstrip("\r\n")
        if not output or "\n" in output or "\r" in output:
            return None
        candidate = Path(output)
        if not candidate.is_absolute():
            return None
        try:
            root = cls(candidate.resolve(strict=True), RootOrigin.GIT)
        except (OSError, ValueError):
            return None
        return root if root.contains(subject) else None

    @classmethod
    def filesystem(
        cls,
        *,
        containing: Path,
    ) -> ContainerRoot:
        """Return the filesystem anchor containing an absolute path.

        The native anchor is preserved, including Windows drive or UNC roots.

        Args:
            containing: Absolute canonical path whose anchor is selected.

        Returns:
            Filesystem-origin container root.

        Raises:
            ValueError: If `containing` is not absolute and canonical.
        """
        subject = _containing_path(containing)
        return cls(Path(subject.anchor).resolve(), RootOrigin.FILESYSTEM)

    @classmethod
    def for_corpus(
        cls,
        *,
        containing: Path,
        explicit: Path | None = None,
    ) -> ContainerRoot:
        """Select explicit, Git, then filesystem containment.

        Args:
            containing: Absolute canonical corpus root to contain.
            explicit: Optional caller-selected root, resolved strictly before
                automatic discovery.

        Returns:
            Highest-precedence valid container root.

        Raises:
            ValueError: If `containing` or an explicit selection is invalid.
        """
        subject = _containing_path(containing)
        if explicit is not None:
            return cls.explicit(explicit, containing=subject)
        discovered = cls.discover(containing=subject)
        return discovered or cls.filesystem(containing=subject)

    def contains(self, path: Path) -> bool:
        """Return whether an absolute path resolves inside this root.

        Args:
            path: Absolute path to test. It need not exist.

        Returns:
            Whether the resolved path remains within the container.
        """
        if not isinstance(path, Path) or not path.is_absolute():
            return False
        try:
            path.resolve(strict=False).relative_to(self.path)
        except (OSError, ValueError):
            return False
        return True

    def relative_path(self, path: Path) -> Path:
        """Return a contained absolute path relative to this root.

        Existing symlinks are resolved before containment is evaluated.

        Args:
            path: Absolute path contained by this root.

        Returns:
            Canonical relative path, with `.` representing the root itself.

        Raises:
            ValueError: If `path` is relative or escapes the container.
        """
        if not isinstance(path, Path) or not path.is_absolute():
            raise ValueError("contained path must be absolute")
        resolved = path.resolve(strict=False)
        try:
            return resolved.relative_to(self.path)
        except ValueError as error:
            raise ValueError(f"path escapes container root: {path}") from error

    def absolute_path(self, relative: Path) -> Path:
        """Expand a canonical relative path without allowing root escape.

        Args:
            relative: Relative path beneath this root.

        Returns:
            Canonical absolute represented path.

        Raises:
            ValueError: If the input is absolute, traverses upward, or resolves
                outside the container through a symlink.
        """
        if not isinstance(relative, Path) or relative.is_absolute():
            raise ValueError("container path must be relative")
        if ".." in relative.parts:
            raise ValueError(f"path escapes container root: {relative}")
        candidate = (self.path / relative).resolve(strict=False)
        if not self.contains(candidate):
            raise ValueError(f"path escapes container root: {relative}")
        return candidate


@dataclass(frozen=True)
class FileRoot:
    """A canonical serialized base for source paths in a generated key.

    Attributes:
        value: Native absolute path or canonical POSIX-relative path.
    """

    value: str

    def __post_init__(self) -> None:
        """Validate the serialized absolute or relative representation."""
        if not isinstance(self.value, str) or not self.value:
            raise ValueError("file_root must not be empty")
        if "\n" in self.value or "\r" in self.value:
            raise ValueError(
                "file_root must be a canonical absolute or POSIX-relative path"
            )

        path = Path(self.value)
        if path.is_absolute():
            if (
                str(path) != self.value
                or os.path.normpath(self.value) != self.value
            ):
                raise ValueError(
                    "file_root must be a canonical absolute or POSIX-relative path"
                )
            return

        if ".." in PurePosixPath(self.value).parts:
            raise ValueError("file_root must not contain '..'")
        if (
            self.value != "."
            and (
                "\\" in self.value
                or self.value.startswith("./")
                or self.value.endswith("/")
                or "//" in self.value
                or "." in PurePosixPath(self.value).parts
                or PurePosixPath(self.value).as_posix() != self.value
            )
        ):
            raise ValueError(
                "file_root must be a canonical absolute or POSIX-relative path"
            )

    @classmethod
    def parse(cls, value: str) -> FileRoot:
        """Parse and validate a serialized file root.

        Args:
            value: First comment-line value from a generated key.

        Returns:
            Validated file root.

        Raises:
            ValueError: If the value is empty, noncanonical, or traversing.
        """
        return cls(value)

    @classmethod
    def from_corpus_root(
        cls,
        corpus_root: Path,
        *,
        container_root: ContainerRoot,
    ) -> FileRoot:
        """Record an absolute corpus root under its selected container.

        Explicit and Git containers produce a portable relative value.
        Filesystem fallback preserves the canonical absolute corpus root.

        Args:
            corpus_root: Absolute canonical corpus root.
            container_root: Runtime boundary selected for production.

        Returns:
            Serialized absolute or container-relative file root.

        Raises:
            ValueError: If the corpus root is invalid or outside the container.
        """
        subject = _containing_path(corpus_root)
        if container_root.origin is RootOrigin.FILESYSTEM:
            if not container_root.contains(subject):
                raise ValueError(f"path escapes container root: {subject}")
            return cls(str(subject))
        relative = container_root.relative_path(subject)
        return cls(relative.as_posix())

    @property
    def is_absolute(self) -> bool:
        """Return whether the stored value resolves without a container."""
        return Path(self.value).is_absolute()

    def absolute_path(
        self,
        *,
        container_root: ContainerRoot | None = None,
    ) -> Path:
        """Return the absolute corpus root represented by this value.

        Args:
            container_root: Required runtime boundary for relative values.
                Ignored for an absolute value.

        Returns:
            Absolute canonical corpus root.

        Raises:
            ValueError: If a relative value has no container or escapes it.
        """
        if self.is_absolute:
            return Path(self.value)
        if container_root is None:
            raise ValueError("relative file_root requires a container root")
        return container_root.absolute_path(Path(self.value))

    def __str__(self) -> str:
        """Return the canonical serialized value."""
        return self.value


def _containing_path(path: Path) -> Path:
    """Validate an absolute canonical path used for containment selection."""
    if not isinstance(path, Path) or not path.is_absolute():
        raise ValueError("containing path must be absolute")
    if path.resolve(strict=False) != path:
        raise ValueError(f"containing path must be canonical: {path}")
    return path
