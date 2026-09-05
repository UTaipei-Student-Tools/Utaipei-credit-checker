"""Build a deterministic, credential-free bundle for the existing HF Space."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import stat
from collections.abc import Mapping, Sequence
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]

# Runtime and public audit sources only.  Tests, local environments, student
# handbooks, working notes, credentials, screenshots, and caches are excluded
# by construction instead of relying on an ignore pattern during upload.
ROOT_FILES = (
    "README.md",
    "requirements.txt",
    "pyproject.toml",
    "app.py",
    "allocation_engine.py",
    "application_resolution.py",
    "audit_export.py",
    "course_input_adapter.py",
    "credit_engine.py",
    "curriculum_registry.py",
    "decision_snapshot.py",
    "equivalency_audit.py",
    "equivalency_ui.py",
    "graduation_service.py",
    "handbook_rules.py",
    "input_confirmation.py",
    "lieflat_progress_chart.py",
    "pdf_parser.py",
    "policy_audit.py",
    "portal_scope.py",
    "public_course_catalog.py",
    "data/public_course_catalog.json",
    "report_renderer.py",
    "rules_config.json",
    "scraper.py",
    "sidebar.py",
    "snapshot_exports.py",
    "snapshot_projection.py",
    "snapshot_renderer.py",
    "ui_components.py",
    ".streamlit/config.toml",
    "static/manifest-v2.webmanifest",
    "static/icons/ut-graduation-v2-source.png",
    "static/icons/ut-graduation-v2-512.png",
    "static/icons/ut-graduation-v2-32.png",
    "static/icons/ut-graduation-v2-192.png",
    "static/icons/ut-graduation-v2-180.png",
    "static/icons/ut-credit-planner-512.png",
    "static/icons/ut-credit-planner-192.png",
    "static/icons/ut-credit-planner-1024.png",
    "static/icons/favicon-32.png",
    "static/icons/apple-touch-icon.png",
    "streamlit_bootstrap/pyproject.toml",
    "streamlit_bootstrap/sitecustomize.py",
    "streamlit_bootstrap/utaipei_pwa_bootstrap/__init__.py",
    "streamlit_bootstrap/utaipei_pwa_bootstrap/patch.py",
)
# Production bundles never recursively include a directory.  The optional
# tree_roots argument remains only for explicit programmatic fixture callers.
TREE_ROOTS: tuple[str, ...] = ()

# Research notes are an explicit public-audit surface.  Do not recursively
# include the directory: a newly-created local note must never become a HF
# deployment artifact by accident.
PUBLIC_RESEARCH_FILES = (
    "research/apc_cs_handbook_matrix_111_115.md",
    "research/apc_double_major_equivalency.md",
    "research/double_major_timing_rules.md",
    "research/math_earth_handbook_matrix_111_115.md",
    "research/minor_program_matrix_111_115.md",
    "research/university_common_policy_111_115.md",
)

_REPARSE_POINT_ATTRIBUTE = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x0400)


def _absolute_path(path: Path) -> Path:
    """Return an absolute lexical path without resolving links."""

    return Path(os.path.abspath(os.fspath(path)))


def _lstat(path: Path):
    try:
        return os.lstat(os.fspath(path))
    except OSError as error:
        raise ValueError(f"bundle path is unavailable: {path.name}") from error


def _has_reparse_attribute(info: object) -> bool:
    try:
        attributes = int(getattr(info, "st_file_attributes", 0) or 0)
    except (TypeError, ValueError, OverflowError):
        attributes = 0
    return bool(attributes & _REPARSE_POINT_ATTRIBUTE)


def _is_link_or_reparse(info: object) -> bool:
    return stat.S_ISLNK(getattr(info, "st_mode", 0)) or _has_reparse_attribute(info)


def _assert_no_link_ancestry(path: Path, *, stop: Path | None = None) -> None:
    """Reject symlink/reparse ancestors without resolving or traversing them."""

    current = _absolute_path(path)
    boundary = _absolute_path(stop) if stop is not None else None
    if boundary is not None:
        try:
            current.relative_to(boundary)
        except ValueError as error:
            raise ValueError("bundle path escaped its allowed root") from error

    while True:
        info = _lstat(current)
        if _is_link_or_reparse(info):
            raise ValueError(f"bundle path cannot use a symlink or reparse point: {current.name}")
        if boundary is not None and current == boundary:
            return
        parent = current.parent
        if parent == current:
            if boundary is not None:
                raise ValueError("bundle path did not reach its allowed root")
            return
        current = parent


def _assert_regular_file(path: Path, info: object) -> None:
    if _is_link_or_reparse(info) or not stat.S_ISREG(getattr(info, "st_mode", 0)):
        raise ValueError(f"bundle source is not a regular file: {path.name}")


def _assert_regular_directory(path: Path, info: object) -> None:
    if _is_link_or_reparse(info) or not stat.S_ISDIR(getattr(info, "st_mode", 0)):
        raise ValueError(f"bundle tree is not a regular directory: {path.name}")


def _file_identity(info: object) -> tuple[object, ...]:
    """Capture portable identity/metadata useful for Windows TOCTOU checks."""

    return tuple(
        getattr(info, name, None)
        for name in (
            "st_dev",
            "st_ino",
            "st_size",
            "st_mtime_ns",
            "st_ctime_ns",
            "st_file_attributes",
        )
    )


def _node_identity(info: object) -> tuple[object, ...]:
    """Capture stable identity fields for a created staging directory."""

    return tuple(
        getattr(info, name, None)
        for name in ("st_dev", "st_ino", "st_file_attributes")
    )


def _safe_root(root: Path) -> Path:
    root = _absolute_path(Path(root))
    _assert_no_link_ancestry(root)
    _assert_regular_directory(root, _lstat(root))
    return root


def _contained_file(root: Path, candidate: Path) -> Path:
    root = _absolute_path(root)
    candidate = _absolute_path(candidate)
    try:
        candidate.relative_to(root)
    except ValueError as error:
        raise ValueError("bundle source escaped the project root") from error
    _assert_no_link_ancestry(candidate, stop=root)
    _assert_regular_file(candidate, _lstat(candidate))
    return candidate


def _tree_files(root: Path, directory: Path) -> list[Path]:
    """Walk only regular directories; never follow links or reparse points."""

    collected: list[Path] = []
    pending = [directory]
    while pending:
        current = pending.pop()
        _assert_no_link_ancestry(current, stop=root)
        _assert_regular_directory(current, _lstat(current))
        try:
            entries = sorted(os.scandir(os.fspath(current)), key=lambda item: item.name)
        except OSError as error:
            raise ValueError(f"bundle tree cannot be read: {current.name}") from error
        for entry in entries:
            candidate = _absolute_path(Path(entry.path))
            _assert_no_link_ancestry(candidate, stop=root)
            info = _lstat(candidate)
            if _is_link_or_reparse(info):
                raise ValueError(f"bundle tree cannot contain a symlink or reparse point: {candidate.name}")
            if stat.S_ISDIR(getattr(info, "st_mode", 0)):
                pending.append(candidate)
                continue
            if not stat.S_ISREG(getattr(info, "st_mode", 0)):
                raise ValueError(f"bundle tree entry is not a regular file: {candidate.name}")
            if candidate.suffix.casefold() in {".pyc", ".pyo"} or "__pycache__" in candidate.parts:
                continue
            collected.append(candidate)
    return collected


def _public_research_paths(root: Path, public_research_files: Sequence[str]) -> list[Path]:
    """Resolve exactly the explicit public research allowlist."""

    if not public_research_files:
        return []
    research_dir = _absolute_path(root / "research")
    # Small fixture roots used by unit tests may not have a research directory;
    # the real deployment root does.  A present directory is always checked.
    if not os.path.lexists(os.fspath(research_dir)):
        return []
    _assert_no_link_ancestry(research_dir, stop=root)
    _assert_regular_directory(research_dir, _lstat(research_dir))
    paths = []
    for relative in public_research_files:
        relative_text = Path(relative).as_posix()
        if not relative_text.startswith("research/") or not relative_text.casefold().endswith(".md"):
            raise ValueError("public research entries must be allowlisted Markdown files under research/")
        paths.append(_contained_file(root, root / relative_text))
    return paths


def collect_bundle_files(
    root: Path = PROJECT_ROOT,
    *,
    root_files: Sequence[str] = ROOT_FILES,
    tree_roots: Sequence[str] = TREE_ROOTS,
    public_research_files: Sequence[str] = PUBLIC_RESEARCH_FILES,
) -> tuple[Path, ...]:
    """Return the exact allowlisted files that may be uploaded."""

    root = _safe_root(Path(root))
    collected: list[Path] = []
    for relative in root_files:
        collected.append(_contained_file(root, root / relative))
    for relative in tree_roots:
        # Older callers may still pass research here.  It is deliberately
        # ignored rather than recursively traversed; only the explicit public
        # research list below can enter a bundle.
        if Path(relative).as_posix().rstrip("/").casefold() == "research":
            continue
        directory = _absolute_path(root / relative)
        try:
            directory.relative_to(root)
        except ValueError as error:
            raise ValueError("bundle tree escaped the project root") from error
        _assert_no_link_ancestry(directory, stop=root)
        _assert_regular_directory(directory, _lstat(directory))
        collected.extend(_tree_files(root, directory))
    collected.extend(_public_research_paths(root, public_research_files))
    return tuple(sorted(set(collected), key=lambda path: path.relative_to(root).as_posix()))


def build_manifest(
    root: Path = PROJECT_ROOT,
    *,
    root_files: Sequence[str] = ROOT_FILES,
    tree_roots: Sequence[str] = TREE_ROOTS,
    public_research_files: Sequence[str] = PUBLIC_RESEARCH_FILES,
) -> dict[str, object]:
    root = _safe_root(Path(root))
    files: dict[str, dict[str, object]] = {}
    for path in collect_bundle_files(
        root,
        root_files=root_files,
        tree_roots=tree_roots,
        public_research_files=public_research_files,
    ):
        payload = path.read_bytes()
        files[path.relative_to(root).as_posix()] = {
            "sha256": hashlib.sha256(payload).hexdigest(),
            "bytes": len(payload),
        }
    canonical = json.dumps(files, ensure_ascii=True, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return {
        "schema": "utaipei-hf-bundle.v1",
        "bundle_digest": f"sha256:{hashlib.sha256(canonical).hexdigest()}",
        "files": files,
    }


def _read_source_bytes(root: Path, relative: str, expected: Mapping[str, object]) -> bytes:
    """Read one source through a checked handle and verify its manifest entry."""

    source = _contained_file(root, root / relative)
    before = _lstat(source)
    _assert_regular_file(source, before)
    before_identity = _file_identity(before)
    flags = os.O_RDONLY | getattr(os, "O_BINARY", 0) | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(os.fspath(source), flags)
    except OSError as error:
        raise ValueError(f"bundle source could not be opened: {source.name}") from error
    try:
        opened = os.fstat(descriptor)
        _assert_regular_file(source, opened)
        if _file_identity(opened) != before_identity:
            raise ValueError(f"bundle source changed before copy: {source.name}")
        with os.fdopen(descriptor, "rb") as handle:
            descriptor = -1
            payload = handle.read()
            after = os.fstat(handle.fileno())
        _assert_regular_file(source, after)
        if _file_identity(after) != before_identity:
            raise ValueError(f"bundle source changed during copy: {source.name}")
    finally:
        if descriptor >= 0:
            os.close(descriptor)

    _assert_no_link_ancestry(source, stop=root)
    path_after = _lstat(source)
    _assert_regular_file(source, path_after)
    if _file_identity(path_after) != before_identity:
        raise ValueError(f"bundle source was replaced during copy: {source.name}")
    expected_digest = str(expected.get("sha256") or "")
    expected_bytes = int(expected.get("bytes", -1))
    actual_digest = hashlib.sha256(payload).hexdigest()
    if len(payload) != expected_bytes or actual_digest != expected_digest:
        raise ValueError(f"bundle source digest changed: {source.name}")
    return payload


def _write_verified_copy(destination: Path, relative: str, payload: bytes, expected: Mapping[str, object]) -> None:
    target = _absolute_path(destination / relative)
    try:
        target.relative_to(destination)
    except ValueError as error:
        raise ValueError("bundle destination escaped its staging root") from error
    _assert_no_link_ancestry(target.parent, stop=destination)
    if os.path.lexists(os.fspath(target)):
        raise ValueError(f"bundle destination already exists: {target.name}")
    try:
        with open(target, "xb") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
    except OSError as error:
        raise ValueError(f"bundle destination could not be written: {target.name}") from error

    # Re-open the destination after the write.  This hashes the actual staged
    # bytes, not merely the in-memory source payload.
    copied = _contained_file(destination, target)
    copied_payload = copied.read_bytes()
    expected_digest = str(expected.get("sha256") or "")
    expected_bytes = int(expected.get("bytes", -1))
    copied_digest = hashlib.sha256(copied_payload).hexdigest()
    if len(copied_payload) != expected_bytes or copied_digest != expected_digest:
        raise ValueError(f"staged bundle digest mismatch: {relative}")


def _remove_created_destination(
    destination: Path,
    *,
    expected_identity: tuple[object, ...] | None = None,
) -> None:
    """Best-effort cleanup limited to the exact directory created by us."""

    try:
        info = os.lstat(os.fspath(destination))
    except FileNotFoundError:
        return
    except OSError:
        return
    if expected_identity is not None and _node_identity(info) != expected_identity:
        # The path was substituted after creation.  Do not remove an object
        # that this invocation did not create, even if it is another directory.
        return
    if _is_link_or_reparse(info):
        # Never recurse through a substituted directory.  Unlink/rmdir removes
        # only the link itself, not its target.
        try:
            if stat.S_ISDIR(getattr(info, "st_mode", 0)):
                destination.rmdir()
            else:
                destination.unlink()
        except OSError:
            pass
        return
    if not stat.S_ISDIR(getattr(info, "st_mode", 0)):
        try:
            destination.unlink()
        except OSError:
            pass
        return
    try:
        _assert_no_link_ancestry(destination.parent)
        shutil.rmtree(destination)
    except (OSError, ValueError):
        # Cleanup failure must not turn the original safe failure into a path
        # traversal.  The caller still fails closed by re-raising the original.
        pass


def stage_bundle(
    root: Path,
    destination: Path,
    *,
    root_files: Sequence[str] = ROOT_FILES,
    tree_roots: Sequence[str] = TREE_ROOTS,
    public_research_files: Sequence[str] = PUBLIC_RESEARCH_FILES,
) -> dict[str, object]:
    """Copy one immutable allowlisted bundle without overwriting a path."""

    root = _safe_root(Path(root))
    destination = _absolute_path(Path(destination))
    try:
        destination.relative_to(root)
    except ValueError:
        pass
    else:
        raise ValueError("bundle destination must be outside the project root")
    _assert_no_link_ancestry(destination.parent)
    created = False
    destination_identity: tuple[object, ...] | None = None
    try:
        destination.mkdir(parents=False, exist_ok=False)
        created = True
        destination_info = _lstat(destination)
        _assert_no_link_ancestry(destination)
        _assert_regular_directory(destination, destination_info)
        destination_identity = _node_identity(destination_info)
        manifest = build_manifest(
            root,
            root_files=root_files,
            tree_roots=tree_roots,
            public_research_files=public_research_files,
        )
        for relative, expected in manifest["files"].items():
            target = destination / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            _assert_no_link_ancestry(target.parent, stop=destination)
            payload = _read_source_bytes(root, relative, expected)
            _write_verified_copy(destination, relative, payload, expected)
        manifest_path = destination / "DEPLOYMENT_MANIFEST.json"
        _assert_no_link_ancestry(manifest_path.parent, stop=destination)
        with open(manifest_path, "x", encoding="utf-8", newline="\n") as handle:
            handle.write(json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n")
        return manifest
    except Exception:
        if created:
            _remove_created_destination(destination, expected_identity=destination_identity)
        raise


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    manifest = stage_bundle(PROJECT_ROOT, args.output)
    print(
        json.dumps(
            {
                "schema": manifest["schema"],
                "bundle_digest": manifest["bundle_digest"],
                "file_count": len(manifest["files"]),
            },
            ensure_ascii=True,
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
