// Pure RRULE (RFC-5545) helpers -- no DOM, no third-party imports, so they are
// trivially unit-testable and reusable. The <rrule-picker> element and the
// human-readable preview (which needs rrule.js) live in rrule-picker.js.

export const WEEKDAYS = [
    { code: 'MO', label: 'Mon' },
    { code: 'TU', label: 'Tue' },
    { code: 'WE', label: 'Wed' },
    { code: 'TH', label: 'Thu' },
    { code: 'FR', label: 'Fri' },
    { code: 'SA', label: 'Sat' },
    { code: 'SU', label: 'Sun' },
];

export const FREQUENCIES = [
    { code: '', label: 'One-time (no repeat)' },
    { code: 'DAILY', label: 'Daily' },
    { code: 'WEEKLY', label: 'Weekly' },
    { code: 'MONTHLY', label: 'Monthly' },
    { code: 'YEARLY', label: 'Yearly' },
];

const WEEKDAY_ORDER = WEEKDAYS.map((w) => w.code);

/** Parse an RRULE string into {freq, interval, byday}. Lenient on casing and
 *  an optional leading "RRULE:" prefix; unknown parts are ignored. */
export function parseRRule(value) {
    const state = { freq: '', interval: 1, byday: [] };
    if (!value) return state;

    const clean = String(value).trim().replace(/^RRULE:/i, '');
    for (const part of clean.split(';')) {
        const [rawKey, rawVal] = part.split('=');
        if (!rawKey || rawVal == null) continue;
        const key = rawKey.trim().toUpperCase();
        const val = rawVal.trim();

        if (key === 'FREQ') {
            state.freq = val.toUpperCase();
        } else if (key === 'INTERVAL') {
            const n = parseInt(val, 10);
            if (!Number.isNaN(n) && n > 0) state.interval = n;
        } else if (key === 'BYDAY') {
            state.byday = val
                .split(',')
                .map((d) => d.trim().toUpperCase())
                .filter(Boolean);
        }
    }
    return state;
}

/** Build a canonical RRULE string from {freq, interval, byday}. Returns "" for
 *  a one-time (no frequency) rule. INTERVAL is omitted when it is 1 (default),
 *  and BYDAY only applies to weekly rules. */
export function buildRRule(state) {
    if (!state || !state.freq) return '';

    const parts = [`FREQ=${state.freq}`];
    const interval = parseInt(state.interval, 10);
    if (!Number.isNaN(interval) && interval > 1) parts.push(`INTERVAL=${interval}`);

    if (state.freq === 'WEEKLY' && Array.isArray(state.byday) && state.byday.length) {
        const sorted = WEEKDAY_ORDER.filter((code) => state.byday.includes(code));
        if (sorted.length) parts.push(`BYDAY=${sorted.join(',')}`);
    }
    return parts.join(';');
}

/** Singular/plural interval unit label for a frequency. */
export function unitLabel(freq, interval) {
    const plural = interval > 1;
    switch (freq) {
        case 'DAILY':
            return plural ? 'days' : 'day';
        case 'WEEKLY':
            return plural ? 'weeks' : 'week';
        case 'MONTHLY':
            return plural ? 'months' : 'month';
        case 'YEARLY':
            return plural ? 'years' : 'year';
        default:
            return '';
    }
}
