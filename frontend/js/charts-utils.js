// Pure helpers for charts.js, split out for node --test.

// Human-readable byte size, matching Document.file_size_display in Python
// ("512 B", "1.5 KB", "2.0 MB") and extended past MB for aggregate totals.
export function formatBytes(bytes) {
    if (bytes < 1024) return `${bytes} B`;
    let value = bytes;
    let unit = 'B';
    for (const next of ['KB', 'MB', 'GB', 'TB']) {
        if (value < 1024) break;
        value /= 1024;
        unit = next;
    }
    return `${value.toFixed(1)} ${unit}`;
}
