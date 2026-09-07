"""Synthetic contract checks for the reviewed GitHub release helpers."""

from __future__ import annotations

import ast
import hashlib
import importlib.util
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


def _load_helper(relative: str, name: str):
    path = ROOT / relative
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


prepare = _load_helper("scripts/prepare_github_release.py", "prepare_github_release_test")
publish = _load_helper("scripts/publish_github_release.py", "publish_github_release_test")


def test_extra_python_files_must_be_explicitly_reviewed(tmp_path):
    (tmp_path / "tests").mkdir()
    (tmp_path / "scripts").mkdir()
    (tmp_path / "tests" / "known.py").write_text("KNOWN = True\n", encoding="utf-8")
    (tmp_path / "scripts" / "known.py").write_text("KNOWN = True\n", encoding="utf-8")
    (tmp_path / "scripts" / "unreviewed.py").write_text("PRIVATE = True\n", encoding="utf-8")

    with pytest.raises(ValueError, match="EXTRA_PATH_UNREVIEWED"):
        prepare._collect_reviewed_extra_payloads(
            tmp_path,
            allowed=("tests/known.py", "scripts/known.py"),
        )


def test_extra_allowlist_rejects_unsafe_manifest_name(tmp_path):
    with pytest.raises(ValueError, match="EXTRA_MANIFEST_INVALID"):
        prepare._collect_reviewed_extra_payloads(tmp_path, allowed=("tests/../secret.py",))


def test_publisher_rejects_changed_parent_and_wrong_remote():
    with pytest.raises(ValueError, match="PARENT_CHANGED"):
        publish._assert_expected_parent("a" * 40, "b" * 40)
    with pytest.raises(ValueError, match="REMOTE_INVALID"):
        publish._assert_expected_remote("https://example.test/repository.git")


def test_changed_staged_hash_fails_closed():
    expected = {"bytes": 3, "sha256": hashlib.sha256(b"abc").hexdigest()}
    with pytest.raises(ValueError, match="STAGED_CONTENT_CHANGED"):
        publish._verify_staged_blob("tests/example.py", expected, b"abd")


def test_lfs_pointer_must_match_expected_binary_hash_and_size():
    binary = b"synthetic png bytes"
    digest = hashlib.sha256(binary).hexdigest()
    expected = {"bytes": len(binary), "sha256": digest}
    pointer = (
        b"version https://git-lfs.github.com/spec/v1\n"
        + f"oid sha256:{digest}\nsize {len(binary)}\n".encode()
    )
    publish._verify_staged_blob("static/icon.png", expected, pointer, lfs=True)
    with pytest.raises(ValueError, match="LFS_POINTER_INVALID"):
        publish._verify_staged_blob("static/icon.png", expected, pointer.replace(digest.encode(), b"0" * 64), lfs=True)


def test_changed_pathspec_hash_is_rejected(tmp_path, monkeypatch):
    checkout = tmp_path / "checkout"
    (checkout / "tests").mkdir(parents=True)
    payload = b"KNOWN = True\n"
    (checkout / "tests" / "known.py").write_bytes(payload)
    expected_path = tmp_path / "expected.json"
    pathspec_path = tmp_path / "pathspec"
    name = "tests/known.py"
    pathspec = name.encode() + b"\0"
    expected_path.write_text(
        json.dumps(
            {
                "schema": publish.EXPECTED_SCHEMA,
                "remote": publish.REMOTE,
                "parent": "a" * 40,
                "bundle_digest": "sha256:" + "0" * 64,
                "pathspec_sha256": hashlib.sha256(pathspec).hexdigest(),
                "files": {name: {"bytes": len(payload), "sha256": hashlib.sha256(payload).hexdigest()}},
            }
        ),
        encoding="utf-8",
    )
    pathspec_path.write_bytes(pathspec)
    monkeypatch.setattr(publish, "CHECKOUT", checkout)
    pathspec_path.write_bytes(b"tests/known.py\0changed.py\0")
    with pytest.raises(ValueError, match="PATHSPEC_CHANGED"):
        publish._read_expected_record(expected_path, pathspec_path)


def test_publish_requires_explicit_flag_skip_ci_and_never_force_pushes():
    source = (ROOT / "scripts" / "publish_github_release.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    assert "[skip ci]" in publish.COMMIT_MESSAGE
    assert "--publish" in source
    push_calls = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "_git_bytes"
        and any(isinstance(arg, ast.Constant) and arg.value == "push" for arg in node.args)
    ]
    assert len(push_calls) == 1
    assert all(not any(isinstance(arg, ast.Constant) and arg.value == "--force" for arg in call.args) for call in push_calls)
    assert "publish_release() if args.publish else review_release()" in source
