"""Fail-closed Streamlit startup patch for the UTaipei PWA identity.

The Streamlit SDK serves its static ``index.html`` before the Python app has
run. iOS therefore needs the title and icon links in that file, not in a
runtime component or JavaScript callback. This module is intentionally
stdlib-only so it can run from ``sitecustomize`` before Streamlit starts.
"""

from __future__ import annotations

import importlib
import os
import re
import stat
import sys
import tempfile
from pathlib import Path
from types import ModuleType

EXPECTED_STREAMLIT_VERSION = "1.57.0"
BOOTSTRAP_BUILD_VERSION = "0.2.0"
PWA_MARKER_BEGIN = "<!-- UTAIPEI_PWA_V2_BEGIN -->"
PWA_MARKER_END = "<!-- UTAIPEI_PWA_V2_END -->"
SERVICE_WORKER_MARKER_BEGIN = "/* UTAIPEI_SERVICE_WORKER_V2_BEGIN */"
SERVICE_WORKER_MARKER_END = "/* UTAIPEI_SERVICE_WORKER_V2_END */"
SERVICE_WORKER_FILENAME = "service-worker.js"

_TAG_RE = re.compile(r"<(?P<tag>link|meta)\b[^>]*>", re.IGNORECASE)
_TITLE_RE = re.compile(r"<title\b[^>]*>.*?</title>", re.IGNORECASE | re.DOTALL)
_ATTR_RE = re.compile(
    r"(?P<name>[A-Za-z_:][A-Za-z0-9_.:-]*)\s*=\s*(?:\"(?P<double>[^\"]*)\"|'(?P<single>[^']*)'|(?P<bare>[^\s>]+))",
    re.IGNORECASE,
)
_SERVICE_WORKER_REGISTER_RE = re.compile(r"\bserviceWorker\s*\.\s*register\b")
_MANAGED_SERVICE_WORKER_SCRIPT_RE = re.compile(
    r"[ \t]*<script\b[^>]*\bid\s*=\s*(?:\"ut-pwa-service-worker\"|'ut-pwa-service-worker')[^>]*>.*?</script>[ \t]*(?:\r?\n)?",
    re.IGNORECASE | re.DOTALL,
)


_SERVICE_WORKER_TEMPLATE = r"""/* UTAIPEI_SERVICE_WORKER_V2_BEGIN */
'use strict';

const BUILD_VERSION = '__UTAIPEI_BUILD_VERSION__';
const CACHE_PREFIX = 'utaipei-graduation-static-';
const CACHE_NAME = `${CACHE_PREFIX}${BUILD_VERSION}`;
const STATIC_SHELL_ASSETS = new Set([
  '/app/static/manifest-v2.webmanifest',
  '/app/static/icons/ut-graduation-v2-32.png',
  '/app/static/icons/ut-graduation-v2-180.png',
  '/app/static/icons/ut-graduation-v2-192.png',
  '/app/static/icons/ut-graduation-v2-512.png'
]);

const isPublicShellRequest = (request) => {
  if (request.method !== 'GET' || request.mode === 'navigate') return false;
  const url = new URL(request.url);
  return url.origin === self.location.origin && !url.search && STATIC_SHELL_ASSETS.has(url.pathname);
};

const clearOwnedStaticCaches = async () => {
  const keys = await caches.keys();
  await Promise.all(keys.filter((key) => key.startsWith(CACHE_PREFIX)).map((key) => caches.delete(key)));
};

self.addEventListener('install', (event) => {
  event.waitUntil(caches.open(CACHE_NAME).then((cache) => cache.addAll([...STATIC_SHELL_ASSETS])));
});

self.addEventListener('activate', (event) => {
  event.waitUntil((async () => {
    const keys = await caches.keys();
    await Promise.all(keys
      .filter((key) => key.startsWith(CACHE_PREFIX) && key !== CACHE_NAME)
      .map((key) => caches.delete(key)));
    await self.clients.claim();
  })());
});

self.addEventListener('message', (event) => {
  const type = event.data && event.data.type;
  if (type === 'SKIP_WAITING') {
    event.waitUntil(self.skipWaiting());
    return;
  }
  if (type === 'CHECK_VERSION') {
    if (event.source && typeof event.source.postMessage === 'function') {
      event.source.postMessage({ type: 'PWA_VERSION', version: BUILD_VERSION });
    }
    return;
  }
  if (type === 'CLEAR_STATIC_CACHES') {
    event.waitUntil(clearOwnedStaticCaches().then(() => {
      if (event.source && typeof event.source.postMessage === 'function') {
        event.source.postMessage({ type: 'STATIC_CACHES_CLEARED', version: BUILD_VERSION });
      }
    }));
  }
});

self.addEventListener('fetch', (event) => {
  if (!isPublicShellRequest(event.request)) return;
  event.respondWith((async () => {
    const cache = await caches.open(CACHE_NAME);
    try {
      const response = await fetch(event.request, { cache: 'no-store' });
      if (response.ok) await cache.put(event.request, response.clone());
      return response;
    } catch (error) {
      const cached = await cache.match(event.request);
      if (cached) return cached;
      throw error;
    }
  })());
});
/* UTAIPEI_SERVICE_WORKER_V2_END */
"""

