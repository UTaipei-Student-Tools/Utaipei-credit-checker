import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from streamlit_bootstrap.utaipei_pwa_bootstrap.patch import (
    BOOTSTRAP_BUILD_VERSION,
    SERVICE_WORKER_FILENAME,
    SERVICE_WORKER_SOURCE,
    BootstrapError,
    install_service_worker,
    patch_html,
    patch_installed_streamlit_index,
)

HTML = """<!doctype html>
<html><head><title>Streamlit</title></head><body></body></html>
"""


class ServiceWorkerTests(unittest.TestCase):
    def test_initial_html_contains_one_root_scope_registration(self):
        patched = patch_html(HTML)

        self.assertEqual(patched.count("navigator.serviceWorker.register"), 1)
        self.assertIn("register('/service-worker.js'", patched)
        self.assertIn("scope: '/'", patched)
        self.assertIn("updateViaCache: 'none'", patched)
        self.assertNotIn("serviceWorker.register('/app/static/", patched)

    def test_initial_html_uses_current_identity_contract(self):
        patched = patch_html(HTML)

        self.assertIn('name="application-name" content="北市大畢業通"', patched)
        self.assertIn('name="theme-color" content="#1E3A5F"', patched)
        self.assertIn("viewport-fit=cover", patched)
        self.assertNotIn("Streamlit</title>", patched)

    def test_service_worker_only_caches_explicit_public_static_assets(self):
        source = SERVICE_WORKER_SOURCE

        self.assertIn("const STATIC_SHELL_ASSETS = new Set(", source)
        self.assertIn("/app/static/manifest-v2.webmanifest", source)
        self.assertIn("/app/static/icons/ut-graduation-v2-180.png", source)
        self.assertIn("request.mode === 'navigate'", source)
        self.assertIn("url.search", source)
        self.assertIn("STATIC_SHELL_ASSETS.has(url.pathname)", source)
        self.assertNotIn("localStorage", source)
        self.assertNotIn("sessionStorage", source)
        self.assertNotIn("document.cookie", source)
        self.assertNotIn("Authorization", source)

    def test_service_worker_messages_and_activation_are_scoped_to_app_cache(self):
        source = SERVICE_WORKER_SOURCE

        self.assertIn("SKIP_WAITING", source)
        self.assertIn("CHECK_VERSION", source)
        self.assertIn("CLEAR_STATIC_CACHES", source)
        self.assertIn("caches.keys()", source)
        self.assertIn("key.startsWith(CACHE_PREFIX)", source)
        self.assertIn("key !== CACHE_NAME", source)
        self.assertIn("const CACHE_PREFIX = 'utaipei-graduation-static-'", source)

    def test_install_is_atomic_idempotent_and_collision_aware(self):
        with tempfile.TemporaryDirectory() as raw_root:
            package_root = Path(raw_root) / "streamlit"
            static_root = package_root / "static"
            static_root.mkdir(parents=True)

            self.assertTrue(install_service_worker(static_root, package_root=package_root))
            worker_path = static_root / SERVICE_WORKER_FILENAME
            self.assertEqual(worker_path.read_text(encoding="utf-8"), SERVICE_WORKER_SOURCE)
            self.assertFalse(install_service_worker(static_root, package_root=package_root))

            worker_path.write_text("foreign worker", encoding="utf-8")
            with self.assertRaises(BootstrapError):
                install_service_worker(static_root, package_root=package_root)

    def test_install_rejects_outside_and_symlinked_static_roots(self):
        with tempfile.TemporaryDirectory() as raw_root:
            root = Path(raw_root)
            package_root = root / "streamlit"
            static_root = package_root / "static"
            static_root.mkdir(parents=True)
            outside = root / "outside"
            outside.mkdir()

            with self.assertRaises(BootstrapError):
                install_service_worker(outside, package_root=package_root)

            symlink_root = package_root / "static-link"
            try:
                symlink_root.symlink_to(static_root, target_is_directory=True)
            except (OSError, NotImplementedError) as exc:
                self.skipTest(f"symlink unavailable: {exc}")
            with self.assertRaises(BootstrapError):
                install_service_worker(symlink_root, package_root=package_root)

    def test_installed_streamlit_patch_writes_worker_and_initial_html(self):
        with tempfile.TemporaryDirectory() as raw_root:
            package_root = Path(raw_root) / "streamlit"
            static_root = package_root / "static"
            static_root.mkdir(parents=True)
            index_path = static_root / "index.html"
            index_path.write_text(HTML, encoding="utf-8")
            fake_streamlit = SimpleNamespace(
                __version__="1.57.0",
                __file__=str(package_root / "__init__.py"),
            )

            self.assertTrue(patch_installed_streamlit_index(fake_streamlit))
            self.assertIn("register('/service-worker.js'", index_path.read_text(encoding="utf-8"))
            self.assertEqual(
                (static_root / SERVICE_WORKER_FILENAME).read_text(encoding="utf-8"),
                SERVICE_WORKER_SOURCE,
            )
            self.assertFalse(patch_installed_streamlit_index(fake_streamlit))

    def test_build_marker_is_non_sensitive_and_single(self):
        self.assertRegex(BOOTSTRAP_BUILD_VERSION, r"^0\.2\.0$")
        self.assertEqual(SERVICE_WORKER_SOURCE.count(BOOTSTRAP_BUILD_VERSION), 1)
        self.assertNotRegex(SERVICE_WORKER_SOURCE, r"(?i)(password|secret|token|cookie|transcript|upload)")


if __name__ == "__main__":
    unittest.main()
