// Unit tests for the pure chart helpers. Run with Node's built-in runner:
// `just npm run test:js` or `node --test frontend/js/`.

import { test } from 'node:test';
import assert from 'node:assert/strict';

import { formatBytes } from './charts-utils.js';

test('formatBytes: bytes below 1 KiB stay integral', () => {
    assert.equal(formatBytes(0), '0 B');
    assert.equal(formatBytes(512), '512 B');
    assert.equal(formatBytes(1023), '1023 B');
});

test('formatBytes: scales through KB/MB/GB/TB with one decimal', () => {
    assert.equal(formatBytes(1024), '1.0 KB');
    assert.equal(formatBytes(1536), '1.5 KB');
    assert.equal(formatBytes(2 * 1024 * 1024), '2.0 MB');
    assert.equal(formatBytes(3.5 * 1024 ** 3), '3.5 GB');
    assert.equal(formatBytes(1024 ** 4), '1.0 TB');
});

test('formatBytes: caps at TB for absurd sizes', () => {
    assert.equal(formatBytes(1024 ** 5), '1024.0 TB');
});