SERVICE_WORKER_SOURCE = _SERVICE_WORKER_TEMPLATE.replace(
    "__UTAIPEI_BUILD_VERSION__", BOOTSTRAP_BUILD_VERSION
)


class BootstrapError(RuntimeError):
    """Raised when the bootstrap cannot prove that it is safe to continue."""


def _attrs(tag: str) -> dict[str, str]:
    result: dict[str, str] = {}
    for match in _ATTR_RE.finditer(tag):
        result[match.group("name").lower()] = (
            match.group("double") or match.group("single") or match.group("bare") or ""
        )
    return result


def _is_stale_link(tag: str) -> bool:
    attributes = _attrs(tag)
    tag_id = attributes.get("id", "").lower()
    rel_values = set(attributes.get("rel", "").lower().split())
    href = attributes.get("href", "").lower()
    return (
        tag_id.startswith(("ut-pwa-", "ut-apple-", "ut-favicon"))
        or bool(rel_values & {"manifest", "apple-touch-icon", "icon", "shortcut"})
        or "manifest.webmanifest" in href
        or "apple-touch-icon" in href
        or "favicon" in href
    )


def _is_stale_meta(tag: str) -> bool:
    attributes = _attrs(tag)
    tag_id = attributes.get("id", "").lower()
    name = attributes.get("name", "").lower()
    return tag_id.startswith(("ut-pwa-", "ut-apple-", "ut-favicon")) or name in {
        "application-name",
        "theme-color",
        "mobile-web-app-capable",
        "apple-mobile-web-app-capable",
        "apple-mobile-web-app-status-bar-style",
        "apple-mobile-web-app-title",
        "viewport",
    }


def _remove_existing_pwa_metadata(html: str) -> str:
    """Remove all known old metadata before adding one canonical block."""

    managed_block = re.compile(
        rf"[ \t]*{re.escape(PWA_MARKER_BEGIN)}.*?{re.escape(PWA_MARKER_END)}[ \t]*(?:\r?\n)?",
        re.IGNORECASE | re.DOTALL,
    )
    html = managed_block.sub("", html)
    html = _MANAGED_SERVICE_WORKER_SCRIPT_RE.sub("", html)

    def remove_stale_tag(match: re.Match[str]) -> str:
        tag = match.group(0)
        tag_name = match.group("tag").lower()
        if tag_name == "link" and _is_stale_link(tag):
            return ""
        if tag_name == "meta" and _is_stale_meta(tag):
            return ""
        return tag

    html = _TAG_RE.sub(remove_stale_tag, html)
    return _TITLE_RE.sub("", html)


