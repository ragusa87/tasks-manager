// Pure helpers for the voice-note recorder. No DOM or browser APIs here so
// they run under Node's test runner (`just npm run test:js`).

export const MAX_RECORDING_MS = 60000;

// Recordings are encoded client-side as 16-bit PCM WAV: unlike the webm/mp4
// containers MediaRecorder produces (which content sniffers report as
// video/*), a RIFF/WAV file is detected as audio everywhere, including by
// the server's magic-byte check (audio/x-wav). 16 kHz mono keeps a 1-minute
// voice note under 2 MB.
export const WAV_SAMPLE_RATE = 16000;

export function recordingFilename(now) {
    const pad = (n) => String(n).padStart(2, '0');
    const stamp = [
        now.getFullYear(),
        pad(now.getMonth() + 1),
        pad(now.getDate()),
    ].join('-') + '-' + [
        pad(now.getHours()),
        pad(now.getMinutes()),
        pad(now.getSeconds()),
    ].join('');
    return 'voice-note-' + stamp + '.wav';
}

// Concatenate the Float32Array frames collected during capture.
export function mergeChunks(chunks) {
    let total = 0;
    for (const chunk of chunks) total += chunk.length;
    const merged = new Float32Array(total);
    let offset = 0;
    for (const chunk of chunks) {
        merged.set(chunk, offset);
        offset += chunk.length;
    }
    return merged;
}

// Linear-interpolation resampler; returns the input untouched when the
// target rate is not lower than the source rate.
export function downsample(samples, fromRate, toRate) {
    if (toRate >= fromRate) return samples;
    const ratio = fromRate / toRate;
    const length = Math.floor(samples.length / ratio);
    const out = new Float32Array(length);
    for (let i = 0; i < length; i++) {
        const pos = i * ratio;
        const idx = Math.floor(pos);
        const frac = pos - idx;
        const next = Math.min(idx + 1, samples.length - 1);
        out[i] = samples[idx] * (1 - frac) + samples[next] * frac;
    }
    return out;
}

// Mono 16-bit PCM WAV (44-byte canonical header + samples).
export function encodeWavPcm16(samples, sampleRate) {
    const buffer = new ArrayBuffer(44 + samples.length * 2);
    const view = new DataView(buffer);
    const writeString = (offset, s) => {
        for (let i = 0; i < s.length; i++) view.setUint8(offset + i, s.charCodeAt(i));
    };
    writeString(0, 'RIFF');
    view.setUint32(4, 36 + samples.length * 2, true);
    writeString(8, 'WAVE');
    writeString(12, 'fmt ');
    view.setUint32(16, 16, true); // fmt chunk size
    view.setUint16(20, 1, true); // PCM
    view.setUint16(22, 1, true); // mono
    view.setUint32(24, sampleRate, true);
    view.setUint32(28, sampleRate * 2, true); // byte rate
    view.setUint16(32, 2, true); // block align
    view.setUint16(34, 16, true); // bits per sample
    writeString(36, 'data');
    view.setUint32(40, samples.length * 2, true);
    let offset = 44;
    for (let i = 0; i < samples.length; i++, offset += 2) {
        const s = Math.max(-1, Math.min(1, samples[i]));
        view.setInt16(offset, s < 0 ? s * 0x8000 : s * 0x7fff, true);
    }
    return buffer;
}

// "0:07", "1:00" -- used for the elapsed / max readout while recording.
export function formatClock(ms) {
    const totalSeconds = Math.max(0, Math.floor(ms / 1000));
    const minutes = Math.floor(totalSeconds / 60);
    const seconds = String(totalSeconds % 60).padStart(2, '0');
    return minutes + ':' + seconds;
}

// Downsample an analyser's byte frequency data (0..255 per bin) into
// barCount levels in 0..1, averaging the bins that fall into each bar.
export function barLevels(frequencyData, barCount) {
    const levels = [];
    if (!barCount) return levels;
    const chunk = frequencyData.length / barCount;
    for (let i = 0; i < barCount; i++) {
        const start = Math.floor(i * chunk);
        const end = Math.min(frequencyData.length, Math.max(start + 1, Math.floor((i + 1) * chunk)));
        let sum = 0;
        for (let j = start; j < end; j++) sum += frequencyData[j];
        const count = end - start;
        levels.push(count > 0 ? sum / count / 255 : 0);
    }
    return levels;
}
