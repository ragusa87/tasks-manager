// Pure helpers for <markdown-editor> link handling (no dependencies, unit
// testable -- see markdown-editor-utils.test.js).
//
// Link policy: standard `[label](url)` links are supported, but a link whose
// visible text IS a URL must always point where it says. Concretely:
// - text is URL-like  -> href is forced to match the text
// - text is a label   -> href may differ (classic markdown link)

/** Bare URL detection for autolinking while typing: a URL immediately
 *  followed by whitespace. The last-char class refuses sentence punctuation,
 *  so "https://x.io. " autolinks nothing rather than a URL with the period. */
export const AUTOLINK_RE = /(https?:\/\/[^\s<>]*[^\s<>.,!?;:)\]}"'])(\s)$/;

/** Whether the whole string reads as a URL (what a user would call "a link"). */
export function isUrlLike(text) {
    return /^https?:\/\/\S+$/i.test(String(text || '').trim());
}

/**
 * Decide what a link's text and href become after the user submits a new URL
 * from the toolbar prompt.
 *
 * @param {string} text  current visible text of the link (or selection)
 * @param {string} oldHref  current href ('' when creating a new link)
 * @param {string} newHref  URL submitted from the prompt (already sanitized)
 * @returns {{text: string, href: string}} the resulting text/href pair
 */
export function resolveLinkEdit(text, oldHref, newHref) {
    // A URL-ish text (or one that merely mirrored the old href) follows the
    // new URL; a real label is kept and only the href changes underneath.
    const keepLabel = text && !isUrlLike(text) && text !== oldHref;
    return { text: keepLabel ? text : newHref, href: newHref };
}

/**
 * Attrs for a list item rebuilt while converting a list between bullet and
 * ordered. Never copy attrs verbatim: Milkdown's markdown parser stamps
 * `spread` as a *string* ("true"/"false") while the schema validates a
 * boolean, so recreating nodes from copied attrs throws — which is what
 * silently broke ordered->bullet. Coerce and set explicitly.
 *
 * @param {object} attrs  the item's current attrs
 * @param {boolean} isOrdered  whether the target list is ordered
 * @param {number} index  zero-based item position (for the ordered label)
 */
export function convertedListItemAttrs(attrs, isOrdered, index) {
    return {
        spread: attrs.spread === true || attrs.spread === 'true',
        listType: isOrdered ? 'ordered' : 'bullet',
        label: isOrdered ? `${index + 1}.` : '•',
    };
}