def canonical_metadata_block() -> str:
    """Return the canonical metadata written into the initial HTML head."""

    return f"""    {PWA_MARKER_BEGIN}
    <meta name="viewport" content="width=device-width, initial-scale=1, shrink-to-fit=no, viewport-fit=cover" />
    <meta name="application-name" content="北市大畢業通" />
    <meta name="theme-color" content="#1E3A5F" />
    <meta name="mobile-web-app-capable" content="yes" />
    <meta name="apple-mobile-web-app-capable" content="yes" />
    <meta name="apple-mobile-web-app-status-bar-style" content="black" />
    <meta name="apple-mobile-web-app-title" content="北市大畢業通" />
    <link rel="manifest" href="/app/static/manifest-v2.webmanifest" />
    <link rel="apple-touch-icon" sizes="180x180" type="image/png" href="/app/static/icons/ut-graduation-v2-180.png" />
    <link rel="icon" sizes="32x32" type="image/png" href="/app/static/icons/ut-graduation-v2-32.png" />
    <title>北市大畢業通</title>
    <script id="ut-pwa-service-worker">
    (() => {{
      if (!('serviceWorker' in navigator)) return;
      window.addEventListener('load', () => {{
        navigator.serviceWorker.register('/service-worker.js', {{
          scope: '/',
          updateViaCache: 'none'
        }}).catch(() => {{}});
      }}, {{ once: true }});
    }})();
    </script>
    {PWA_MARKER_END}"""


def patch_html(html: str) -> str:
    """Return canonical initial HTML or raise on an unsupported/malformed file."""

    if not html.strip():
        raise BootstrapError("Streamlit index.html is empty")
    if not re.search(r"<html\b[^>]*>", html, re.IGNORECASE):
        raise BootstrapError("Streamlit index.html has no <html> element")
    if not re.search(r"<head\b[^>]*>", html, re.IGNORECASE):
        raise BootstrapError("Streamlit index.html has no <head> element")
    if not re.search(r"</head\s*>", html, re.IGNORECASE):
        raise BootstrapError("Streamlit index.html has no closing </head> element")
    if not re.search(r"</html\s*>", html, re.IGNORECASE):
        raise BootstrapError("Streamlit index.html has no closing </html> element")

    clean_html = _remove_existing_pwa_metadata(html)
    head_end = re.search(r"</head\s*>", clean_html, re.IGNORECASE)
    if head_end is None:  # pragma: no cover - guarded above
        raise BootstrapError("Unable to locate closing </head> after cleanup")

    prefix = clean_html[: head_end.start()].rstrip()
    suffix = clean_html[head_end.start() :].lstrip()
    patched = f"{prefix}\n{canonical_metadata_block()}\n{suffix}"

    if patched.count(PWA_MARKER_BEGIN) != 1 or patched.count(PWA_MARKER_END) != 1:
        raise BootstrapError("PWA metadata marker count is not exactly one")
    if len(_TITLE_RE.findall(patched)) != 1:
        raise BootstrapError("PWA patch did not produce exactly one title")
    if patched.count('name="apple-mobile-web-app-title" content="北市大畢業通"') != 1:
        raise BootstrapError("PWA patch did not produce exactly one iOS title")
    if patched.count('name="apple-mobile-web-app-status-bar-style" content="black"') != 1:
        raise BootstrapError("PWA patch did not produce exactly one opaque iOS status-bar style")
    if "black-translucent" in patched.lower():
        raise BootstrapError("PWA patch must not produce a translucent iOS status-bar style")
    if patched.count('rel="manifest" href="/app/static/manifest-v2.webmanifest"') != 1:
        raise BootstrapError("PWA patch did not produce exactly one manifest link")
    if patched.count('rel="apple-touch-icon" sizes="180x180"') != 1:
        raise BootstrapError("PWA patch did not produce exactly one Apple icon link")
    if len(_SERVICE_WORKER_REGISTER_RE.findall(patched)) != 1:
        raise BootstrapError("PWA patch must contain exactly one service-worker registration")
    if patched.count("id=\"ut-pwa-service-worker\"") != 1:
        raise BootstrapError("PWA patch must contain exactly one managed service-worker script")
    if "register('/service-worker.js'" not in patched:
        raise BootstrapError("PWA patch must register the root service-worker path")
    if "scope: '/'" not in patched or "updateViaCache: 'none'" not in patched:
        raise BootstrapError("PWA patch must request an uncached root scope")
    return patched


def _is_regular_file(path: Path) -> bool:
    try:
        return stat.S_ISREG(os.lstat(path).st_mode)
    except OSError:
        return False


def _is_regular_directory(path: Path) -> bool:
    try:
        return stat.S_ISDIR(os.lstat(path).st_mode)
    except OSError:
        return False


