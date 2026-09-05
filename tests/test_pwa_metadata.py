import json
import re
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from PIL import Image

import streamlit_bootstrap.utaipei_pwa_bootstrap.patch as pwa_patch
from streamlit_bootstrap.utaipei_pwa_bootstrap.patch import (
    EXPECTED_STREAMLIT_VERSION,
    PWA_MARKER_BEGIN,
    PWA_MARKER_END,
    BootstrapError,
    find_competing_sitecustomize,
    patch_html,
    resolve_streamlit_index,
    run_bootstrap,
    validate_index_path,
)

ROOT = Path(__file__).resolve().parents[1]
BOOTSTRAP_ARTIFACT_COMMIT = "593c7137262901b8cc1c5372d55d98888e66a83f"
BOOTSTRAP_WHEEL_FILENAME = "utaipei_streamlit_bootstrap-0.2.0-py3-none-any.whl"
BOOTSTRAP_WHEEL_SHA256 = "858a7d9fe2a82ea7d181dd9c3912b0021ab09c02838ebf0319cd876ba63c871e"
BOOTSTRAP_WHEEL_REQUIREMENT = (
    "utaipei-streamlit-bootstrap @ "
    "https://huggingface.co/spaces/Sapphirejimmy/Utaipei-credit-checker/resolve/"
    f"{BOOTSTRAP_ARTIFACT_COMMIT}/vendor/{BOOTSTRAP_WHEEL_FILENAME}"
    f"#sha256={BOOTSTRAP_WHEEL_SHA256}"
)


