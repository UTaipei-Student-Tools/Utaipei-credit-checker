"""Review and, only with ``--publish``, publish the prepared GitHub release.

The target checkout and remote are fixed deliberately.  The default command is
read-only and validates the prepared record; mutation requires the explicit
``--publish`` flag and still uses an ordinary fast-forward push.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import stat
import subprocess
import sys
from collections.abc import Mapping
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.build_hf_bundle import build_manifest  # noqa: E402

REMOTE = "https://github.com/UTaipei-Student-Tools/Utaipei-credit-checker.git"
CHECKOUT = ROOT / "tmp" / "github-release"
PATHSPEC = ROOT / "tmp" / "github-release-pathspec"
EXPECTED = ROOT / "tmp" / "github-release-expected.json"
EXPECTED_SCHEMA = "utaipei-github-release.v1"
COMMIT_MESSAGE = "Publish reviewed UTaipei application sources [skip ci]"
_REPARSE_POINT_ATTRIBUTE = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x0400)
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_GIT_OBJECT_ID = re.compile(r"^[0-9a-f]{40,64}$")


def _git_bytes(*args: str, config: bool = False) -> bytes:
    command = ["git"]
    if config:
        command.extend(("-c", "core.autocrlf=false", "-c", "core.safecrlf=false"))
    command.extend(("-C", str(CHECKOUT), *args))
    result = subprocess.run(command, capture_output=True)
    if result.returncode:
        raise ValueError("GIT_COMMAND_FAILED")
    return result.stdout


def _git_text(*args: str, config: bool = False) -> str:
    try:
        return _git_bytes(*args, config=config).decode("utf-8")
    except UnicodeDecodeError as error:
        raise ValueError("GIT_COMMAND_FAILED") from error


def _has_reparse_attribute(info: object) -> bool:
    try:
        attributes = int(getattr(info, "st_file_attributes", 0) or 0)
    except (TypeError, ValueError, OverflowError):
        attributes = 0
    return bool(attributes & _REPARSE_POINT_ATTRIBUTE)


def _safe_checkout_file(relative: str) -> Path:
    """Resolve one expected file without following links or reparse points."""

    name = Path(relative).as_posix()
    if name.startswith("/") or "\\" in name or any(part in {"", ".", ".."} for part in name.split("/")):
        raise ValueError("PATHSPEC_INVALID")
    candidate = Path(os.path.abspath(os.fspath(CHECKOUT / name)))
    checkout = Path(os.path.abspath(os.fspath(CHECKOUT)))
    try:
        candidate.relative_to(checkout)
    except ValueError as error:
        raise ValueError("PATHSPEC_INVALID") from error
    current = candidate
    while True:
        try:
            info = current.lstat()
        except FileNotFoundError as error:
            raise ValueError("PREPARED_FILE_MISSING") from error
        if current.is_symlink() or _has_reparse_attribute(info):
            raise ValueError("PREPARED_PATH_INVALID")
        if current == checkout:
            break
        parent = current.parent
        if parent == current:
            raise ValueError("PATHSPEC_INVALID")
        current = parent
    if not stat.S_ISREG(candidate.lstat().st_mode):
        raise ValueError("PREPARED_PATH_INVALID")
    return candidate


def _expected_meta(value: object) -> dict[str, object]:
    """Accept the current record and the original hash-only record format."""

    if isinstance(value, str):
        return {"sha256": value}
    if isinstance(value, Mapping):
        return dict(value)
    raise ValueError("EXPECTED_RECORD_INVALID")


def _read_expected_record(
    expected_path: Path = EXPECTED,
    pathspec_path: Path = PATHSPEC,
) -> tuple[dict[str, object], dict[str, dict[str, object]]]:
    try:
        record = json.loads(expected_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise ValueError("EXPECTED_RECORD_INVALID") from error
    if not isinstance(record, dict) or record.get("schema") != EXPECTED_SCHEMA:
        raise ValueError("EXPECTED_RECORD_INVALID")
    if record.get("remote") != REMOTE:
        raise ValueError("REMOTE_INVALID")
    parent = record.get("parent")
    if not isinstance(parent, str) or not _GIT_OBJECT_ID.fullmatch(parent):
        raise ValueError("EXPECTED_RECORD_INVALID")
    raw_files = record.get("files")
    if not isinstance(raw_files, Mapping) or not raw_files:
        raise ValueError("EXPECTED_RECORD_INVALID")
    files = {str(name): _expected_meta(value) for name, value in raw_files.items()}
    if set(files) != set(Path(name).as_posix() for name in files):
        raise ValueError("PATHSPEC_INVALID")
    try:
        pathspec_bytes = pathspec_path.read_bytes()
    except OSError as error:
        raise ValueError("PATHSPEC_INVALID") from error
    expected_pathspec_hash = record.get("pathspec_sha256")
    if not isinstance(expected_pathspec_hash, str) or hashlib.sha256(pathspec_bytes).hexdigest() != expected_pathspec_hash:
        raise ValueError("PATHSPEC_CHANGED")
    try:
        names = [item.decode("utf-8") for item in pathspec_bytes.split(b"\0") if item]
    except UnicodeDecodeError as error:
        raise ValueError("PATHSPEC_INVALID") from error
    if names != sorted(names) or len(names) != len(set(names)) or set(names) != set(files):
        raise ValueError("PATHSPEC_INVALID")
    for name in names:
        _safe_checkout_file(name)
    return record, files


def _assert_expected_parent(actual: str, expected: str) -> None:
    if actual != expected:
        raise ValueError("PARENT_CHANGED")


def _assert_expected_remote(actual: str, expected: str = REMOTE) -> None:
    if actual.strip() != expected:
        raise ValueError("REMOTE_INVALID")


def _remote_head() -> str:
    output = _git_text("ls-remote", "origin", "refs/heads/main")
    fields = output.strip().split()
    if len(fields) < 2 or fields[1] != "refs/heads/main" or not _GIT_OBJECT_ID.fullmatch(fields[0]):
        raise ValueError("REMOTE_HEAD_INVALID")
    return fields[0]


def _assert_parent_and_remote(parent: str, *, contact_remote: bool = False) -> None:
    _assert_expected_parent(_git_text("rev-parse", "HEAD").strip(), parent)
    origin_head = _git_text("rev-parse", "refs/remotes/origin/main").strip()
    _assert_expected_parent(origin_head, parent)
    if contact_remote:
        _assert_expected_parent(_remote_head(), parent)


def _verify_worktree_files(files: Mapping[str, Mapping[str, object]]) -> None:
    for name, raw_meta in files.items():
        meta = _expected_meta(raw_meta)
        expected_hash = meta.get("sha256")
        expected_bytes = meta.get("bytes")
        if not isinstance(expected_hash, str) or not _SHA256.fullmatch(expected_hash):
            raise ValueError("EXPECTED_RECORD_INVALID")
        payload = _safe_checkout_file(name).read_bytes()
        if not isinstance(expected_bytes, int):
            expected_bytes = len(payload)
        if len(payload) != expected_bytes or hashlib.sha256(payload).hexdigest() != expected_hash:
            raise ValueError("PREPARED_CONTENT_CHANGED")


def _looks_like_lfs_pointer(payload: bytes) -> bool:
    return payload.startswith(b"version https://git-lfs.github.com/spec/v1\n")


def _verify_staged_blob(
    name: str,
    expected: Mapping[str, object] | str,
    staged: bytes,
    *,
    lfs: bool = False,
) -> None:
    """Verify a staged blob, resolving an LFS pointer to its binary digest."""

    meta = _expected_meta(expected)
    expected_hash = meta.get("sha256")
    expected_bytes = meta.get("bytes")
    if not isinstance(expected_hash, str) or not _SHA256.fullmatch(expected_hash):
        raise ValueError("EXPECTED_RECORD_INVALID")
    if lfs:
        try:
            lines = staged.decode("utf-8", errors="strict").splitlines()
        except UnicodeDecodeError as error:
            raise ValueError("LFS_POINTER_INVALID") from error
        if not lines or lines[0] != "version https://git-lfs.github.com/spec/v1":
            raise ValueError("LFS_POINTER_INVALID")
        values: dict[str, str] = {}
        for line in lines[1:]:
            key, separator, value = line.partition(" ")
            if separator and key in {"oid", "size"}:
                values[key] = value
        oid = values.get("oid", "")
        size_text = values.get("size", "")
        if not oid.startswith("sha256:") or not _SHA256.fullmatch(oid[7:]):
            raise ValueError("LFS_POINTER_INVALID")
        try:
            size = int(size_text)
        except (TypeError, ValueError):
            raise ValueError("LFS_POINTER_INVALID") from None
        if oid[7:] != expected_hash or (isinstance(expected_bytes, int) and size != expected_bytes):
            raise ValueError("LFS_POINTER_INVALID")
        expected_pointer = (
            b"version https://git-lfs.github.com/spec/v1\n"
            + f"oid sha256:{expected_hash}\nsize {size}\n".encode("ascii")
        )
        if staged != expected_pointer:
            raise ValueError("LFS_POINTER_INVALID")
        return
    if _looks_like_lfs_pointer(staged):
        raise ValueError("STAGED_CONTENT_CHANGED")
    if isinstance(expected_bytes, int) and len(staged) != expected_bytes:
        raise ValueError("STAGED_CONTENT_CHANGED")
    if hashlib.sha256(staged).hexdigest() != expected_hash:
        raise ValueError("STAGED_CONTENT_CHANGED")


def _git_filter_is_lfs(name: str) -> bool:
    output = _git_text("check-attr", "filter", "--", name)
    return output.strip().endswith(": filter: lfs")


def _verify_staged_files(files: Mapping[str, Mapping[str, object]]) -> None:
    for name, meta in files.items():
        staged = _git_bytes("show", f":{name}")
        _verify_staged_blob(name, meta, staged, lfs=_git_filter_is_lfs(name))


def _names_from_nul(output: str) -> set[str]:
    return {item for item in output.split("\0") if item}


def _assert_staged_changes_are_allowlisted(files: Mapping[str, Mapping[str, object]]) -> None:
    changed = _names_from_nul(_git_text("diff", "--cached", "--name-only", "-z"))
    if not changed.issubset(set(files)):
        raise ValueError("STAGED_PATH_INVALID")


def _verify_current_bundle_digest(record: Mapping[str, object]) -> None:
    bundle_digest = record.get("bundle_digest")
    current = build_manifest(ROOT).get("bundle_digest")
    if not isinstance(bundle_digest, str) or current != bundle_digest:
        raise ValueError("SOURCE_CHANGED")


def review_release() -> dict[str, object]:
    """Perform all read-only checks and return safe review metadata."""

    checkout = Path(os.path.abspath(os.fspath(CHECKOUT)))
    expected_checkout = Path(os.path.abspath(os.fspath(ROOT / "tmp" / "github-release")))
    if checkout != expected_checkout or CHECKOUT.is_symlink():
        raise ValueError("CHECKOUT_INVALID")
    _assert_expected_remote(_git_text("remote", "get-url", "origin"))
    record, files = _read_expected_record()
    _assert_parent_and_remote(str(record["parent"]))
    _verify_current_bundle_digest(record)
    _verify_worktree_files(files)
    return {
        "reviewed": True,
        "remote": REMOTE,
        "parent": record["parent"],
        "runtime_digest": record.get("bundle_digest"),
        "file_count": len(files),
    }


def publish_release() -> dict[str, object]:
    """Stage, commit, and fast-forward push the already reviewed payload."""

    result = review_release()
    record, files = _read_expected_record()
    parent = str(record["parent"])
    preexisting = _names_from_nul(_git_text("diff", "--cached", "--name-only", "-z"))
    if preexisting:
        raise ValueError("STAGED_STATE_DIRTY")
    _assert_parent_and_remote(parent, contact_remote=True)
    _git_bytes(
        "add",
        "--force",
        f"--pathspec-from-file={PATHSPEC}",
        "--pathspec-file-nul",
        config=True,
    )
    _assert_staged_changes_are_allowlisted(files)
    _verify_staged_files(files)
    _assert_parent_and_remote(parent, contact_remote=True)
    _git_bytes("commit", "-m", COMMIT_MESSAGE, config=True)
    new_head = _git_text("rev-parse", "HEAD").strip()
    if not _GIT_OBJECT_ID.fullmatch(new_head) or _git_text("rev-parse", "HEAD^1").strip() != parent:
        raise ValueError("COMMIT_PARENT_INVALID")
    if "[skip ci]" not in _git_text("log", "-1", "--format=%B"):
        raise ValueError("COMMIT_MESSAGE_INVALID")
    committed = _names_from_nul(_git_text("diff-tree", "--no-commit-id", "--name-only", "-r", "-z", "HEAD"))
    if not committed.issubset(set(files)):
        raise ValueError("COMMIT_PATH_INVALID")
    _assert_expected_remote(_git_text("remote", "get-url", "origin"))
    _assert_expected_parent(_remote_head(), parent)
    _git_bytes("push", "origin", "HEAD:refs/heads/main", config=True)
    return {**result, "published": True, "commit": new_head}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--publish",
        action="store_true",
        help="commit and fast-forward push after all review checks; default is read-only review",
    )
    args = parser.parse_args()
    result = publish_release() if args.publish else review_release()
    print(json.dumps(result, ensure_ascii=True))


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        approved = {
            "CHECKOUT_INVALID",
            "REMOTE_INVALID",
            "EXPECTED_RECORD_INVALID",
            "PATHSPEC_INVALID",
            "PATHSPEC_CHANGED",
            "PARENT_CHANGED",
            "REMOTE_HEAD_INVALID",
            "PREPARED_FILE_MISSING",
            "PREPARED_PATH_INVALID",
            "PREPARED_CONTENT_CHANGED",
            "SOURCE_CHANGED",
            "GIT_COMMAND_FAILED",
            "STAGED_CONTENT_CHANGED",
            "LFS_POINTER_INVALID",
            "STAGED_PATH_INVALID",
            "STAGED_STATE_DIRTY",
            "COMMIT_PARENT_INVALID",
            "COMMIT_MESSAGE_INVALID",
            "COMMIT_PATH_INVALID",
        }
        code = str(error) if isinstance(error, ValueError) and str(error) in approved else type(error).__name__
        print(json.dumps({"published": False, "code": code}, ensure_ascii=True))
        raise SystemExit(1) from None
