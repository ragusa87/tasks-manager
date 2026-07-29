// Pure helpers of the offload quick-capture page (offload.js). Kept free of
// DOM and browser APIs so they run under Node's test runner.

// The API's ItemIn title limit (task_processor/api/schemas.py).
export const MAX_TITLE_LENGTH = 1024;

// Split a note into the item payload: first line becomes the title
// (truncated to the API limit), the remaining lines the description.
export function composeNote(raw) {
    const text = (raw || '').trim();
    if (!text) return { error: 'Nothing typed yet.' };
    const [first, ...rest] = text.split('\n');
    return {
        title: first.slice(0, MAX_TITLE_LENGTH),
        description: rest.join('\n').trim(),
    };
}

// Human file size for the readout: whole KB below 1 MB, one decimal above.
export function fmtSize(bytes) {
    if (bytes < 1024 * 1024) return Math.round(bytes / 1024) + ' KB';
    return (bytes / (1024 * 1024)).toFixed(1) + ' MB';
}
