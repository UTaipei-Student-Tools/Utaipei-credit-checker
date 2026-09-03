"""
Shared presentation primitives for the UTaipei graduation credit dashboard.

The app renders a few deliberately small HTML fragments so that course rows and
progress bars remain responsive.  All visual decisions live in the semantic
token layer below; report and sidebar code should only select component classes.
"""

import math
from html import escape
from pathlib import Path

import streamlit as st
import streamlit.components.v1 as components


def format_credit(value):
    """Format a credit value consistently without changing its numeric data."""

    if value in (None, ""):
        return ""
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return str(value)
    if not math.isfinite(numeric):
        return str(value)
    return f"{numeric:.1f}"


def render_html(markup, *, ui=None):
    """Render a non-script HTML fragment through Streamlit's HTML element.

    ``st.markdown(..., unsafe_allow_html=True)`` is intentionally kept out of
    this seam.  Large style/raw-HTML blocks can be parsed as visible Markdown
    by a deployed Streamlit build, which exposes implementation markup to the
    user.  ``st.html`` keeps the fragment in the HTML element boundary.  The
    fallback is only for older test/legacy runtimes that do not expose
    ``st.html``; it is never used for JavaScript.
    """

    markup = str(markup)
    if "<script" in markup.casefold():
        raise ValueError("render_html only accepts non-script markup")
    ui = ui or st
    html_renderer = getattr(ui, "html", None)
    if callable(html_renderer):
        return html_renderer(markup)
    markdown_renderer = getattr(ui, "markdown", None)
    if callable(markdown_renderer):  # Streamlit 1.49 and older compatibility.
        return markdown_renderer(markup, unsafe_allow_html=True)
    raise AttributeError("Streamlit HTML renderer is unavailable")


def setup_page():
    page_icon = Path(__file__).resolve().parent / "static" / "icons" / "ut-graduation-v2-32.png"
    st.set_page_config(
        page_title="北市大畢業通",
        page_icon=str(page_icon) if page_icon.exists() else "🎓",
        layout="wide",
        initial_sidebar_state="collapsed",
    )
    inject_theme_css()
    render_html('<a class="skip-link" href="#main-content">跳到主要內容</a>')
    _inject_update_menu_script()


