// Unit tests for the pure RRULE helpers. Run with Node's built-in runner
// (no extra dependency): `just npm run test:js` or `node --test frontend/js/`.

import { test } from 'node:test';
import assert from 'node:assert/strict';

import { parseRRule, buildRRule, unitLabel } from './rrule-utils.js';

test('parseRRule: empty -> defaults', () => {
    assert.deepEqual(parseRRule(''), { freq: '', interval: 1, byday: [] });
    assert.deepEqual(parseRRule(null), { freq: '', interval: 1, byday: [] });
});

test('parseRRule: lenient on casing and RRULE: prefix', () => {
    assert.deepEqual(parseRRule('rrule:FREQ=weekly;byday=fr,mo;INTERVAL=3'), {
        freq: 'WEEKLY',
        interval: 3,
        byday: ['FR', 'MO'],
    });
});

test('parseRRule: ignores unknown parts and bad interval', () => {
    const s = parseRRule('FREQ=MONTHLY;BYMONTHDAY=1;INTERVAL=0');
    assert.equal(s.freq, 'MONTHLY');
    assert.equal(s.interval, 1); // 0 is rejected, default kept
    assert.deepEqual(s.byday, []);
});

test('buildRRule: one-time when no freq', () => {
    assert.equal(buildRRule({ freq: '', interval: 2, byday: ['MO'] }), '');
});

test('buildRRule: omits INTERVAL=1, keeps BYDAY only for weekly', () => {
    assert.equal(buildRRule({ freq: 'DAILY', interval: 1, byday: [] }), 'FREQ=DAILY');
    assert.equal(
        buildRRule({ freq: 'DAILY', interval: 2, byday: ['MO'] }),
        'FREQ=DAILY;INTERVAL=2'
    );
    assert.equal(
        buildRRule({ freq: 'WEEKLY', interval: 2, byday: ['WE', 'MO'] }),
        'FREQ=WEEKLY;INTERVAL=2;BYDAY=MO,WE' // canonical weekday order
    );
});

test('round-trips canonical strings', () => {
    for (const s of [
        '',
        'FREQ=DAILY',
        'FREQ=DAILY;INTERVAL=2',
        'FREQ=WEEKLY;INTERVAL=2;BYDAY=MO,WE',
    ]) {
        assert.equal(buildRRule(parseRRule(s)), s);
    }
});

test('unitLabel: singular/plural per frequency', () => {
    assert.equal(unitLabel('WEEKLY', 1), 'week');
    assert.equal(unitLabel('WEEKLY', 2), 'weeks');
    assert.equal(unitLabel('', 1), '');
});
