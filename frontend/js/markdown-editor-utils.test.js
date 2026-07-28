import { test } from 'node:test';
import assert from 'node:assert/strict';

import { AUTOLINK_RE, isUrlLike, resolveLinkEdit } from './markdown-editor-utils.js';

test('isUrlLike: accepts http/https URLs', () => {
    assert.equal(isUrlLike('https://example.com'), true);
    assert.equal(isUrlLike('http://example.com/a?b=1'), true);
    assert.equal(isUrlLike('  https://example.com  '), true);
});

test('isUrlLike: rejects labels and other schemes', () => {
    assert.equal(isUrlLike('documentation'), false);
    assert.equal(isUrlLike('see https://example.com'), false); // not the whole string
    assert.equal(isUrlLike('ftp://example.com'), false);
    assert.equal(isUrlLike(''), false);
    assert.equal(isUrlLike(null), false);
});

test('resolveLinkEdit: URL-like text follows the new href', () => {
    const r = resolveLinkEdit('https://me.com', 'https://me.com', 'https://example.com');
    assert.deepEqual(r, { text: 'https://example.com', href: 'https://example.com' });
});

test('resolveLinkEdit: text mirroring the old href follows the new href', () => {
    // Covers text that equals the old href even if not strictly URL-like.
    const r = resolveLinkEdit('mailto:a@b.ch', 'mailto:a@b.ch', 'https://example.com');
    assert.deepEqual(r, { text: 'https://example.com', href: 'https://example.com' });
});

test('resolveLinkEdit: a real label is kept, only href changes ([text](url) style)', () => {
    const r = resolveLinkEdit('the docs', 'https://old.example', 'https://new.example');
    assert.deepEqual(r, { text: 'the docs', href: 'https://new.example' });
});

test('resolveLinkEdit: new link from selection keeps the selected label', () => {
    const r = resolveLinkEdit('read this', '', 'https://example.com');
    assert.deepEqual(r, { text: 'read this', href: 'https://example.com' });
});

test('resolveLinkEdit: new link with no selection inserts the URL as text', () => {
    const r = resolveLinkEdit('', '', 'https://example.com');
    assert.deepEqual(r, { text: 'https://example.com', href: 'https://example.com' });
});

test('AUTOLINK_RE: matches a typed URL followed by whitespace', () => {
    const m = 'see https://example.com '.match(AUTOLINK_RE);
    assert.ok(m);
    assert.equal(m[1], 'https://example.com');
});

test('AUTOLINK_RE: does not fire on a URL ending with sentence punctuation', () => {
    // "com." then space: the "." can be neither the URL end nor the trigger,
    // so nothing autolinks (better no link than a link including the period).
    assert.equal('see https://example.com. '.match(AUTOLINK_RE), null);
});

test('AUTOLINK_RE: no match without a trailing whitespace trigger', () => {
    assert.equal('https://example.com'.match(AUTOLINK_RE), null);
});
