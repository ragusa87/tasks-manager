// Unit tests for the pure offload page helpers. Run with Node's built-in
// runner: `just npm run test:js` or `node --test frontend/js/`.

import { test } from 'node:test';
import assert from 'node:assert/strict';

import { MAX_TITLE_LENGTH, composeNote, composeOffload, fmtSize } from './offload-utils.js';

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

test('composeNote: an injected title limit overrides the default', () => {
    const { title } = composeNote('x'.repeat(20), 10);
    assert.equal(title.length, 10);
});

test('composeOffload: nothing captured is an error', () => {
    assert.match(composeOffload({}).error, /Nothing captured/);
    // A title alone is not content — there is nothing to attach it to.
    assert.match(composeOffload({ note: '  \n ', title: 'x' }).error, /Nothing captured/);
});

test('composeOffload: note only behaves like composeNote', () => {
    const plan = composeOffload({ note: 'Buy milk\n2 liters' });
    assert.equal(plan.title, 'Buy milk');
    assert.equal(plan.description, '2 liters');
    assert.deepEqual(plan.parts, ['note']);
    assert.equal(plan.label, 'Offload note');
});

test('composeOffload: everything at once goes out as one item', () => {
    const plan = composeOffload({
        note: 'Fix the sink', hasPhoto: true, hasAudio: true,
    });
    assert.equal(plan.title, 'Fix the sink');
    assert.deepEqual(plan.parts, ['note', 'photo', 'voice']);
    assert.equal(plan.label, 'Offload note + photo + voice');
});

test('composeOffload: an explicit title demotes the whole note to the description', () => {
    const plan = composeOffload({ title: ' Kitchen leak ', note: 'Fix the sink\nunder the counter' });
    assert.equal(plan.title, 'Kitchen leak');
    assert.equal(plan.description, 'Fix the sink\nunder the counter');
});

test('composeOffload: an explicit title titles a media-only send', () => {
    const plan = composeOffload({ title: 'Receipt', hasPhoto: true });
    assert.equal(plan.title, 'Receipt');
    assert.equal(plan.description, '');
    assert.equal(plan.label, 'Offload photo');
});

test('composeOffload: generated titles name what is attached', () => {
    assert.equal(
        composeOffload({ hasPhoto: true, stamp: '29 Jul, 14:02' }).title,
        'Photo · 29 Jul, 14:02',
    );
    assert.equal(
        composeOffload({ hasAudio: true, clock: '0:42', stamp: '29 Jul, 14:02' }).title,
        'Voice memo · 0:42 · 29 Jul, 14:02',
    );
    assert.equal(
        composeOffload({ hasPhoto: true, hasAudio: true, clock: '0:42', stamp: '29 Jul, 14:02' }).title,
        'Photo + Voice memo · 0:42 · 29 Jul, 14:02',
    );
});

test('composeOffload: the title limit applies to the explicit title', () => {
    const plan = composeOffload({ title: 'x'.repeat(20), hasPhoto: true }, 10);
    assert.equal(plan.title.length, 10);
});

test('fmtSize: whole KB below 1 MB, one decimal above', () => {
    assert.equal(fmtSize(512), '1 KB');
    assert.equal(fmtSize(220 * 1024), '220 KB');
    assert.equal(fmtSize(1.44 * 1024 * 1024), '1.4 MB');
});
