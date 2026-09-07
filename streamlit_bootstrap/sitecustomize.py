"""Fail-closed Python startup hook for the UTaipei Streamlit PWA metadata."""

from __future__ import annotations

import sys

try:
    from utaipei_pwa_bootstrap.patch import run_bootstrap

    run_bootstrap(__file__)
except Exception:
    print("UTaipei PWA bootstrap failed closed.", file=sys.stderr)
    raise SystemExit(78) from None
