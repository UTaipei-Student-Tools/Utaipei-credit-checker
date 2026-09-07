"""Test-only isolation for modules mutated by Streamlit's AppTest runner."""

import sys

import pytest

_MISSING = object()


@pytest.fixture(autouse=True)
def _restore_main_module_after_test():
    """Restore the caller's ``__main__`` module after every test.

    Streamlit ``AppTest`` executes a temporary script by replacing
    ``sys.modules["__main__"]``.  Keeping that temporary module around leaks
    its import state into later tests, notably multiprocessing spawn tests.
    Capture the state at test setup and restore it even when the test raises.
    """

    original_main = sys.modules.get("__main__", _MISSING)
    try:
        yield
    finally:
        if original_main is _MISSING:
            sys.modules.pop("__main__", None)
        else:
            sys.modules["__main__"] = original_main
