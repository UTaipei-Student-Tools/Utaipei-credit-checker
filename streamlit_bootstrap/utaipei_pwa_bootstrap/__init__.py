"""Safe, startup-time PWA metadata patching for the UTaipei Streamlit app."""

from .patch import (
    EXPECTED_STREAMLIT_VERSION,
    PWA_MARKER_BEGIN,
    PWA_MARKER_END,
    BootstrapError,
    canonical_metadata_block,
    find_competing_sitecustomize,
    patch_html,
    patch_index_file,
    patch_installed_streamlit_index,
    resolve_streamlit_index,
    run_bootstrap,
)

__all__ = [
    "EXPECTED_STREAMLIT_VERSION",
    "PWA_MARKER_BEGIN",
    "PWA_MARKER_END",
    "BootstrapError",
    "canonical_metadata_block",
    "find_competing_sitecustomize",
    "patch_html",
    "patch_index_file",
    "patch_installed_streamlit_index",
    "resolve_streamlit_index",
    "run_bootstrap",
]
