from __future__ import annotations

import json
import stat
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest

import scripts.build_hf_bundle as bundle
from scripts.build_hf_bundle import build_manifest, collect_bundle_files, stage_bundle


def _fixture_tree(root):
    (root / "app.py").write_text("print('safe')\n", encoding="utf-8")
    (root / "requirements.txt").write_text("streamlit==1.57.0\n", encoding="utf-8")
    (root / "static").mkdir()
    (root / "static" / "manifest.webmanifest").write_text("{}", encoding="utf-8")
    (root / "HF資訊.txt").write_text("HF Token: must-not-copy", encoding="utf-8")


def _research_fixture(root):
    research = root / "research"
    research.mkdir(exist_ok=True)
    for relative in bundle.PUBLIC_RESEARCH_FILES:
        path = root / relative
        path.write_text(f"public: {path.name}\n", encoding="utf-8")


def test_bundle_collection_is_allowlisted_and_excludes_local_credentials(tmp_path):
    _fixture_tree(tmp_path)

    files = collect_bundle_files(
        tmp_path,
        root_files=("app.py", "requirements.txt"),
        tree_roots=("static",),
    )

    assert [path.relative_to(tmp_path).as_posix() for path in files] == [
        "app.py",
        "requirements.txt",
        "static/manifest.webmanifest",
    ]
    assert all("資訊" not in path.name for path in files)


def test_production_allowlist_excludes_secrets_and_transcripts_inside_asset_directories(tmp_path):
    for relative in bundle.ROOT_FILES:
        path = tmp_path / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"synthetic public runtime asset")
    (tmp_path / ".streamlit" / "secrets.toml").write_text("synthetic_private_value=1")
    (tmp_path / "static" / "transcript.json").write_text('{"synthetic_private_grade": 91}')

    manifest = build_manifest(tmp_path)

    assert set(manifest["files"]) == set(bundle.ROOT_FILES)
    assert ".streamlit/secrets.toml" not in manifest["files"]
    assert "static/transcript.json" not in manifest["files"]


def test_manifest_is_deterministic_and_records_only_safe_relative_paths(tmp_path):
    _fixture_tree(tmp_path)
    kwargs = {"root_files": ("app.py", "requirements.txt"), "tree_roots": ("static",)}

    first = build_manifest(tmp_path, **kwargs)
    second = build_manifest(tmp_path, **kwargs)

    assert first == second
    assert first["schema"] == "utaipei-hf-bundle.v1"
    assert first["bundle_digest"].startswith("sha256:")
    assert all(not name.startswith(("/", "..")) for name in first["files"])
    assert "HF資訊.txt" not in json.dumps(first, ensure_ascii=False)


def test_stage_bundle_refuses_to_overwrite_existing_directory(tmp_path):
    source = tmp_path / "source"
    source.mkdir()
    _fixture_tree(source)
    destination = tmp_path / "existing"
    destination.mkdir()

    with pytest.raises(FileExistsError):
        stage_bundle(
            source,
            destination,
            root_files=("app.py", "requirements.txt"),
            tree_roots=("static",),
        )


def test_stage_bundle_writes_content_addressed_public_manifest(tmp_path):
    source = tmp_path / "source"
    source.mkdir()
    _fixture_tree(source)
    destination = tmp_path / "bundle"

    manifest = stage_bundle(
        source,
        destination,
        root_files=("app.py", "requirements.txt"),
        tree_roots=("static",),
    )

    assert (destination / "app.py").read_text(encoding="utf-8") == "print('safe')\n"
    assert not (destination / "HF資訊.txt").exists()
    deployed = json.loads((destination / "DEPLOYMENT_MANIFEST.json").read_text(encoding="utf-8"))
    assert deployed == manifest


def test_collection_rejects_symlink_tree_root_before_traversal(tmp_path):
    source = tmp_path / "source"
    source.mkdir()
    _fixture_tree(source)
    linked_root = tmp_path / "linked-static"
    try:
        linked_root.symlink_to(source / "static", target_is_directory=True)
    except (OSError, NotImplementedError):
        pytest.skip("symlink creation is unavailable on this platform")

    with pytest.raises(ValueError, match="symlink|reparse"):
        collect_bundle_files(
            source,
            root_files=("app.py",),
            tree_roots=("linked-static",),
            public_research_files=(),
        )


