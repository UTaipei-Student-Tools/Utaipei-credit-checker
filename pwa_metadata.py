"""Progressive-web-app metadata for the Streamlit parent document.

Streamlit renders custom components inside an iframe, so the small script below
updates the parent document head idempotently.  The app deliberately does not
register a service worker: transcript-derived results must never be served from
an old offline cache.
"""

from __future__ import annotations

import streamlit.components.v1 as components
import streamlit as st


def _pwa_head_script() -> str:
    """Return the idempotent parent-head metadata injector."""

    return r"""
    <script>
    (() => {
      const doc = window.parent.document;
      const parentUrl = window.parent.location.href;
      const staticBase = new URL("app/static/", new URL(".", parentUrl));

      const upsertLink = (id, rel, file, extra = {}) => {
        let node = doc.getElementById(id);
        if (!node) {
          node = doc.createElement("link");
          node.id = id;
          doc.head.appendChild(node);
        }
        node.rel = rel;
        node.href = new URL(file, staticBase).href;
        Object.entries(extra).forEach(([key, value]) => node.setAttribute(key, value));
      };

      const upsertMeta = (id, name, content) => {
        let node = doc.getElementById(id);
        if (!node) {
          node = doc.createElement("meta");
          node.id = id;
          doc.head.appendChild(node);
        }
        node.name = name;
        node.content = content;
      };

      upsertLink("ut-pwa-manifest", "manifest", "manifest.webmanifest");
      upsertLink("ut-apple-touch-icon", "apple-touch-icon", "icons/apple-touch-icon.png", {sizes: "180x180"});
      upsertLink("ut-favicon", "icon", "icons/favicon-32.png", {sizes: "32x32", type: "image/png"});
      upsertMeta("ut-theme-color", "theme-color", "#081f5c");
      upsertMeta("ut-mobile-capable", "mobile-web-app-capable", "yes");
      upsertMeta("ut-apple-capable", "apple-mobile-web-app-capable", "yes");
      upsertMeta("ut-apple-status", "apple-mobile-web-app-status-bar-style", "black-translucent");
      upsertMeta("ut-apple-title", "apple-mobile-web-app-title", "UT 學分規劃");

      const viewport = doc.querySelector('meta[name="viewport"]');
      if (viewport && !viewport.content.includes("viewport-fit=cover")) {
        viewport.content = `${viewport.content}, viewport-fit=cover`;
      }
    })();
    </script>
    """


def inject_pwa_metadata() -> None:
    """Install app-icon and standalone-mode metadata in the parent page."""

    if hasattr(st, "iframe"):
        st.iframe(_pwa_head_script(), height=1, width=1, tab_index=-1)
    else:  # Streamlit 1.57–1.61 compatibility.
        components.html(_pwa_head_script(), height=0, width=0)


__all__ = ["inject_pwa_metadata"]