def validate_static_root(package_root: Path, static_root: Path) -> Path:
    """Validate the installed Streamlit static directory without following links."""

    package_root = Path(package_root)
    static_root = Path(static_root)
    if package_root.is_symlink() or static_root.is_symlink():
        raise BootstrapError("Streamlit package and static directory must not be symlinks")
    if not _is_regular_directory(package_root) or not _is_regular_directory(static_root):
        raise BootstrapError("Streamlit package and static paths must be regular directories")

    # Check every existing component between the package and static roots. A
    # symlinked ancestor can otherwise resolve inside the package and evade a
    # check made only on the final directory.
    current = static_root
    while True:
        if current.is_symlink():
            raise BootstrapError("Streamlit static path contains a symlink")
        if current == package_root:
            break
        parent = current.parent
        if parent == current:
            raise BootstrapError("Streamlit static directory is outside the installed package")
        current = parent

    try:
        package_resolved = package_root.resolve(strict=True)
        static_resolved = static_root.resolve(strict=True)
        static_resolved.relative_to(package_resolved)
    except (OSError, ValueError) as exc:
        raise BootstrapError("Streamlit static directory is outside the installed package") from exc
    if static_resolved == package_resolved:
        raise BootstrapError("Streamlit static directory must be below the installed package")
    return static_root


def validate_index_path(package_root: Path, index_path: Path) -> Path:
    """Validate a static index is a regular non-symlink inside Streamlit."""

    package_root = Path(package_root)
    index_path = Path(index_path)
    try:
        package_resolved = package_root.resolve(strict=True)
        index_resolved = index_path.resolve(strict=True)
    except OSError as exc:
        raise BootstrapError("Unable to resolve Streamlit static path") from exc
    try:
        index_resolved.relative_to(package_resolved)
    except ValueError as exc:
        raise BootstrapError("Streamlit static index is outside the installed package") from exc
    if index_path.is_symlink() or not _is_regular_file(index_path):
        raise BootstrapError("Streamlit static index must be a regular non-symlink file")
    static_dir = index_path.parent
    if static_dir.is_symlink():
        raise BootstrapError("Streamlit static directory must not be a symlink")
    return index_path


def resolve_streamlit_index(
    streamlit_module: ModuleType | None = None,
    *,
    expected_version: str = EXPECTED_STREAMLIT_VERSION,
) -> Path:
    """Resolve and validate the installed Streamlit static index."""

    module = streamlit_module or importlib.import_module("streamlit")
    actual_version = str(getattr(module, "__version__", ""))
    if actual_version != expected_version:
        raise BootstrapError(f"Unsupported Streamlit version: expected {expected_version}")
    module_file_value = getattr(module, "__file__", None)
    if not module_file_value:
        raise BootstrapError("Streamlit module has no file path")
    module_file = Path(module_file_value)
    package_root = module_file.parent
    if module_file.is_symlink() or package_root.is_symlink():
        raise BootstrapError("Installed Streamlit package must not be symlinked")
    static_dir = package_root / "static"
    index_path = static_dir / "index.html"
    if static_dir.is_symlink():
        raise BootstrapError("Streamlit static directory must not be a symlink")
    return validate_index_path(package_root, index_path)


def find_competing_sitecustomize(
    own_file: Path | None = None,
    *,
    path_entries: list[str] | tuple[str, ...] | None = None,
) -> Path | None:
    """Find another filesystem ``sitecustomize.py`` without importing it.

    Python can also load modules from zip files or custom import hooks; those
    cannot be identified safely without executing arbitrary code. All ordinary
    filesystem entries are checked and any unknown regular file is treated as a
    collision so the bootstrap does not silently chain untrusted startup code.
    """

    own_path = Path(own_file or __file__).resolve()
    entries = sys.path if path_entries is None else path_entries
    seen: set[Path] = set()
    for raw_entry in entries:
        base = Path.cwd() if not raw_entry else Path(raw_entry)
        candidate = base / "sitecustomize.py"
        try:
            candidate_resolved = candidate.resolve(strict=False)
            if candidate_resolved == own_path or candidate_resolved in seen:
                continue
            seen.add(candidate_resolved)
            if candidate.is_file():
                return candidate
        except (OSError, RuntimeError) as exc:
            raise BootstrapError("Unable to inspect sitecustomize search path") from exc
    return None


