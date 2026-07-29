// Unit tests for the pure cookie parsing. Run with Node's built-in runner:
// `just npm run test:js` or `node --test frontend/js/`.

import { test } from 'node:test';
import assert from 'node:assert/strict';

import { csrfTokenFromCookie } from './csrf.js';

test('finds csrftoken among other cookies', () => {
    const cookies = 'sessionid=abc; csrftoken=eDsnABqZnZ3OuI3mFAadTry6Z10vKXXu; theme=dark';
    assert.equal(csrfTokenFromCookie(cookies), 'eDsnABqZnZ3OuI3mFAadTry6Z10vKXXu');
});

test('finds csrftoken when it is the only cookie', () => {
    assert.equal(csrfTokenFromCookie('csrftoken=tok'), 'tok');
});

test('ignores cookies whose name merely ends with csrftoken', () => {
    assert.equal(csrfTokenFromCookie('notcsrftoken=evil; csrftoken=good'), 'good');
    assert.equal(csrfTokenFromCookie('notcsrftoken=evil'), '');
});

test('returns empty string when absent or empty', () => {
    assert.equal(csrfTokenFromCookie(''), '');
    assert.equal(csrfTokenFromCookie(undefined), '');
    assert.equal(csrfTokenFromCookie('sessionid=abc; theme=dark'), '');
});

test('decodes percent-encoded values', () => {
    assert.equal(csrfTokenFromCookie('csrftoken=a%3Db'), 'a=b');
});

test('supports a custom cookie name', () => {
    assert.equal(csrfTokenFromCookie('mytoken=tok', 'mytoken'), 'tok');
});