class PwaMetadataTests(unittest.TestCase):
    def test_versioned_icon_assets_and_manifest_are_consistent(self):
        manifest = json.loads((ROOT / "static" / "manifest-v2.webmanifest").read_text(encoding="utf-8"))
        self.assertEqual(manifest["name"], "北市大畢業通")
        self.assertEqual(manifest["short_name"], "畢業通")
        self.assertIn("輔系", manifest["description"])
        self.assertEqual(manifest["id"], "/utaipei-graduation-credit-planner")
        self.assertEqual(manifest["start_url"], "/")
        self.assertEqual(manifest["scope"], "/")
        self.assertEqual(manifest["display"], "standalone")
        self.assertEqual(manifest["theme_color"], "#1E3A5F")
        self.assertEqual(manifest["background_color"], "#F8FAFC")
        self.assertTrue(
            any(
                icon["src"] == "icons/ut-graduation-v2-192.png"
                and icon["sizes"] == "192x192"
                and "any" in icon.get("purpose", "").split()
                for icon in manifest["icons"]
            )
        )
        self.assertTrue(
            any(
                icon["src"] == "icons/ut-graduation-v2-512.png"
                and icon["sizes"] == "512x512"
                and "any" in icon.get("purpose", "").split()
                for icon in manifest["icons"]
            )
        )
        self.assertTrue(
            any(
                icon["src"] == "icons/ut-graduation-v2-512.png"
                and icon["sizes"] == "512x512"
                and "maskable" in icon.get("purpose", "").split()
                for icon in manifest["icons"]
            )
        )
        for icon in manifest["icons"]:
            icon_path = ROOT / "static" / icon["src"]
            self.assertTrue(icon_path.is_file(), icon_path)
            with Image.open(icon_path) as image:
                self.assertEqual(image.size, tuple(int(value) for value in icon["sizes"].split("x")))
                self.assertNotIn("A", image.getbands(), icon_path)
        for size in (32, 180, 192, 512):
            self.assertTrue((ROOT / "static" / "icons" / f"ut-graduation-v2-{size}.png").is_file())

    def test_startup_patch_replaces_stale_metadata_and_is_idempotent(self):
        stale_index = """<!doctype html>
<html><head>
  <link rel="shortcut icon" href="./favicon.png" />
  <link id="ut-pwa-manifest" rel="manifest" href="./app/static/manifest.webmanifest" />
  <meta id="ut-apple-title" name="apple-mobile-web-app-title" content="UT 學分規劃" />
  <meta name="apple-mobile-web-app-status-bar-style" content="black-translucent" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>Streamlit</title>
</head><body><script>window.prerenderReady = false</script></body></html>
"""
        # The pure patch function works on a fake document and never executes
        # the script included in that document.
        patched = patch_html(stale_index)
        self.assertEqual(patched, patch_html(patched))

        self.assertEqual(patched.count(PWA_MARKER_BEGIN), 1)
        self.assertEqual(patched.count(PWA_MARKER_END), 1)
        self.assertEqual(re.findall(r"<title>(.*?)</title>", patched), ["北市大畢業通"])
        self.assertEqual(
            patched.count('name="apple-mobile-web-app-status-bar-style" content="black"'),
            1,
        )
        self.assertEqual(patched.count('name="apple-mobile-web-app-status-bar-style"'), 1)
        self.assertNotIn("black-translucent", patched)
        self.assertIn("viewport-fit=cover", patched)
        self.assertEqual(patched.count('name="apple-mobile-web-app-title" content="北市大畢業通"'), 1)
        self.assertEqual(patched.count('rel="manifest" href="/app/static/manifest-v2.webmanifest"'), 1)
        self.assertEqual(patched.count('rel="apple-touch-icon" sizes="180x180"'), 1)
        self.assertIn("ut-graduation-v2-180.png", patched)
        self.assertIn("ut-graduation-v2-32.png", patched)
        self.assertNotIn("manifest.webmanifest\"", patched.replace("manifest-v2.webmanifest", ""))
        self.assertNotIn("UT 學分規劃", patched)
        self.assertEqual(patched.count("navigator.serviceWorker.register"), 1)
        self.assertIn("register('/service-worker.js'", patched)
        self.assertIn("scope: '/'", patched)
        self.assertIn("updateViaCache: 'none'", patched)

    def test_patch_rejects_malformed_html(self):
        for malformed in (
            "",
            "<html><body>missing head</body></html>",
            "<html><head><title>x</title></head>",
        ):
            with self.subTest(malformed=malformed), self.assertRaises(BootstrapError):
                patch_html(malformed)

    def test_resolver_refuses_wrong_version_and_outside_path(self):
        fake_module = SimpleNamespace(__version__="1.56.0", __file__=str(ROOT / "app.py"))
        with self.assertRaises(BootstrapError):
            resolve_streamlit_index(fake_module)
        with self.assertRaises(BootstrapError):
            validate_index_path(ROOT / "static", ROOT / "README.md")

    def test_resolver_refuses_symlink_target_without_following_it(self):
        target = ROOT / "README.md"
        with patch.object(Path, "is_symlink", side_effect=lambda: True):
            with self.assertRaises(BootstrapError):
                validate_index_path(ROOT, target)

    def test_competing_sitecustomize_is_detected_without_importing_it(self):
        own_file = ROOT / "tests" / "test_pwa_metadata.py"
        with patch.object(Path, "is_file", side_effect=lambda: True):
            collision = find_competing_sitecustomize(own_file=own_file, path_entries=[str(ROOT)])
        self.assertIsNotNone(collision)
        self.assertEqual(collision.name, "sitecustomize.py")

    def test_bootstrap_uses_installed_top_level_sitecustomize_as_own_file(self):
        with patch.object(pwa_patch, "find_competing_sitecustomize", return_value=None) as find_collision:
            with patch.object(pwa_patch, "patch_installed_streamlit_index", return_value=False):
                self.assertFalse(run_bootstrap())
        find_collision.assert_called_once()
        own_file = find_collision.call_args.kwargs["own_file"]
        self.assertEqual(Path(own_file).name, "sitecustomize.py")

    def test_sitecustomize_is_small_fail_closed_and_secret_free(self):
        source = (ROOT / "streamlit_bootstrap" / "sitecustomize.py").read_text(encoding="utf-8")
        self.assertLessEqual(len(source.splitlines()), 20)
        self.assertIn("UTaipei PWA bootstrap failed closed.", source)
        self.assertIn("SystemExit(78)", source)
        self.assertNotIn("HF資訊", source)
        self.assertNotIn("token", source.lower())

    def test_app_uses_static_pwa_metadata_only(self):
        app_source = (ROOT / "app.py").read_text(encoding="utf-8")
        page_source = (ROOT / "ui_components.py").read_text(encoding="utf-8")
        self.assertNotIn("pwa_metadata", app_source)
        self.assertNotIn("serviceWorker.register", app_source)
        self.assertIn('page_title="北市大畢業通"', page_source)
        self.assertEqual(EXPECTED_STREAMLIT_VERSION, "1.57.0")

    def test_streamlit_bootstrap_package_declares_both_installable_modules(self):
        project = (ROOT / "streamlit_bootstrap" / "pyproject.toml").read_text(encoding="utf-8")
        self.assertIn('py-modules = ["sitecustomize"]', project)
        self.assertIn('include = ["utaipei_pwa_bootstrap*"]', project)
        requirements_text = (ROOT / "requirements.txt").read_text(encoding="utf-8")
        requirements = requirements_text.splitlines()
        self.assertEqual(requirements[0], "streamlit==1.57.0")
        bootstrap_requirement = requirements[-1]
        self.assertEqual(bootstrap_requirement, BOOTSTRAP_WHEEL_REQUIREMENT)
        self.assertTrue(bootstrap_requirement.startswith("utaipei-streamlit-bootstrap @ https://"))
        self.assertIn(f"/resolve/{BOOTSTRAP_ARTIFACT_COMMIT}/", bootstrap_requirement)
        self.assertIn(f"/vendor/{BOOTSTRAP_WHEEL_FILENAME}", bootstrap_requirement)
        self.assertIn(f"#sha256={BOOTSTRAP_WHEEL_SHA256}", bootstrap_requirement)
        self.assertNotIn("git+", requirements_text)
        self.assertNotIn("./streamlit_bootstrap", requirements_text)
        self.assertNotRegex(bootstrap_requirement, r"/(?:main|master|develop|latest)/")
        self.assertNotRegex(
            bootstrap_requirement,
            r"(?i)(?:[?&]|#)(?:token|password|secret|authorization|access[_-]?token)=",
        )


if __name__ == "__main__":
    unittest.main()
