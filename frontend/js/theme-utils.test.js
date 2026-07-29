// Unit tests for the pure theme helpers. Run with Node's built-in runner:
// `just npm run test:js` or `node --test frontend/js/`.

import { test } from 'node:test';
import assert from 'node:assert/strict';

import { THEME_CYCLE, nextTheme, themeLabel } from './theme-utils.js';

test('cycle order is system -> light -> dark', () => {
    assert.deepEqual(THEME_CYCLE, ['system', 'light', 'dark']);
});

test('nextTheme cycles and wraps around', () => {
    assert.equal(nextTheme('system'), 'light');
    assert.equal(nextTheme('light'), 'dark');
    assert.equal(nextTheme('dark'), 'system');
});

test('nextTheme treats unknown values as system', () => {
    assert.equal(nextTheme(''), 'system');
    assert.equal(nextTheme('bogus'), 'system');
});

test('themeLabel names the state', () => {
    assert.equal(themeLabel('system'), 'Theme: follows system');
    assert.equal(themeLabel('light'), 'Theme: light');
    assert.equal(themeLabel('dark'), 'Theme: dark');
});