def _build_update_menu_script():
    """Build the hidden parent-document bridges for menu updates and theme.

    Streamlit owns the header menu, so there is no Python callback to attach to
    here.  Both bridges are deliberately idempotent: stable state is kept on the
    parent window, the menu item is keyed by a stable test id, and the theme is
    reflected from Streamlit's checked theme choice or effective header signal.
    """

    return """
<script>
(() => {
    const LABEL = "更新至最新版";
    const ITEM_TEST_ID = "utMainMenuItem-update";
    const STATE_KEY = "__utaipeiGraduationMenuEnhancer";
    // This marker covers all transient student state, including data that was
    // already exported but is still resident in this browser session.  The
    // server owns the truth table; the DOM only carries a non-sensitive bool.
    const ANALYSIS_STATE_SELECTOR = "#utaipei-analysis-state[data-analysis-active='true']";
    const STATIC_CACHE_PREFIX = "utaipei-graduation-static-";
    const THEME_STATE_KEY = "__utaipeiGraduationThemeBridge";
    const THEME_STATE_VERSION = 2;
    const THEME_ATTRIBUTE = "data-utaipei-theme";
    const DARK_MEDIA_QUERY = "(prefers-color-scheme: dark)";

    function themePreferenceFromElement(element) {
        if (!element || element.getAttribute("aria-checked") !== "true") return "";
        const testId = element.getAttribute("data-testid");
        if (testId === "stMainMenuItem-theme-Light") return "light";
        if (testId === "stMainMenuItem-theme-Dark") return "dark";
        if (testId === "stMainMenuItem-theme-System") return "system";
        return "";
    }

    function readCheckedThemePreference(parentWindow) {
        const document = parentWindow.document;
        const themeItems = [
            "stMainMenuItem-theme-Light",
            "stMainMenuItem-theme-Dark",
            "stMainMenuItem-theme-System",
        ];
        for (const testId of themeItems) {
            const item = document.querySelector('[data-testid="' + testId + '"]');
            const preference = themePreferenceFromElement(item);
            if (preference) return preference;
        }
        return "";
    }

    function readThemePreferenceFromMutations(mutations) {
        for (const record of mutations || []) {
            if (record.type !== "attributes" || record.attributeName !== "aria-checked") continue;
            const preference = themePreferenceFromElement(record.target);
            if (preference) return preference;
        }
        return "";
    }

    function themeFromHeaderBackground(value) {
        const normalized = String(value || "").trim().toLowerCase();
        if (!normalized || normalized === "transparent") return "";
        const channels = normalized.match(/[0-9.]+/g);
        if (!channels || channels.length < 3) return "";

        const red = Number(channels[0]);
        const green = Number(channels[1]);
        const blue = Number(channels[2]);
        let alpha = channels.length >= 4 ? Number(channels[3]) : 1;
        if (normalized.includes("%") && channels.length >= 4) alpha /= 100;
        if (![red, green, blue, alpha].every(Number.isFinite) || alpha <= 0.01) return "";

        const luminance = (0.2126 * red + 0.7152 * green + 0.0722 * blue) / 255;
        return luminance >= 0.5 ? "light" : "dark";
    }

    function readHeaderTheme(parentWindow) {
        const header = parentWindow.document.querySelector('[data-testid="stHeader"]');
        if (!header || typeof parentWindow.getComputedStyle !== "function") return "";

        try {
            const computed = parentWindow.getComputedStyle(header);
            const background = computed && (computed.backgroundColor
                || (typeof computed.getPropertyValue === "function"
                    ? computed.getPropertyValue("background-color")
                    : ""));
            return themeFromHeaderBackground(background);
        } catch (_error) {
            return "";
        }
    }

    function readAppColorScheme(parentWindow) {
        const app = parentWindow.document.querySelector(".stApp");
        if (!app || typeof parentWindow.getComputedStyle !== "function") {
            return "";
        }

        try {
            const computed = parentWindow.getComputedStyle(app);
            const values = [
                computed && computed.colorScheme,
                computed && typeof computed.getPropertyValue === "function"
                    ? computed.getPropertyValue("color-scheme")
                    : "",
            ];
            for (const value of values) {
                const scheme = String(value || "")
                    .toLowerCase()
                    .split(/\\s+/)
                    .find((candidate) => candidate === "light" || candidate === "dark");
                if (scheme) return scheme;
            }
        } catch (_error) {
            // Parent DOM access can be unavailable in embedded deployments.
        }
        return "";
    }

    function readMediaTheme(parentWindow, mediaQuery) {
        if (mediaQuery) return mediaQuery.matches ? "dark" : "light";
        if (typeof parentWindow.matchMedia !== "function") return "";
        try {
            const currentMediaQuery = parentWindow.matchMedia(DARK_MEDIA_QUERY);
            return currentMediaQuery.matches ? "dark" : "light";
        } catch (_error) {
            return "";
        }
    }

    function syncTheme(parentWindow, state, mutations) {
        const root = parentWindow.document.documentElement;
        if (!root) return;

        const checkedPreference = readCheckedThemePreference(parentWindow);
        if (checkedPreference) {
            state.preference = checkedPreference;
        } else {
            const mutationPreference = readThemePreferenceFromMutations(mutations);
            if (mutationPreference) state.preference = mutationPreference;
        }

        let theme = "";
        if (checkedPreference === "light" || state.preference === "light") {
            state.preference = "light";
            theme = "light";
        } else if (checkedPreference === "dark" || state.preference === "dark") {
            state.preference = "dark";
            theme = "dark";
        } else if (checkedPreference === "system" || state.preference === "system") {
            state.preference = "system";
            theme = readMediaTheme(parentWindow, state.mediaQuery);
        } else {
            // Streamlit's header is outside the app palette we inject.  It is
            // therefore the useful startup/reload signal before .stApp can be
            // trusted, because our own media CSS can affect .stApp's computed
            // color-scheme.
            theme = readHeaderTheme(parentWindow);
            if (!theme) theme = readAppColorScheme(parentWindow);
            if (!theme) theme = readMediaTheme(parentWindow, state.mediaQuery);
        }
        if (!theme || root.getAttribute(THEME_ATTRIBUTE) === theme) return;
        root.setAttribute(THEME_ATTRIBUTE, theme);
    }

    function installThemeBridge(parentWindow) {
        const document = parentWindow.document;
        const root = document.documentElement;
        if (!root) return;

        let state = parentWindow[THEME_STATE_KEY];
        if (!state || state.version !== THEME_STATE_VERSION || typeof state.sync !== "function") {
            if (state && state.observer && typeof state.observer.disconnect === "function") {
                state.observer.disconnect();
            }
            if (state && state.mediaQuery && state.mediaListener) {
                if (typeof state.mediaQuery.removeEventListener === "function") {
                    state.mediaQuery.removeEventListener("change", state.mediaListener);
                } else if (typeof state.mediaQuery.removeListener === "function") {
                    state.mediaQuery.removeListener(state.mediaListener);
                }
            }

            let mediaQuery = null;
            try {
                if (typeof parentWindow.matchMedia === "function") {
                    mediaQuery = parentWindow.matchMedia(DARK_MEDIA_QUERY);
                }
            } catch (_error) {
                mediaQuery = null;
            }

            state = {
                version: THEME_STATE_VERSION,
                mediaQuery,
                mediaListener: null,
                observer: null,
                preference: "",
                sync: null,
            };
            state.sync = (mutations) => syncTheme(parentWindow, state, mutations);
            parentWindow[THEME_STATE_KEY] = state;

            if (typeof parentWindow.MutationObserver === "function") {
                state.observer = new parentWindow.MutationObserver((mutations) => state.sync(mutations));
                state.observer.observe(root, {
                    attributes: true,
                    attributeFilter: [
                        "class",
                        "style",
                        "aria-checked",
                        "data-theme",
                        "data-streamlit-theme",
                        "data-testid",
                    ],
                    childList: true,
                    subtree: true,
                });
            }

            if (state.mediaQuery) {
                state.mediaListener = () => state.sync();
                if (typeof state.mediaQuery.addEventListener === "function") {
                    state.mediaQuery.addEventListener("change", state.mediaListener);
                } else if (typeof state.mediaQuery.addListener === "function") {
                    state.mediaQuery.addListener(state.mediaListener);
                }
            }
        }
        state.sync();
    }

    function markScriptHost() {
        try {
            const candidate = window.frameElement || document.currentScript;
            const element = candidate && candidate.closest
                ? candidate.closest('[data-testid="stElementContainer"]')
                : null;
            if (element) {
                element.setAttribute("data-utaipei-menu-script-host", "true");
                element.style.display = "none";
            }
        } catch (_error) {
            // The bridge is optional; a blocked parent must not stop the app.
        }
    }

    function waitForWorkerActivation(parentWindow, worker) {
        if (!worker || !worker.addEventListener) {
            return Promise.resolve();
        }
        return new Promise((resolve) => {
            let settled = false;
            const finish = () => {
                if (settled) return;
                settled = true;
                resolve();
            };
            worker.addEventListener("statechange", () => {
                if (worker.state === "activated" || worker.state === "redundant") finish();
            }, { once: false });
            if (parentWindow.navigator && parentWindow.navigator.serviceWorker) {
                parentWindow.navigator.serviceWorker.addEventListener("controllerchange", finish, { once: true });
            }
            // A worker is allowed to finish activation during the reload.  Do
            // not hold the menu open indefinitely when that happens.
            parentWindow.setTimeout(finish, 2500);
        });
    }

    async function clearStaticCaches(parentWindow) {
        const caches = parentWindow.caches;
        if (!caches || typeof caches.keys !== "function") return;
        const cacheNames = await caches.keys();
        await Promise.all(cacheNames
            .filter((cacheName) => cacheName.startsWith(STATIC_CACHE_PREFIX))
            .map((cacheName) => caches.delete(cacheName)));
    }

    async function activateUpdate(parentWindow, item) {
        const document = parentWindow.document;
        const unsavedAnalysis = document.querySelector(ANALYSIS_STATE_SELECTOR);
        // Check before touching the worker or Cache Storage.  Cancel therefore
        // has no mutation and no navigation side effect.
        if (unsavedAnalysis) {
            if (!parentWindow.confirm("本次工作階段仍有暫存分析資料，更新後可能需要重新確認上傳內容。仍要更新嗎？")) {
                return;
            }
        }

        item.setAttribute("aria-busy", "true");
        item.setAttribute("aria-disabled", "true");
        try {
            const serviceWorker = parentWindow.navigator && parentWindow.navigator.serviceWorker;
            if (serviceWorker && typeof serviceWorker.getRegistration === "function") {
                const registration = await serviceWorker.getRegistration().catch(() => null);
                if (registration && typeof registration.update === "function") {
                    await registration.update().catch(() => undefined);
                }
                if (registration && registration.active && typeof registration.active.postMessage === "function") {
                    registration.active.postMessage({ type: "GET_VERSION" });
                    registration.active.postMessage({ type: "CHECK_VERSION" });
                }
                const waitingWorker = registration && (registration.waiting || registration.installing);
                if (waitingWorker && typeof waitingWorker.postMessage === "function") {
                    waitingWorker.postMessage({ type: "SKIP_WAITING" });
                    await waitForWorkerActivation(parentWindow, waitingWorker);
                }
            }

            if (serviceWorker && serviceWorker.controller && typeof serviceWorker.controller.postMessage === "function") {
                serviceWorker.controller.postMessage({ type: "CLEAR_STATIC_CACHES" });
            }
            await clearStaticCaches(parentWindow);
            const url = new URL(parentWindow.location.href);
            url.searchParams.set("_ut_update", String(Date.now()));
            // Keep the marker non-sensitive and reload the same document.  No
            // local/session storage, cookie, or uploaded student data is cleared.
            parentWindow.history.replaceState(null, "", url.toString());
            parentWindow.location.reload();
        } catch (_error) {
            // A missing or unavailable SW/cache API must not make the update
            // action destructive.  The app remains usable and can be retried.
            item.removeAttribute("aria-busy");
            item.removeAttribute("aria-disabled");
        }
    }

    function installUpdateItem(parentWindow) {
        const document = parentWindow.document;
        const menu = document.querySelector('[data-testid="stMainMenuList"][role="menu"]')
            || document.querySelector('[data-testid="stMainMenuList"]');
        if (!menu || menu.querySelector('[data-testid="' + ITEM_TEST_ID + '"]')) {
            return;
        }

        const insertionAnchor = menu.querySelector('[data-testid="stMainMenuItem-rerun"]')
            || menu.querySelector('[data-testid="stMainMenuItem-clearCache"]')
            || menu.querySelector('[data-testid="stMainMenuItem-print"]')
            || menu.querySelector('button[role="menuitem"]');
        const item = document.createElement("a");
        const url = new URL(parentWindow.location.href);
        url.searchParams.set("_ut_update", String(Date.now()));
        item.setAttribute("href", url.toString());
        item.setAttribute("target", "_self");
        item.setAttribute("type", "button");
        item.setAttribute("role", "menuitem");
        item.setAttribute("tabindex", "-1");
        item.setAttribute("aria-label", LABEL);
        item.setAttribute("data-testid", ITEM_TEST_ID);
        item.classList.add("utaipei-update-menu-item");

        const label = document.createElement("span");
        label.setAttribute("data-testid", "stMainMenuItemLabel");
        label.textContent = LABEL;
        item.appendChild(label);

        item.addEventListener("click", (event) => {
            event.preventDefault();
            event.stopPropagation();
            if (item.getAttribute("aria-disabled") === "true") return;
            void activateUpdate(parentWindow, item);
        });
        item.addEventListener("keydown", (event) => {
            if (event.key === " " || event.key === "Spacebar") {
                event.preventDefault();
                event.stopPropagation();
                item.click();
            }
        });

        if (insertionAnchor) {
            menu.insertBefore(item, insertionAnchor);
        } else {
            menu.appendChild(item);
        }
    }

    markScriptHost();
    try {
        const parentWindow = window.parent;
        if (!parentWindow || parentWindow === window || !parentWindow.document) {
            return;
        }

        installThemeBridge(parentWindow);
        let state = parentWindow[STATE_KEY];
        if (!state) {
            state = {
                install: () => installUpdateItem(parentWindow),
                observer: null,
            };
            parentWindow[STATE_KEY] = state;
            state.observer = new parentWindow.MutationObserver(() => state.install());
            state.observer.observe(parentWindow.document.documentElement, {
                childList: true,
                subtree: true,
            });
        }
        state.install();
        parentWindow.requestAnimationFrame(state.install);
    } catch (_error) {
        // The bridge is optional; keep the app usable if parent DOM access fails.
    }
})();
</script>
"""


