// Single source of the CSRF token for fetch/htmx POSTs.
//
// The token is read from the csrftoken cookie, not from a rendered
// [name=csrfmiddlewaretoken] input: the reverse-proxy login silently
// re-authenticates when the Django session expires, which rotates the CSRF
// secret — a token baked into a long-open page then no longer matches the
// cookie and every POST 403s. The cookie is always current (Django >= 4.1
// accepts the raw cookie value as a token). The DOM input remains as a
// fallback for the CSRF_USE_SESSIONS / CSRF_COOKIE_HTTPONLY configurations,
// where the cookie is not readable from JS.

export function csrfTokenFromCookie(cookieString, cookieName = 'csrftoken') {
    if (!cookieString) return '';
    const prefix = cookieName + '=';
    for (const part of cookieString.split(';')) {
        const cookie = part.trim();
        if (cookie.startsWith(prefix)) {
            return decodeURIComponent(cookie.slice(prefix.length));
        }
    }
    return '';
}

export function getCsrfToken() {
    const fromCookie = csrfTokenFromCookie(document.cookie);
    if (fromCookie) return fromCookie;
    const input = document.querySelector('[name=csrfmiddlewaretoken]');
    return input ? input.value : '';
}