def _write_temp_bytes(directory: Path, filename: str, data: bytes, mode: int) -> Path:
    fd, raw_path = tempfile.mkstemp(prefix=f".{filename}.utaipei-", suffix=".tmp", dir=directory)
    temp_path = Path(raw_path)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(temp_path, mode)
        if temp_path.is_symlink() or not _is_regular_file(temp_path):
            raise BootstrapError("Temporary PWA patch file is not a regular file")
        return temp_path
    except Exception:
        try:
            temp_path.unlink(missing_ok=True)
        except OSError:
            pass
        raise


def _verify_service_worker(worker_path: Path, expected_bytes: bytes) -> None:
    if worker_path.is_symlink() or not _is_regular_file(worker_path):
        raise BootstrapError("Installed service-worker.js must be a regular non-symlink file")
    try:
        observed = worker_path.read_bytes()
    except OSError as exc:
        raise BootstrapError("Unable to read installed service-worker.js") from exc
    if observed != expected_bytes:
        raise BootstrapError("Service Worker installation verification failed")
    try:
        decoded = observed.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise BootstrapError("Service Worker is not valid UTF-8") from exc
    if not decoded.startswith(SERVICE_WORKER_MARKER_BEGIN) or not decoded.rstrip().endswith(
        SERVICE_WORKER_MARKER_END
    ):
        raise BootstrapError("Service Worker markers are missing")


def install_service_worker(static_root: Path, *, package_root: Path | None = None) -> bool:
    """Install the managed root-scope worker into a validated Streamlit static root.

    An existing file is replaced only when it carries this bootstrap's audit
    markers. Unknown files, links, and non-regular filesystem objects are
    treated as collisions and stop startup rather than being overwritten.
    """

    static_root = Path(static_root)
    package_root = Path(package_root) if package_root is not None else static_root.parent
    static_root = validate_static_root(package_root, static_root)
    worker_path = static_root / SERVICE_WORKER_FILENAME
    expected_bytes = SERVICE_WORKER_SOURCE.encode("utf-8")

    has_existing = os.path.lexists(worker_path)
    original_bytes: bytes | None = None
    original_mode = 0o644
    if has_existing:
        if worker_path.is_symlink() or not _is_regular_file(worker_path):
            raise BootstrapError("Existing service-worker.js is not a regular non-symlink file")
        try:
            original_bytes = worker_path.read_bytes()
            original_mode = stat.S_IMODE(os.lstat(worker_path).st_mode)
        except OSError as exc:
            raise BootstrapError("Unable to inspect existing service-worker.js") from exc
        if original_bytes == expected_bytes:
            _verify_service_worker(worker_path, expected_bytes)
            return False
        try:
            original_text = original_bytes.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise BootstrapError("Existing service-worker.js is not valid UTF-8") from exc
        if SERVICE_WORKER_MARKER_BEGIN not in original_text or SERVICE_WORKER_MARKER_END not in original_text:
            raise BootstrapError("Unknown service-worker.js collision detected")

    temp_path: Path | None = None
    replaced = False
    try:
        temp_path = _write_temp_bytes(static_root, SERVICE_WORKER_FILENAME, expected_bytes, original_mode)
        os.replace(temp_path, worker_path)
        temp_path = None
        replaced = True
        _verify_service_worker(worker_path, expected_bytes)
        return True
    except Exception:
        if replaced:
            rollback_path: Path | None = None
            try:
                if original_bytes is None:
                    # Only remove the exact managed file we just committed.
                    if not worker_path.is_symlink() and _is_regular_file(worker_path):
                        worker_path.unlink()
                else:
                    rollback_path = _write_temp_bytes(
                        static_root,
                        SERVICE_WORKER_FILENAME,
                        original_bytes,
                        original_mode,
                    )
                    os.replace(rollback_path, worker_path)
                    rollback_path = None
            except Exception as rollback_error:
                raise BootstrapError("Service Worker installation failed and rollback was unsuccessful") from rollback_error
            finally:
                if rollback_path is not None:
                    rollback_path.unlink(missing_ok=True)
        raise
    finally:
        if temp_path is not None:
            temp_path.unlink(missing_ok=True)