def _inject_update_menu_script():
    """Run the parent-document bridge without rendering a visible page control."""

    script = _build_update_menu_script()
    # ``st.html`` sanitizes script-only fragments in some deployed Streamlit
    # builds even when ``unsafe_allow_javascript`` is available.  The legacy
    # component bridge is intentionally used here because it guarantees a
    # same-origin executable document on the pinned 1.57 runtime.
    components.html(script, height=1, width=1)


def collapse_sidebar_if_needed():
    if st.session_state.get("collapse_sidebar_flag"):
        script = """
            <script>
                setTimeout(function() {
                    const parent = window.parent;
                    let closed = false;
                    parent.document.querySelectorAll('button').forEach(b => {
                        const label = b.getAttribute('aria-label');
                        if (label === 'Close sidebar' || label === 'Close') {
                            b.click();
                            closed = true;
                        }
                    });
                    if (!closed) {
                        const btn = parent.document.querySelector('[data-testid="stSidebarCollapseButton"]');
                        if (btn) btn.click();
                    }
                    parent.document.dispatchEvent(new KeyboardEvent('keydown', {
                        key: 'Escape', code: 'Escape', keyCode: 27, which: 27, bubbles: true
                    }));
                }, 300);
            </script>
            """
        if hasattr(st, "iframe"):
            st.iframe(script, height=1, width=1, tab_index=-1)
        else:  # Streamlit 1.57–1.61 compatibility.
            components.html(script, height=0, width=0)
        st.session_state["collapse_sidebar_flag"] = False


