// Unit tests for the pure offload page helpers. Run with Node's built-in
// runner: `just npm run test:js` or `node --test frontend/js/`.

import { test } from 'node:test';
import assert from 'node:assert/strict';

import { MAX_TITLE_LENGTH, composeNote, fmtSize } from './offload-utils.js';

test('composeNote: first line is the title, the rest the description', () => {
    assert.deepEqual(composeNote('Buy milk\n2 liters\nlactose free'), {
        title: 'Buy milk',
        description: '2 liters\nlactose free',
    });
});

test('composeNote: single line has an empty description', () => {
    assert.deepEqual(composeNote('Buy milk'), {
        title: 'Buy milk',
        description: '',
    });
});

test('composeNote: surrounding whitespace is stripped', () => {
    assert.deepEqual(composeNote('  Buy milk  \n\n  '), {
        title: 'Buy milk',
        description: '',
    });
});

test('composeNote: empty input is an error', () => {
    assert.equal(composeNote('').error, 'Nothing typed yet.');
    assert.equal(composeNote('   \n  ').error, 'Nothing typed yet.');
    assert.equal(composeNote(null).error, 'Nothing typed yet.');
});

test('composeNote: title is truncated to the API limit', () => {
    const { title } = composeNote('x'.repeat(MAX_TITLE_LENGTH + 50));
    assert.equal(title.length, MAX_TITLE_LENGTH);
});

test('fmtSize: whole KB below 1 MB, one decimal above', () => {
    assert.equal(fmtSize(512), '1 KB');
    assert.equal(fmtSize(220 * 1024), '220 KB');
    assert.equal(fmtSize(1.44 * 1024 * 1024), '1.4 MB');
});