def test_collection_rejects_symlink_project_root_without_resolving_it(tmp_path):
    source = tmp_path / "source"
    source.mkdir()
    _fixture_tree(source)
    linked_root = tmp_path / "linked-source"
    try:
        linked_root.symlink_to(source, target_is_directory=True)
    except (OSError, NotImplementedError):
        pytest.skip("symlink creation is unavailable on this platform")

    with pytest.raises(ValueError, match="symlink|reparse"):
        collect_bundle_files(
            linked_root,
            root_files=("app.py",),
            tree_roots=("static",),
            public_research_files=(),
        )


def test_collection_rejects_windows_reparse_tree_root_before_traversal(tmp_path):
    source = tmp_path / "source"
    source.mkdir()
    _fixture_tree(source)
    real_lstat = bundle._lstat

    def fake_lstat(path):
        info = real_lstat(path)
        if path.name == "static":
            return SimpleNamespace(st_mode=stat.S_IFDIR, st_file_attributes=0x0400)
        return info

    with patch.object(bundle, "_lstat", side_effect=fake_lstat):
        with pytest.raises(ValueError, match="symlink|reparse"):
            collect_bundle_files(
                source,
                root_files=("app.py",),
                tree_roots=("static",),
                public_research_files=(),
            )


def test_collection_rejects_file_symlink_without_following_target(tmp_path):
    source = tmp_path / "source"
    source.mkdir()
    _fixture_tree(source)
    outside = tmp_path / "outside.py"
    outside.write_text("private\n", encoding="utf-8")
    app_path = source / "app.py"
    app_path.unlink()
    try:
        app_path.symlink_to(outside)
    except (OSError, NotImplementedError):
        pytest.skip("symlink creation is unavailable on this platform")

    with pytest.raises(ValueError, match="symlink|reparse"):
        collect_bundle_files(
            source,
            root_files=("app.py",),
            tree_roots=("static",),
            public_research_files=(),
        )


def test_public_research_allowlist_excludes_new_private_note(tmp_path):
    _fixture_tree(tmp_path)
    _research_fixture(tmp_path)
    (tmp_path / "research" / "private-note.md").write_text("private", encoding="utf-8")

    files = collect_bundle_files(
        tmp_path,
        root_files=("app.py", "requirements.txt"),
        tree_roots=("static", "research"),
    )
    names = {path.relative_to(tmp_path).as_posix() for path in files}
    assert "research/private-note.md" not in names
    assert {path for path in names if path.startswith("research/")} == set(bundle.PUBLIC_RESEARCH_FILES)


def test_stage_bundle_removes_only_new_destination_after_post_copy_digest_mismatch(tmp_path):
    source = tmp_path / "source"
    source.mkdir()
    _fixture_tree(source)
    destination = tmp_path / "staging"
    real_read_bytes = type(destination).read_bytes

    def mismatched_read_bytes(path):
        if path == destination / "app.py":
            return b"tampered"
        return real_read_bytes(path)

    with patch.object(type(destination), "read_bytes", mismatched_read_bytes):
        with pytest.raises(ValueError, match="digest"):
            stage_bundle(
                source,
                destination,
                root_files=("app.py", "requirements.txt"),
                tree_roots=("static",),
                public_research_files=(),
            )
    assert not destination.exists()


def test_stage_bundle_rechecks_source_identity_before_copy(tmp_path):
    source = tmp_path / "source"
    source.mkdir()
    _fixture_tree(source)
    destination = tmp_path / "staging"
    real_open = bundle.os.open
    replaced = False

    def substitute_before_open(path, flags, *args):
        nonlocal replaced
        if not replaced and Path(path).name == "app.py":
            replaced = True
            app_path = Path(path)
            app_path.write_text("changed after manifest\n", encoding="utf-8")
        return real_open(path, flags, *args)

    with patch.object(bundle.os, "open", side_effect=substitute_before_open):
        with pytest.raises(ValueError, match="digest|changed|replaced"):
            stage_bundle(
                source,
                destination,
                root_files=("app.py", "requirements.txt"),
                tree_roots=("static",),
                public_research_files=(),
            )
    assert not destination.exists()