def inject_theme_css():
    """Inject one theme-aware stylesheet for both Streamlit and custom markup.

    Streamlit's theme variables are not consistently exposed across releases.
    These tokens therefore have explicit light defaults, a system dark override,
    legacy data-theme fallbacks, and a final parent-document bridge override.
    """

    render_html(
        """
        <style>
            @import url('https://fonts.googleapis.com/css2?family=Noto+Sans+TC:wght@400;500;600;700;800&display=swap');

            /* ----- semantic palette ------------------------------------------------ */
            :root {
                color-scheme: light;
                --ui-canvas: #F8FAFC;
                --ui-canvas-raised: #F1F5F9;
                --ui-surface: #FFFFFF;
                --ui-surface-raised: #FFFFFF;
                --ui-surface-soft: #F8FAFC;
                --ui-surface-strong: #E2E8F0;
                --ui-text: #0F172A;
                --ui-text-muted: #475569;
                --ui-text-faint: #64748B;
                --ui-border: #E2E8F0;
                --ui-border-strong: #CBD5E1;
                --ui-academic-primary: #1E3A5F;
                --ui-accent: #2563EB;
                --ui-accent-strong: #1E3A5F;
                --ui-accent-soft: rgba(37, 99, 235, .12);
                --ui-success: #087f5b;
                --ui-success-soft: rgba(8, 127, 91, .12);
                --ui-warning: #9a5b00;
                --ui-warning-soft: rgba(154, 91, 0, .13);
                --ui-danger: #dc2626;
                --ui-danger-soft: rgba(220, 38, 38, .11);
                --ui-info: #2563EB;
                --ui-info-soft: rgba(37, 99, 235, .12);
                --ui-focus: #2563EB;
                --ui-shadow: 0 16px 38px rgba(33, 61, 85, .11);
                --ui-shadow-soft: 0 8px 22px rgba(33, 61, 85, .07);
                --ui-radius-sm: 8px;
                    --ui-radius-md: 13px;
                    --ui-radius-lg: 20px;
                    --ui-control-height: 44px;
                    --ui-header-height: 3.75rem;

                /* aliases from the project design system */
                --color-primary: #1E3A5F;
                --color-on-primary: #FFFFFF;
                --color-secondary: #2563EB;
                --color-accent: #d97706;
                --color-background: #F8FAFC;
                --color-foreground: #0F172A;
                --color-muted: #F1F5F9;
                --color-border: #E2E8F0;
                --color-destructive: #dc2626;
                --color-ring: #2563EB;
            }

            @media (prefers-color-scheme: dark) {
                :root {
                    color-scheme: dark;
                    --ui-canvas: #0B1120;
                    --ui-canvas-raised: #111827;
                    --ui-surface: #111827;
                    --ui-surface-raised: #172033;
                    --ui-surface-soft: #172033;
                    --ui-surface-strong: #334155;
                    --ui-text: #F8FAFC;
                    --ui-text-muted: #CBD5E1;
                    --ui-text-faint: #CBD5E1;
                    --ui-border: #334155;
                    --ui-border-strong: #64748B;
                    --ui-academic-primary: #60A5FA;
                    --ui-accent: #60A5FA;
                    --ui-accent-strong: #60A5FA;
                    --ui-accent-soft: rgba(96, 165, 250, .16);
                    --ui-success: #65d5ab;
                    --ui-success-soft: rgba(101, 213, 171, .14);
                    --ui-warning: #f5c276;
                    --ui-warning-soft: rgba(245, 194, 118, .16);
                    --ui-danger: #ff9a92;
                    --ui-danger-soft: rgba(255, 154, 146, .15);
                    --ui-info: #60A5FA;
                    --ui-info-soft: rgba(147, 197, 253, .16);
                    --ui-focus: #60A5FA;
                    --ui-shadow: 0 18px 46px rgba(0, 0, 0, .34);
                    --ui-shadow-soft: 0 8px 24px rgba(0, 0, 0, .25);

                    --color-primary: #172033;
                    --color-on-primary: #F8FAFC;
                    --color-secondary: #60A5FA;
                    --color-accent: #fbbf24;
                    --color-background: #0B1120;
                    --color-foreground: #F8FAFC;
                    --color-muted: #172033;
                    --color-border: #334155;
                    --color-destructive: #ef4444;
                    --color-ring: #60A5FA;
                }
            }

            /* Streamlit's user theme may expose a data-theme attribute rather
               than changing the browser's prefers-color-scheme value. */
            html[data-theme="dark"],
            body[data-theme="dark"],
            .stApp[data-theme="dark"],
            [data-testid="stAppViewContainer"][data-theme="dark"],
            [data-streamlit-theme="dark"],
            html:has(body[data-theme="dark"]),
            html:has(.stApp[data-theme="dark"]),
            html:has([data-testid="stAppViewContainer"][data-theme="dark"]),
            html:has([data-streamlit-theme="dark"]) {
                color-scheme: dark;
                --ui-canvas: #0B1120;
                --ui-canvas-raised: #111827;
                --ui-surface: #111827;
                --ui-surface-raised: #172033;
                --ui-surface-soft: #172033;
                --ui-surface-strong: #334155;
                --ui-text: #F8FAFC;
                --ui-text-muted: #CBD5E1;
                --ui-text-faint: #CBD5E1;
                --ui-border: #334155;
                --ui-border-strong: #64748B;
                --ui-academic-primary: #60A5FA;
                --ui-accent: #60A5FA;
                --ui-accent-strong: #60A5FA;
                --ui-accent-soft: rgba(96, 165, 250, .16);
                --ui-success: #65d5ab;
                --ui-success-soft: rgba(101, 213, 171, .14);
                --ui-warning: #f5c276;
                --ui-warning-soft: rgba(245, 194, 118, .16);
                --ui-danger: #ff9a92;
                --ui-danger-soft: rgba(255, 154, 146, .15);
                --ui-info: #60A5FA;
                --ui-info-soft: rgba(147, 197, 253, .16);
                --ui-focus: #60A5FA;
                --ui-shadow: 0 18px 46px rgba(0, 0, 0, .34);
                --ui-shadow-soft: 0 8px 24px rgba(0, 0, 0, .25);

                --color-primary: #172033;
                --color-on-primary: #F8FAFC;
                --color-secondary: #60A5FA;
                --color-accent: #fbbf24;
                --color-background: #0B1120;
                --color-foreground: #F8FAFC;
                --color-muted: #172033;
                --color-border: #334155;
                --color-destructive: #ef4444;
                --color-ring: #60A5FA;
            }

            /* Explicit user preference must win over the OS media query.  These
               selectors intentionally follow the media block above so a light
               choice remains light on an iPhone set to dark (and vice versa). */
            html[data-theme="light"],
            body[data-theme="light"],
            .stApp[data-theme="light"],
            [data-testid="stAppViewContainer"][data-theme="light"],
            [data-streamlit-theme="light"],
            html:has(body[data-theme="light"]),
            html:has(.stApp[data-theme="light"]),
            html:has([data-testid="stAppViewContainer"][data-theme="light"]),
            html:has([data-streamlit-theme="light"]) {
                color-scheme: light;
                --ui-canvas: #F8FAFC;
                --ui-canvas-raised: #F1F5F9;
                --ui-surface: #FFFFFF;
                --ui-surface-raised: #FFFFFF;
                --ui-surface-soft: #F8FAFC;
                --ui-surface-strong: #E2E8F0;
                --ui-text: #0F172A;
                --ui-text-muted: #475569;
                --ui-text-faint: #64748B;
                --ui-border: #E2E8F0;
                --ui-border-strong: #CBD5E1;
                --ui-academic-primary: #1E3A5F;
                --ui-accent: #2563EB;
                --ui-accent-strong: #1E3A5F;
                --ui-accent-soft: rgba(37, 99, 235, .12);
                --ui-info: #2563EB;
                --ui-info-soft: rgba(37, 99, 235, .12);
                --ui-focus: #2563EB;
                --color-primary: #1E3A5F;
                --color-on-primary: #FFFFFF;
                --color-secondary: #2563EB;
                --color-background: #F8FAFC;
                --color-foreground: #0F172A;
                --color-muted: #F1F5F9;
                --color-border: #E2E8F0;
                --color-ring: #2563EB;
            }

            /* The parent-document bridge mirrors .stApp's computed
               color-scheme here.  Keep these rules last so an explicit
               Streamlit choice wins over both the OS media query and any
               legacy theme attributes on app containers. */
            :root[data-utaipei-theme="dark"],
            html[data-utaipei-theme="dark"],
            html:root[data-utaipei-theme="dark"],
            html[data-utaipei-theme="dark"] body,
            html[data-utaipei-theme="dark"] .stApp,
            html[data-utaipei-theme="dark"] [data-testid="stAppViewContainer"],
            html[data-utaipei-theme="dark"] [data-streamlit-theme] {
                color-scheme: dark;
                --ui-canvas: #0B1120;
                --ui-canvas-raised: #111827;
                --ui-surface: #111827;
                --ui-surface-raised: #172033;
                --ui-surface-soft: #172033;
                --ui-surface-strong: #334155;
                --ui-text: #F8FAFC;
                --ui-text-muted: #CBD5E1;
                --ui-text-faint: #CBD5E1;
                --ui-border: #334155;
                --ui-border-strong: #64748B;
                --ui-academic-primary: #60A5FA;
                --ui-accent: #60A5FA;
                --ui-accent-strong: #60A5FA;
                --ui-accent-soft: rgba(96, 165, 250, .16);
                --ui-success: #65d5ab;
                --ui-success-soft: rgba(101, 213, 171, .14);
                --ui-warning: #f5c276;
                --ui-warning-soft: rgba(245, 194, 118, .16);
                --ui-danger: #ff9a92;
                --ui-danger-soft: rgba(255, 154, 146, .15);
                --ui-info: #60A5FA;
                --ui-info-soft: rgba(147, 197, 253, .16);
                --ui-focus: #60A5FA;
                --ui-shadow: 0 18px 46px rgba(0, 0, 0, .34);
                --ui-shadow-soft: 0 8px 24px rgba(0, 0, 0, .25);

                --color-primary: #172033;
                --color-on-primary: #F8FAFC;
                --color-secondary: #60A5FA;
                --color-accent: #fbbf24;
                --color-background: #0B1120;
                --color-foreground: #F8FAFC;
                --color-muted: #172033;
                --color-border: #334155;
                --color-destructive: #ef4444;
                --color-ring: #60A5FA;
            }

            :root[data-utaipei-theme="light"],
            html[data-utaipei-theme="light"],
            html:root[data-utaipei-theme="light"],
            html[data-utaipei-theme="light"] body,
            html[data-utaipei-theme="light"] .stApp,
            html[data-utaipei-theme="light"] [data-testid="stAppViewContainer"],
            html[data-utaipei-theme="light"] [data-streamlit-theme] {
                color-scheme: light;
                --ui-canvas: #F8FAFC;
                --ui-canvas-raised: #F1F5F9;
                --ui-surface: #FFFFFF;
                --ui-surface-raised: #FFFFFF;
                --ui-surface-soft: #F8FAFC;
                --ui-surface-strong: #E2E8F0;
                --ui-text: #0F172A;
                --ui-text-muted: #475569;
                --ui-text-faint: #64748B;
                --ui-border: #E2E8F0;
                --ui-border-strong: #CBD5E1;
                --ui-academic-primary: #1E3A5F;
                --ui-accent: #2563EB;
                --ui-accent-strong: #1E3A5F;
                --ui-accent-soft: rgba(37, 99, 235, .12);
                --ui-success: #087f5b;
                --ui-success-soft: rgba(8, 127, 91, .12);
                --ui-warning: #9a5b00;
                --ui-warning-soft: rgba(154, 91, 0, .13);
                --ui-danger: #dc2626;
                --ui-danger-soft: rgba(220, 38, 38, .11);
                --ui-info: #2563EB;
                --ui-info-soft: rgba(37, 99, 235, .12);
                --ui-focus: #2563EB;
                --ui-shadow: 0 16px 38px rgba(33, 61, 85, .11);
                --ui-shadow-soft: 0 8px 22px rgba(33, 61, 85, .07);

                --color-primary: #1E3A5F;
                --color-on-primary: #FFFFFF;
                --color-secondary: #2563EB;
                --color-accent: #d97706;
                --color-background: #F8FAFC;
                --color-foreground: #0F172A;
                --color-muted: #F1F5F9;
                --color-border: #E2E8F0;
                --color-destructive: #dc2626;
                --color-ring: #2563EB;
            }

            /* ----- reset and page frame ------------------------------------------ */
            *, *::before, *::after { box-sizing: border-box; }
            html { background: var(--ui-canvas); scroll-behavior: smooth; }
            body {
                margin: 0;
                min-width: 0;
                background: var(--ui-canvas) !important;
                color: var(--ui-text) !important;
                font-family: "Noto Sans TC", "Microsoft JhengHei", system-ui, -apple-system, sans-serif;
                text-rendering: optimizeLegibility;
            }
            .stApp,
            [data-testid="stAppViewContainer"],
            [data-testid="stMain"] {
                background: var(--ui-canvas) !important;
                color: var(--ui-text) !important;
            }
            [data-testid="stAppViewContainer"] {
                min-width: 0;
                overflow-x: clip;
                --ui-safe-top: env(safe-area-inset-top, 0px);
                --ui-safe-right: env(safe-area-inset-right, 0px);
                --ui-safe-bottom: env(safe-area-inset-bottom, 0px);
                --ui-safe-left: env(safe-area-inset-left, 0px);
                padding: var(--ui-safe-top) var(--ui-safe-right)
                    var(--ui-safe-bottom) var(--ui-safe-left);
            }
            [data-testid="stMainBlockContainer"] {
                width: min(100%, 1400px) !important;
                max-width: 1400px !important;
                min-width: 0;
                margin-inline: auto;
                padding: calc(var(--ui-header-height) + 1rem) clamp(1rem, 3vw, 2.75rem)
                    clamp(1.25rem, 3vw, 2.5rem) !important;
            }
            [data-testid="stMainBlockContainer"] > div { min-width: 0; }
            .stMarkdown, .stMarkdown p, .stMarkdown li,
            [data-testid="stMarkdownContainer"] { color: var(--ui-text) !important; }
            .stMarkdown p, .stMarkdown li { line-height: 1.7; }
            label, legend,
            [data-testid="stWidgetLabel"],
            [data-testid="stWidgetLabel"] p,
            [data-testid="stWidgetLabel"] label,
            [data-baseweb="select"] *,
            [data-testid="stFileUploader"] * {
                color: var(--ui-text) !important;
            }
            [data-testid="stFileUploader"] small,
            [data-testid="stWidgetLabel"] small { color: var(--ui-text-muted) !important; }
            h1, h2, h3, h4, h5, h6 {
                color: var(--ui-text) !important;
                font-family: "Noto Sans TC", "Microsoft JhengHei", system-ui, -apple-system, sans-serif;
                text-wrap: balance;
                scroll-margin-top: 1.5rem;
                letter-spacing: -.015em;
            }
            h1 { font-size: clamp(1.65rem, 3vw, 2.35rem); line-height: 1.2; }
            h2 { font-size: clamp(1.35rem, 2vw, 1.75rem); line-height: 1.25; }
            h3 { font-size: clamp(1.15rem, 1.7vw, 1.4rem); line-height: 1.35; }
            h4 { font-size: 1.05rem; line-height: 1.4; }
            a { color: var(--ui-accent); text-underline-offset: 3px; }
            a:hover { color: var(--ui-accent-strong); }
            /* Streamlit's 16px heading deep-link glyph is not part of the app's
               task flow and cannot meet the 44px touch-target contract. */
            a[aria-label="Link to heading"] { display: none !important; }
            code, pre, .course-row, .dataframe, [data-testid="stDataFrame"] {
                font-variant-numeric: tabular-nums;
            }
            .skip-link {
                position: fixed;
                z-index: 20;
                top: .5rem;
                left: .75rem;
                transform: translateY(-150%);
                padding: .7rem 1rem;
                border-radius: var(--ui-radius-sm);
                background: var(--ui-accent-strong);
                color: #fff !important;
                font-weight: 700;
                text-decoration: none;
                transition: transform .2s ease;
            }
            .skip-link:focus-visible { transform: translateY(0); }

            /* ----- shared surfaces ------------------------------------------------ */
            .header-card {
                margin: 0 0 1.75rem;
                padding: clamp(1.35rem, 3vw, 2.4rem);
                border: 1px solid var(--ui-border);
                border-radius: var(--ui-radius-lg);
                background: var(--ui-surface-raised);
                box-shadow: var(--ui-shadow-soft);
                text-align: left;
            }
            .header-title {
                position: relative;
                z-index: 1;
                max-width: 28ch;
                color: var(--ui-text) !important;
                font-size: clamp(1.55rem, 3vw, 2.5rem);
                font-weight: 800;
                letter-spacing: -.045em;
                line-height: 1.18;
                text-wrap: balance;
            }
            .header-subtitle {
                position: relative;
                z-index: 1;
                max-width: 70ch;
                margin-top: .55rem;
                color: var(--ui-text-muted) !important;
                font-size: 1rem;
                line-height: 1.65;
            }
            .hero-callout,
            .info-card,
            .card-panel,
            .metric-card,
            .overview-grid > div,
            .metric-grid > div {
                color: var(--ui-text);
                background: var(--ui-surface) !important;
                border: 1px solid var(--ui-border) !important;
                box-shadow: none;
            }
            .hero-callout {
                margin: 0 0 1.5rem;
                padding: 1rem 1.15rem;
                border-left: 4px solid var(--ui-accent) !important;
                border-radius: var(--ui-radius-md);
                background: var(--ui-accent-soft) !important;
                line-height: 1.7;
            }
            .hero-callout b, .hero-callout strong { color: var(--ui-text) !important; }
            .info-flex {
                display: grid;
                grid-template-columns: minmax(0, 1fr) minmax(0, 1.15fr);
                gap: 1rem;
                margin-bottom: 1.6rem;
            }
            .info-card {
                min-width: 0;
                padding: 1.1rem 1.25rem;
                border-radius: var(--ui-radius-md);
            }
            .info-card-highlight {
                background: var(--ui-accent-soft) !important;
                border-color: color-mix(in srgb, var(--ui-accent) 42%, var(--ui-border)) !important;
            }
            .info-card .eyebrow,
            .info-card .meta-label { color: var(--ui-text-muted) !important; }
            .info-card .meta-value { color: var(--ui-text) !important; }
            .info-value { margin-top: .65rem; font-size: .94rem; line-height: 1.75; }
            .info-value strong { color: var(--ui-text) !important; font-weight: 750; }
            .info-source { margin-top: .55rem; font-size: 1rem; font-weight: 750; }
            .info-note { display: block; margin-top: .65rem; font-size: .82rem; line-height: 1.6; }
            .source-badge {
                display: inline-flex;
                align-items: center;
                min-height: 2rem;
                padding: .25rem .65rem;
                border: 1px solid color-mix(in srgb, var(--ui-accent) 48%, var(--ui-border));
                border-radius: var(--ui-radius-sm);
                background: var(--ui-accent-soft);
                color: var(--ui-accent-strong) !important;
                font-size: .82rem !important;
                font-weight: 700;
            }
            .card-panel {
                margin-block: 1rem;
                padding: clamp(1rem, 2vw, 1.5rem);
                border-radius: var(--ui-radius-lg);
            }
            .section-heading { margin: 0 0 .8rem; color: var(--ui-text) !important; }
            .section-gap { height: .55rem; }
            .section-gap-compact { height: .2rem; }
            .category-card {
                margin-bottom: .75rem;
                padding: .9rem 1rem;
                border: 1px solid var(--ui-border);
                border-radius: var(--ui-radius-md);
                background: var(--ui-surface);
            }
            .category-heading { display: flex; align-items: center; justify-content: space-between; gap: .75rem; }
            .category-name { min-width: 0; color: var(--ui-text) !important; font-weight: 700; overflow-wrap: anywhere; }
            .category-meta { margin-top: .55rem; color: var(--ui-text-muted); font-size: .82rem; font-variant-numeric: tabular-nums; }
            .parsed-summary {
                display: grid;
                grid-template-columns: repeat(4, minmax(0, 1fr));
                gap: .7rem;
                margin: 0 0 1rem;
            }
            .parsed-summary-item {
                display: flex;
                min-width: 0;
                flex-direction: column;
                gap: .25rem;
                padding: .75rem .9rem;
                border-left: 3px solid var(--ui-accent);
                border-radius: var(--ui-radius-sm);
                background: var(--ui-surface-soft);
                color: var(--ui-text-muted);
                font-size: .8rem;
            }
            .parsed-summary-item b { color: var(--ui-text); font-size: 1.1rem; font-variant-numeric: tabular-nums; }

            /* ----- outcomes and progress ----------------------------------------- */
            .outcome-banner {
                display: flex;
                align-items: center;
                gap: .75rem;
                margin: .25rem 0 1rem;
                padding: .9rem 1.1rem;
                border: 1px solid var(--ui-border);
                border-left: 5px solid var(--ui-info);
                border-radius: var(--ui-radius-md);
                background: var(--ui-surface-raised);
                color: var(--ui-text);
                font-size: 1.2rem;
                font-weight: 800;
            }
            .outcome-satisfied { border-left-color: var(--ui-success); background: var(--ui-success-soft); }
            .outcome-not-satisfied { border-left-color: var(--ui-danger); background: var(--ui-danger-soft); }
            .outcome-unknown { border-left-color: var(--ui-warning); background: var(--ui-warning-soft); }
            .metric-grid {
                display: grid;
                grid-template-columns: repeat(3, minmax(0, 1fr));
                gap: .85rem;
                align-items: stretch;
            }
            .metric-card,
            .metric-grid > div {
                display: flex;
                min-width: 0;
                min-height: 8rem;
                flex-direction: column;
                justify-content: space-between;
                padding: 1rem 1.1rem;
                border-radius: var(--ui-radius-md);
                transition: transform .2s ease, border-color .2s ease, box-shadow .2s ease;
            }
            .metric-card--muted { opacity: .82; }
            .metric-card:hover,
            .metric-grid > div:hover,
            .overview-grid > div:hover {
                transform: translateY(-2px);
                border-color: var(--ui-border-strong) !important;
                box-shadow: var(--ui-shadow-soft);
            }
            .metric-label { color: var(--ui-text-muted) !important; font-size: .86rem; font-weight: 650; }
            .metric-value { color: var(--ui-text) !important; font-size: clamp(1.55rem, 3vw, 2rem); font-weight: 800; letter-spacing: -.035em; }
            .metric-meta { color: var(--ui-text-faint) !important; font-size: .79rem; line-height: 1.45; }
            .progress-container { margin: 1rem 0 1.25rem; }
            .progress-label-row {
                display: flex;
                justify-content: space-between;
                gap: 1rem;
                margin-bottom: .45rem;
                color: var(--ui-text-muted) !important;
                font-size: .88rem;
                line-height: 1.45;
            }
            .progress-label-row > * { min-width: 0; }
            .progress-label-row .progress-title { color: var(--ui-text) !important; font-weight: 700; }
            .progress-label-row .progress-number { color: var(--ui-text-muted) !important; text-align: right; }
            .progress-label-row b { color: var(--ui-text) !important; font-variant-numeric: tabular-nums; }
            .progress-number .credit-completed { color: var(--ui-success) !important; }
            .progress-number .credit-ip { color: var(--ui-info) !important; }
            .progress-bar-bg {
                display: flex;
                width: 100%;
                height: .7rem;
                overflow: hidden;
                border: 1px solid var(--ui-border);
                border-radius: 999px;
                background: var(--ui-surface-strong);
            }
            .progress-bar-fill { height: 100%; transition: width .45s ease; }
            .progress-bar-fill.completed { background: var(--ui-success); }
            .progress-bar-fill.in-progress { background: var(--ui-info); }

            /* ----- statuses -------------------------------------------------------- */
            .status-badge {
                display: inline-flex;
                align-items: center;
                justify-content: center;
                min-height: 1.9rem;
                padding: .2rem .6rem;
                border: 1px solid var(--ui-border);
                border-radius: var(--ui-radius-sm);
                color: var(--ui-text) !important;
                font-size: .76rem;
                font-weight: 750;
                line-height: 1.2;
                overflow-wrap: anywhere;
            }
            .status-completed { border-color: color-mix(in srgb, var(--ui-success) 58%, var(--ui-border)); background: var(--ui-success-soft); color: var(--ui-success) !important; }
            .status-ip { border-color: color-mix(in srgb, var(--ui-info) 58%, var(--ui-border)); background: var(--ui-info-soft); color: var(--ui-info) !important; }
            .status-missing { border-color: color-mix(in srgb, var(--ui-danger) 58%, var(--ui-border)); background: var(--ui-danger-soft); color: var(--ui-danger) !important; }
            .status-unknown { border-color: color-mix(in srgb, var(--ui-warning) 58%, var(--ui-border)); background: var(--ui-warning-soft); color: var(--ui-warning) !important; }

            /* ----- tables and course lists ---------------------------------------- */
            .table-container,
            .report-table-wrap,
            .course-list {
                width: 100%;
                max-width: 100%;
                min-width: 0;
                overflow-x: clip;
                border: 1px solid var(--ui-border);
                border-radius: var(--ui-radius-md);
                background: var(--ui-surface);
            }
            .table-container table,
            .report-table-wrap table {
                width: 100%;
                min-width: 0;
                max-width: 100%;
                table-layout: fixed;
                border-collapse: separate;
                border-spacing: 0;
                color: var(--ui-text);
                font-size: .9rem;
                line-height: 1.5;
            }
            .table-container th, .table-container td,
            .report-table-wrap th, .report-table-wrap td {
                padding: .7rem .8rem;
                border-bottom: 1px solid var(--ui-border);
                color: var(--ui-text) !important;
                text-align: left;
                vertical-align: middle;
                white-space: normal;
                overflow-wrap: anywhere;
            }
            .table-container th, .report-table-wrap th {
                position: sticky;
                z-index: 1;
                top: 0;
                background: var(--ui-surface-strong) !important;
                color: var(--ui-text) !important;
                font-size: .78rem;
                font-weight: 800;
                letter-spacing: .02em;
            }
            .table-container tbody tr:nth-child(even),
            .report-table-wrap tbody tr:nth-child(even) { background: var(--ui-surface-soft); }
            .table-container tbody tr:hover,
            .report-table-wrap tbody tr:hover { background: var(--ui-accent-soft); }
            .table-container tr:last-child td,
            .report-table-wrap tr:last-child td { border-bottom: 0; }
            .table-container td:nth-last-child(-n+3),
            .report-table-wrap td:nth-last-child(-n+3) {
                font-variant-numeric: tabular-nums;
            }
            .course-list { display: grid; gap: 0; overflow-x: clip; }
            .course-header, .course-row {
                display: grid;
                grid-template-columns: minmax(0, 3fr) minmax(0, 1fr) minmax(0, .7fr) minmax(0, .8fr) minmax(0, 1fr);
                gap: .8rem;
                min-width: 0;
                max-width: 100%;
                align-items: center;
                padding: .72rem .9rem;
            }
            .course-header {
                position: sticky;
                z-index: 1;
                top: 0;
                border-bottom: 1px solid var(--ui-border);
                background: var(--ui-surface-strong);
                color: var(--ui-text-muted);
                font-size: .78rem;
                font-weight: 800;
                letter-spacing: .02em;
            }
            .course-row {
                border-bottom: 1px solid var(--ui-border);
                background: var(--ui-surface);
                color: var(--ui-text);
                font-size: .9rem;
            }
            .course-row:nth-child(odd) { background: var(--ui-surface-soft); }
            .course-row:hover { background: var(--ui-accent-soft); }
            .course-row:last-child { border-bottom: 0; }
            .course-row > div, .course-header > div { min-width: 0; overflow-wrap: anywhere; }
            .course-row > div:not(.course-name-col):not(.course-status-col) { color: var(--ui-text-muted) !important; font-variant-numeric: tabular-nums; }
            .course-name-col { color: var(--ui-text) !important; font-weight: 700; }
            .course-allocation-note {
                margin-top: .25rem;
                color: var(--ui-text-muted) !important;
                font-size: .76rem;
                font-weight: 500;
                line-height: 1.45;
                overflow-wrap: anywhere;
            }
            .course-status-col { justify-self: start; }
            .report-table-wrap + .stDownloadButton,
            .course-list + .stDownloadButton { margin-top: .75rem; }

            /* Streamlit's dataframe uses a virtualized grid in recent versions;
               these selectors style both the wrapper and the accessible grid. */
            [data-testid="stDataFrame"], .stDataFrame {
                width: 100%;
                max-width: 100%;
                overflow: hidden;
                border: 1px solid var(--ui-border);
                border-radius: var(--ui-radius-md);
                background: var(--ui-surface) !important;
                color: var(--ui-text) !important;
            }
            [data-testid="stDataFrame"] [role="columnheader"],
            [data-testid="stDataFrame"] [role="gridcell"] { font-variant-numeric: tabular-nums; }
            [data-testid="stDataFrame"] [role="columnheader"] {
                background: var(--ui-surface-strong) !important;
                color: var(--ui-text) !important;
                font-weight: 800;
            }
            [data-testid="stDataFrame"] [role="gridcell"] { color: var(--ui-text) !important; }
            [data-testid="stDataFrame"] [role="row"]:nth-child(even) { background: var(--ui-surface-soft) !important; }
            [data-testid="stDataFrame"] [role="row"]:hover { background: var(--ui-accent-soft) !important; }

            /* ----- controls, alerts, sidebar, popovers ---------------------------- */
            button, input, textarea, select, [role="button"], [data-baseweb="select"] > div {
                min-height: var(--ui-control-height) !important;
                min-width: var(--ui-control-height) !important;
                touch-action: manipulation;
            }
            button[data-testid="stBaseButton-headerNoPadding"],
            [data-testid="stExpandSidebarButton"],
            [data-testid="stMainMenuButton"],
            [data-testid="stSidebarCollapseButton"] {
                min-width: var(--ui-control-height) !important;
            }
            input, textarea, select,
            [data-baseweb="select"] > div,
            [data-testid="stFileUploaderDropzone"] {
                border-color: var(--ui-border) !important;
                background: var(--ui-surface) !important;
                color: var(--ui-text) !important;
            }
            input::placeholder, textarea::placeholder { color: var(--ui-text-faint) !important; opacity: 1; }
            button, .stButton > button, .stDownloadButton > button {
                border: 1px solid var(--ui-border-strong) !important;
                border-radius: var(--ui-radius-sm) !important;
                background: var(--ui-surface-raised) !important;
                color: var(--ui-text) !important;
                font-weight: 700;
                transition: transform .18s ease, background-color .18s ease, border-color .18s ease, box-shadow .18s ease;
            }
            button:hover, .stButton > button:hover, .stDownloadButton > button:hover {
                border-color: var(--ui-accent) !important;
                background: var(--ui-accent-soft) !important;
                color: var(--ui-text) !important;
                box-shadow: var(--ui-shadow-soft);
            }
            button:active, .stButton > button:active, .stDownloadButton > button:active { transform: translateY(1px); }
            button[kind="primary"], .stButton > button[kind="primary"] {
                border-color: var(--ui-accent-strong) !important;
                background: var(--ui-accent-strong) !important;
                color: #fff !important;
            }
            button[kind="primary"]:hover, .stButton > button[kind="primary"]:hover { background: var(--ui-accent) !important; }
            :where(button, a, input, textarea, select, [role="button"], [tabindex]):focus-visible {
                outline: 3px solid var(--ui-focus) !important;
                outline-offset: 2px !important;
                box-shadow: 0 0 0 2px var(--ui-canvas) !important;
            }
            /* Streamlit versions render selectboxes as either React Aria or
               BaseWeb comboboxes. On iOS, BaseWeb collapses the focused input
               to caret width; drawing the global focus outline there creates
               two vertical stripes. Keep the caret clean and draw one complete,
               accessible focus ring around either outer select control. */
            [data-testid="stSelectbox"] [role="group"] {
                min-height: var(--ui-control-height) !important;
                min-width: var(--ui-control-height) !important;
                border: 1px solid var(--ui-border) !important;
                border-radius: var(--ui-radius-sm) !important;
                border-color: var(--ui-border) !important;
                background: var(--ui-surface) !important;
                transition: border-color .18s ease, box-shadow .18s ease;
            }
            [data-testid="stSelectbox"] [data-baseweb="select"] {
                min-height: var(--ui-control-height) !important;
                min-width: var(--ui-control-height) !important;
                border: 1px solid var(--ui-border) !important;
                border-radius: var(--ui-radius-sm) !important;
                background: var(--ui-surface) !important;
                transition: border-color .18s ease, box-shadow .18s ease;
            }
            [data-testid="stSelectbox"] input[role="combobox"] {
                background: transparent !important;
                min-width: 0 !important;
                border: 0 !important;
                outline: none !important;
                box-shadow: none !important;
                caret-color: transparent;
                appearance: none !important;
                -webkit-appearance: none !important;
            }
            [data-testid="stSelectbox"] input[role="combobox"]:focus-visible {
                outline: none !important;
                box-shadow: none !important;
            }
            [data-testid="stSelectbox"] [data-baseweb="select"] > div {
                min-width: 0 !important;
                border: 0 !important;
                outline: none !important;
                box-shadow: none !important;
            }
            [data-testid="stSelectbox"] [role="group"]:focus-within,
            [data-testid="stSelectbox"] [data-baseweb="select"]:focus-within {
                border-color: var(--ui-focus) !important;
                box-shadow: 0 0 0 3px var(--ui-focus) !important;
            }
            /* When BaseWeb is nested in Streamlit's accessible group, the
               group is the sole visible focus owner; the nested shell remains
               a borderless input surface. */
            [data-testid="stSelectbox"] [role="group"] [data-baseweb="select"]:focus-within {
                border-color: transparent !important;
                box-shadow: none !important;
            }
            [data-testid="stAlert"] {
                border: 1px solid var(--ui-border) !important;
                border-radius: var(--ui-radius-md) !important;
                background: var(--ui-surface-raised) !important;
                color: var(--ui-text) !important;
            }
            [data-testid="stAlert"] * { color: inherit; }
            [data-testid="stSidebar"] {
                color-scheme: inherit;
                border-right: 1px solid var(--ui-border) !important;
                background: var(--ui-canvas-raised) !important;
                color: var(--ui-text) !important;
            }
            [data-testid="stSidebar"] * { color: inherit; }
            [data-testid="stSidebar"] input,
            [data-testid="stSidebar"] textarea,
            [data-testid="stSidebar"] [data-baseweb="select"] > div,
            [data-testid="stSidebar"] [data-testid="stFileUploaderDropzone"] {
                background: var(--ui-surface) !important;
                color: var(--ui-text) !important;
            }
            [data-baseweb="popover"], [role="listbox"], [role="option"] {
                border-color: var(--ui-border) !important;
                background: var(--ui-surface-raised) !important;
                color: var(--ui-text) !important;
            }
            [role="option"]:hover, [role="option"][aria-selected="true"] {
                background: var(--ui-accent-soft) !important;
                color: var(--ui-text) !important;
            }
            [data-testid="stExpander"] {
                border-color: var(--ui-border) !important;
                background: var(--ui-surface) !important;
            }
            [data-testid="stExpander"] summary { min-height: var(--ui-control-height) !important; }
            [data-testid="stExpander"] summary:hover { background: var(--ui-accent-soft); }
            .export-group { margin-top: 1rem; padding-top: .9rem; border-top: 1px solid var(--ui-border); }
            .export-label { margin: 0 0 .55rem; color: var(--ui-text-muted); font-size: .82rem; font-weight: 750; }
            .sidebar-rules-card {
                margin: .2rem 0 .8rem;
                padding: .75rem .9rem;
                border: 1px solid color-mix(in srgb, var(--ui-accent) 40%, var(--ui-border));
                border-radius: var(--ui-radius-md);
                background: var(--ui-accent-soft);
            }
            .sidebar-eyebrow { color: var(--ui-text-muted); font-size: .72rem; font-weight: 750; }
            .sidebar-rules-version { margin-top: .15rem; color: var(--ui-accent-strong); font-size: .95rem; font-weight: 800; }
            .sidebar-meta { color: var(--ui-text-muted); font-size: .72rem; line-height: 1.55; overflow-wrap: anywhere; }
            .admin-help { color: var(--ui-text-muted) !important; font-size: .84rem !important; line-height: 1.6; }

            /* The updater lives in an HTML element only as a DOM bridge.  It
               must never reserve a row in the visible report layout. */
            [data-testid="stElementContainer"][data-utaipei-menu-script-host="true"] {
                display: none !important;
            }
            [data-testid="stMainMenuList"] .utaipei-update-menu-item {
                display: flex !important;
                align-items: center;
                min-width: 100% !important;
                min-height: var(--ui-control-height) !important;
                justify-content: flex-start;
                padding: .5rem .55rem !important;
                border: 0 !important;
                border-radius: var(--ui-radius-sm) !important;
                background: transparent !important;
                color: var(--ui-text) !important;
                font: inherit;
                text-align: left;
                text-decoration: none !important;
                cursor: pointer;
                touch-action: manipulation;
            }
            [data-testid="stMainMenuList"] .utaipei-update-menu-item:hover {
                border-color: transparent !important;
                background: var(--ui-accent-soft) !important;
                color: var(--ui-text) !important;
                box-shadow: none;
            }
            [data-testid="stMainMenuList"] .utaipei-update-menu-item:focus-visible {
                outline: 3px solid var(--ui-focus) !important;
                outline-offset: -2px !important;
                box-shadow: none !important;
            }

            /* ----- responsive layout ---------------------------------------------- */
            @media (max-width: 1100px) {
                .metric-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); }
                .info-flex { grid-template-columns: minmax(0, 1fr); }
            }
            @media (max-width: 768px) {
                /* Keep the safe-area inset and Streamlit's fixed header offset
                   separate so neither the notch nor the toolbar is counted
                   twice. Streamlit's main section remains the only scroller. */
                [data-testid="stAppViewContainer"] {
                    padding: var(--ui-safe-top) 0 0 0 !important;
                }
                [data-testid="stMainBlockContainer"] {
                    padding: calc(var(--ui-header-height) + .85rem)
                        max(.85rem, var(--ui-safe-right))
                        max(1.25rem, var(--ui-safe-bottom))
                        max(.85rem, var(--ui-safe-left)) !important;
                }
                [data-testid="stSidebar"][aria-expanded="true"] { width: min(88vw, 23rem) !important; max-width: 88vw !important; }
                [data-testid="stHorizontalBlock"] { flex-wrap: wrap; gap: .75rem; }
                [data-testid="column"] { min-width: min(100%, 14rem); flex: 1 1 14rem !important; }
                .metric-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); gap: .7rem; }
                .parsed-summary { grid-template-columns: repeat(2, minmax(0, 1fr)); }
                .metric-card, .metric-grid > div { min-height: 7rem; padding: .85rem; }
                .progress-label-row { flex-direction: column; align-items: flex-start; gap: .2rem; }
                .progress-label-row .progress-number { text-align: left; }
                .stButton > button, .stDownloadButton > button { width: 100%; }
                .header-card { margin-bottom: 1rem; padding: 1.05rem; border-radius: var(--ui-radius-md); }
                .header-title { font-size: clamp(1.45rem, 7vw, 2rem); }
                .header-subtitle { font-size: .9rem; }
                .card-panel { margin-block: .7rem; border-radius: var(--ui-radius-md); }
                .hero-callout { margin-bottom: .9rem; padding: .8rem .9rem; line-height: 1.55; }
                [data-testid="stExpander"] summary { min-height: var(--ui-control-height); }
                .table-container table, .report-table-wrap table {
                    min-width: 0;
                    width: 100%;
                    table-layout: fixed;
                }
                .course-header { display: none; }
                .course-row {
                    grid-template-columns: 1fr;
                    min-width: 0;
                    gap: .45rem;
                    padding: .85rem;
                }
                .course-row > div {
                    display: flex;
                    justify-content: space-between;
                    gap: .75rem;
                    text-align: right;
                }
                .course-row > div::before {
                    flex: 0 0 auto;
                    content: attr(data-label);
                    color: var(--ui-text-muted);
                    font-weight: 750;
                    text-align: left;
                }
                .course-name-col {
                    display: block !important;
                    text-align: left !important;
                    font-size: 1rem;
                }
                .course-name-col::before, .course-status-col::before { display: none; }
                .course-status-col { justify-content: flex-start !important; text-align: left !important; }
            }
            @media (max-width: 480px) {
                [data-testid="stMainBlockContainer"] {
                    padding-inline: max(.65rem, var(--ui-safe-left))
                        max(.65rem, var(--ui-safe-right)) !important;
                }
                [data-testid="column"] { min-width: 100%; flex-basis: 100% !important; }
                .metric-grid { grid-template-columns: minmax(0, 1fr); }
                .parsed-summary { grid-template-columns: minmax(0, 1fr); }
                .info-card, .card-panel, .hero-callout { padding: .85rem; }
                .table-container, .report-table-wrap, .course-list { border-radius: var(--ui-radius-sm); }
            }
            @media (hover: none) {
                .metric-card:hover, .metric-grid > div:hover, .overview-grid > div:hover { transform: none; box-shadow: none; }
            }
            @media (prefers-reduced-motion: reduce) {
                html { scroll-behavior: auto !important; }
                *, *::before, *::after {
                    animation-duration: .01ms !important;
                    animation-iteration-count: 1 !important;
                    transition-duration: .01ms !important;
                }
            }
            @media (forced-colors: active) {
                *, *::before, *::after { forced-color-adjust: auto; }
                :where(button, a, input, textarea, select, [role="button"]):focus-visible { outline: 3px solid Highlight !important; }
                [data-testid="stSelectbox"] [role="group"]:focus-within,
                [data-testid="stSelectbox"] [data-baseweb="select"]:focus-within > div {
                    outline: 3px solid Highlight !important;
                    outline-offset: 2px !important;
                }
            }
            *::-webkit-scrollbar { width: 10px; height: 10px; }
            *::-webkit-scrollbar-track { background: var(--ui-canvas-raised); }
            *::-webkit-scrollbar-thumb { border: 2px solid var(--ui-canvas-raised); border-radius: 999px; background: var(--ui-border-strong); }
            *::-webkit-scrollbar-thumb:hover { background: var(--ui-accent); }
            * { scrollbar-color: var(--ui-border-strong) var(--ui-canvas-raised); scrollbar-width: thin; }
        </style>
        <span data-utaipei-theme-style-marker hidden aria-hidden="true"></span>
        """,
    )


