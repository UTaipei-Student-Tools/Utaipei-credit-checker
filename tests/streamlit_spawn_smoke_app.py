"""Credential-free real-Streamlit fixture for the portal spawn supervisor."""

import multiprocessing

import streamlit as st

from scraper import fetch_transcript


def _success_worker(connection, _operation_timeout, _correlation_id):
    """Return a tiny validated PDF after consuming fake pipe credentials."""

    account = None
    password = None
    try:
        if not connection.poll(1.0):
            return
        kind, account, password = connection.recv()
        if kind == "credentials" and account == "smoke-account" and password == "smoke-secret":
            connection.send(("success", b"%PDF-streamlit-spawn"))
    finally:
        account = None
        password = None
        connection.close()


if multiprocessing.current_process().name == "MainProcess":
    result = fetch_transcript(
        "smoke-account",
        "smoke-secret",
        operation_timeout=3.0,
        hard_timeout=5.0,
        worker_target=_success_worker,
    )
    state = "SUCCESS" if result == b"%PDF-streamlit-spawn" else "ERROR"
    st.markdown(f'<div data-streamlit-spawn-state="{state}"></div>', unsafe_allow_html=True)
