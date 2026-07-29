// Pure helpers of the offload quick-capture page (offload.js). Kept free of
// DOM and browser APIs so they run under Node's test runner.

// Fallback for the API's ItemIn title limit; the page normally injects the
// live value via <body data-max-title-length> (see offload.js).
export const MAX_TITLE_LENGTH = 1024;

// Split a note into the item payload: first line becomes the title
// (truncated to the API limit), the remaining lines the description.
export function composeNote(raw, titleLimit = MAX_TITLE_LENGTH) {
    const text = (raw || '').trim();
    if (!text) return { error: 'Nothing typed yet.' };
    const [first, ...rest] = text.split('\n');
    return {
        title: first.slice(0, titleLimit),
        description: rest.join('\n').trim(),
    };
}

// One press of Offload sends everything captured across the three tabs as a
// single item: the note becomes title + description, the photo and the voice
// memo attach as documents. Pure: the files themselves stay in offload.js,
// only their presence (hasPhoto / hasAudio) matters here.
//
// input: { note, title, hasPhoto, hasAudio, clock, stamp } where title is the
// shared optional title field, clock the memo duration ("0:42") and stamp a
// locale date string — the last two preformatted by the caller so this stays
// clock-free and testable.
//
// Returns { error } when nothing is captured, otherwise
// { title, description, parts, label } where parts lists what goes out
// (['note', 'photo', 'voice']) and label is the Offload button text.
export function composeOffload(input, titleLimit = MAX_TITLE_LENGTH) {
    const note = (input.note || '').trim();
    const explicit = (input.title || '').trim();

    const parts = [];
    if (note) parts.push('note');
    if (input.hasPhoto) parts.push('photo');
    if (input.hasAudio) parts.push('voice');
    if (!parts.length) {
        return { error: 'Nothing captured yet — type a note, pick a photo or record a memo.' };
    }

    // Title precedence: the shared title field, then the note's first line,
    // then a generated stamp. With an explicit title the whole note is
    // description, so nothing typed is dropped silently.
    let title;
    let description;
    if (explicit) {
        title = explicit.slice(0, titleLimit);
        description = note;
    } else if (note) {
        ({ title, description } = composeNote(note, titleLimit));
    } else {
        title = [
            [input.hasPhoto && 'Photo', input.hasAudio && 'Voice memo'].filter(Boolean).join(' + '),
            input.hasAudio && input.clock,
            input.stamp,
        ].filter(Boolean).join(' · ');
        description = '';
    }

    return { title, description, parts, label: 'Offload ' + parts.join(' + ') };
}

// Human file size for the readout: whole KB below 1 MB, one decimal above.
export function fmtSize(bytes) {
    if (bytes < 1024 * 1024) return Math.round(bytes / 1024) + ' KB';
    return (bytes / (1024 * 1024)).toFixed(1) + ' MB';
}
