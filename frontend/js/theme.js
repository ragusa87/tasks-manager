// Theme toggle + theme-aware color resolution.
//
// The effective theme is CSS-only (color-scheme + light-dark() tokens); the
// server renders <html data-theme=...> from the "theme" cookie. This module
// only cycles the override: it flips the attribute optimistically for an
// instant repaint, persists the choice through POST /theme/, and tells
// canvas/chart code to re-read its colors via a "themechange" event.
import { nextTheme, themeLabel } from './theme-utils.js';
import { getCsrfToken } from './csrf.js';

export function currentTheme() {
    return document.documentElement.dataset.theme || 'system';
}

function applyTheme(theme) {
    if (theme === 'system') {
        delete document.documentElement.dataset.theme;
    } else {
        document.documentElement.dataset.theme = theme;
    }
    document.querySelectorAll('[data-theme-toggle]').forEach(function(btn) {
        btn.setAttribute('aria-label', themeLabel(theme));
        btn.querySelectorAll('[data-theme-icon]').forEach(function(icon) {
            icon.classList.toggle('hidden', icon.dataset.themeIcon !== theme);
        });
    });
    document.dispatchEvent(new CustomEvent('themechange', { detail: { theme: theme } }));
}

function persistTheme(theme, endpoint) {
    var body = new FormData();
    body.append('theme', theme);
    var csrf = getCsrfToken();
    if (csrf) body.append('csrfmiddlewaretoken', csrf);
    fetch(endpoint, { method: 'POST', body: body }).catch(function() {
        // The optimistic flip already happened; losing persistence only
        // means the next page load falls back to the previous choice.
    });
}

export function initThemeToggle() {
    document.querySelectorAll('[data-theme-toggle]:not([data-theme-init])').forEach(function(btn) {
        btn.setAttribute('data-theme-init', 'true');
        btn.addEventListener('click', function() {
            var theme = nextTheme(currentTheme());
            applyTheme(theme);
            persistTheme(theme, btn.dataset.themeEndpoint);
        });
    });
    // Paint the icons of freshly added toggles to the current state.
    var theme = currentTheme();
    document.querySelectorAll('[data-theme-toggle]').forEach(function(btn) {
        btn.setAttribute('aria-label', themeLabel(theme));
        btn.querySelectorAll('[data-theme-icon]').forEach(function(icon) {
            icon.classList.toggle('hidden', icon.dataset.themeIcon !== theme);
        });
    });
}

// Resolve a color token (e.g. '--color-danger') to a concrete rgb() for
// canvas/Chart.js. getComputedStyle().getPropertyValue() would return the
// raw, unresolved "light-dark(...)" string, so the value is read through a
// probe element's used color instead. Re-call on "themechange".
export function resolveColor(variableName) {
    var probe = document.createElement('span');
    probe.style.color = 'var(' + variableName + ')';
    probe.style.display = 'none';
    document.body.appendChild(probe);
    var color = getComputedStyle(probe).color;
    probe.remove();
    return color;
}
