// Unit tests for the pure voice-note recorder helpers. Run with Node's
// built-in runner: `just npm run test:js` or `node --test frontend/js/`.

import { test } from 'node:test';
import assert from 'node:assert/strict';

import {
    MAX_RECORDING_MS,
    WAV_SAMPLE_RATE,
    recordingFilename,
    mergeChunks,
    downsample,
    encodeWavPcm16,
    formatClock,
    barLevels,
} from './audio-recorder-utils.js';

test('MAX_RECORDING_MS is one minute', () => {
    assert.equal(MAX_RECORDING_MS, 60000);
});

test('recordingFilename: timestamped .wav name', () => {
    const now = new Date(2026, 6, 29, 9, 5, 3); // 2026-07-29 09:05:03
    assert.equal(recordingFilename(now), 'voice-note-2026-07-29-090503.wav');
});

test('mergeChunks: concatenates Float32 frames in order', () => {
    const merged = mergeChunks([new Float32Array([1, 2]), new Float32Array([3])]);
    assert.deepEqual(Array.from(merged), [1, 2, 3]);
    assert.equal(mergeChunks([]).length, 0);
});

test('downsample: halves length for a 2:1 ratio, interpolating', () => {
    const samples = new Float32Array([0, 1, 0, 1, 0, 1, 0, 1]);
    const out = downsample(samples, 32000, 16000);
    assert.equal(out.length, 4);
    for (const v of out) assert.ok(v >= 0 && v <= 1);
});

test('downsample: returns input untouched when target rate is not lower', () => {
    const samples = new Float32Array([0.5, -0.5]);
    assert.equal(downsample(samples, 16000, 16000), samples);
    assert.equal(downsample(samples, 16000, 48000), samples);
});

test('encodeWavPcm16: canonical RIFF/WAVE header for 16 kHz mono', () => {
    const wav = encodeWavPcm16(new Float32Array([0, 1, -1]), WAV_SAMPLE_RATE);
    const view = new DataView(wav);
    const tag = (offset, length) =>
        String.fromCharCode(...new Uint8Array(wav, offset, length));

    assert.equal(wav.byteLength, 44 + 3 * 2);
    assert.equal(tag(0, 4), 'RIFF');
    assert.equal(view.getUint32(4, true), 36 + 3 * 2);
    assert.equal(tag(8, 4), 'WAVE');
    assert.equal(tag(12, 4), 'fmt ');
    assert.equal(view.getUint16(20, true), 1); // PCM
    assert.equal(view.getUint16(22, true), 1); // mono
    assert.equal(view.getUint32(24, true), 16000);
    assert.equal(view.getUint32(28, true), 32000); // byte rate
    assert.equal(view.getUint16(32, true), 2); // block align
    assert.equal(view.getUint16(34, true), 16); // bits per sample
    assert.equal(tag(36, 4), 'data');
    assert.equal(view.getUint32(40, true), 3 * 2);
});

test('encodeWavPcm16: samples scaled to int16 and clamped', () => {
    const wav = encodeWavPcm16(new Float32Array([0, 1, -1, 2, -2]), 16000);
    const view = new DataView(wav);
    assert.equal(view.getInt16(44, true), 0);
    assert.equal(view.getInt16(46, true), 0x7fff);
    assert.equal(view.getInt16(48, true), -0x8000);
    assert.equal(view.getInt16(50, true), 0x7fff); // clamped
    assert.equal(view.getInt16(52, true), -0x8000); // clamped
});

test('formatClock: m:ss, floors partial seconds, clamps negatives', () => {
    assert.equal(formatClock(0), '0:00');
    assert.equal(formatClock(7999), '0:07');
    assert.equal(formatClock(60000), '1:00');
    assert.equal(formatClock(-500), '0:00');
});

test('barLevels: averages bins per bar, scaled to 0..1', () => {
    const data = [255, 255, 0, 0];
    assert.deepEqual(barLevels(data, 2), [1, 0]);
    assert.deepEqual(barLevels([255, 0], 1), [0.5]);
});

test('barLevels: more bars than bins reuses bins, never NaN', () => {
    const levels = barLevels([255, 0], 4);
    assert.equal(levels.length, 4);
    for (const level of levels) {
        assert.ok(Number.isFinite(level));
        assert.ok(level >= 0 && level <= 1);
    }
});

test('barLevels: empty data or zero bars', () => {
    assert.deepEqual(barLevels([], 3), [0, 0, 0]);
    assert.deepEqual(barLevels([255], 0), []);
});