def _verify_committed(index_path: Path, expected_bytes: bytes) -> None:
    validate_index_path(index_path.parent.parent, index_path)
    observed = index_path.read_bytes()
    if observed != expected_bytes:
        raise BootstrapError("PWA patch verification failed")
    decoded = observed.decode("utf-8")
    if patch_html(decoded) != decoded:
        raise BootstrapError("PWA patch is not idempotent after write")


def patch_index_file(index_path: Path) -> bool:
    """Atomically patch one validated index and roll back failed post-write checks."""

    index_path = Path(index_path)
    if index_path.is_symlink() or not _is_regular_file(index_path):
        raise BootstrapError("Streamlit static index must be a regular non-symlink file")
    if index_path.parent.is_symlink():
        raise BootstrapError("Streamlit static directory must not be a symlink")
    original_bytes = index_path.read_bytes()
    try:
        original_text = original_bytes.decode("utf-8")
        patched_bytes = patch_html(original_text).encode("utf-8")
    except UnicodeDecodeError as exc:
        raise BootstrapError("Streamlit index is not valid UTF-8") from exc
    if patched_bytes == original_bytes:
        return False

    original_mode = stat.S_IMODE(os.lstat(index_path).st_mode)
    temp_path: Path | None = None
    replaced = False
    try:
        temp_path = _write_temp_bytes(index_path.parent, index_path.name, patched_bytes, original_mode)
        os.replace(temp_path, index_path)
        temp_path = None
        replaced = True
        _verify_committed(index_path, patched_bytes)
        return True
    except Exception:
        if replaced:
            rollback_path: Path | None = None
            try:
                rollback_path = _write_temp_bytes(index_path.parent, index_path.name, original_bytes, original_mode)
                os.replace(rollback_path, index_path)
                rollback_path = None
            except Exception as rollback_error:
                raise BootstrapError("PWA patch failed and rollback was unsuccessful") from rollback_error
            finally:
                if rollback_path is not None:
                    rollback_path.unlink(missing_ok=True)
        raise
    finally:
        if temp_path is not None:
            temp_path.unlink(missing_ok=True)


def patch_installed_streamlit_index(
    streamlit_module: ModuleType | None = None,
    *,
    expected_version: str = EXPECTED_STREAMLIT_VERSION,
) -> bool:
    """Version-check, resolve, and atomically patch the installed index."""

    index_path = resolve_streamlit_index(streamlit_module, expected_version=expected_version)
    # Install the worker before mutating HTML. This makes a foreign worker
    # collision fail before the startup document is changed.
    worker_changed = install_service_worker(index_path.parent, package_root=index_path.parent.parent)
    index_changed = patch_index_file(index_path)
    return worker_changed or index_changed


def run_bootstrap(own_sitecustomize_file: Path | None = None) -> bool:
    """Run the safe startup sequence and return whether bytes changed."""

    # ``run_bootstrap`` lives one package below the installed top-level
    # ``sitecustomize.py``. Derive that path by default, while allowing the
    # startup shim to pass its own exact path explicitly.
    own_file = own_sitecustomize_file or Path(__file__).resolve().parent.parent / "sitecustomize.py"
    collision = find_competing_sitecustomize(own_file=own_file)
    if collision is not None:
        raise BootstrapError("Unknown competing sitecustomize detected")
    return patch_installed_streamlit_index()


__all__ = [
    "EXPECTED_STREAMLIT_VERSION",
    "BOOTSTRAP_BUILD_VERSION",
    "PWA_MARKER_BEGIN",
    "PWA_MARKER_END",
    "SERVICE_WORKER_MARKER_BEGIN",
    "SERVICE_WORKER_MARKER_END",
    "SERVICE_WORKER_FILENAME",
    "SERVICE_WORKER_SOURCE",
    "BootstrapError",
    "canonical_metadata_block",
    "find_competing_sitecustomize",
    "install_service_worker",
    "patch_html",
    "patch_index_file",
    "patch_installed_streamlit_index",
    "resolve_streamlit_index",
    "run_bootstrap",
    "validate_static_root",
    "validate_index_path",
]