def draw_premium_progress(label, completed, required, ip=0.0):
    completed = float(completed or 0.0)
    ip = float(ip or 0.0)
    required = float(required or 0.0)
    comp_pct = min(100.0, (completed / required) * 100.0) if required > 0 else 100.0
    ip_pct = min(100.0 - comp_pct, (ip / required) * 100.0) if required > 0 else 0.0
    completed_text = format_credit(completed)
    ip_text = format_credit(ip)
    required_text = format_credit(required)
    ip_markup = f'／修讀中 <b class="credit-ip">{ip_text}</b>' if ip > 0 else ""

    render_html(
        f"""
        <div class="progress-container" role="group" aria-label="{escape(str(label))}進度">
            <div class="progress-label-row">
                <span class="progress-title">{escape(str(label))}</span>
                <span class="progress-number">已得 <b class="credit-completed">{completed_text}</b> 學分{ip_markup} ／應修 <b>{required_text}</b> 學分</span>
            </div>
            <div class="progress-bar-bg" role="progressbar" aria-label="{escape(str(label))}" aria-valuemin="0" aria-valuemax="{required_text}" aria-valuenow="{completed_text}">
                <div class="progress-bar-fill completed" style="width: {comp_pct}%;"></div>
                <div class="progress-bar-fill in-progress" style="width: {ip_pct}%;"></div>
            </div>
        </div>
        """,
    )


def render_header_card(title, subtitle, landmark_id=None):
    landmark_attr = f' id="{escape(str(landmark_id))}"' if landmark_id else ""
    render_html(
        f"""
        <header class="header-card"{landmark_attr} tabindex="-1">
            <div class="header-title">{escape(str(title))}</div>
            <div class="header-subtitle">{escape(str(subtitle))}</div>
        </header>
        """,
    )


def render_landing_message():
    render_html(
        """
        <section class="hero-callout" aria-label="開始方式">
            <b>開始畢業盤點</b><br>
            先選入學年度與主修，再上傳成績單或登入校務系統。資料只在本次工作階段分析。<br>
            <small>結果供自我檢查；正式畢業資格仍以校方審核為準。</small>
        </section>
        """,
    )
