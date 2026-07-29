// Shared recording level meter: fills a container with vertical bars and
// animates them from an AnalyserNode until stopped. Single implementation of
// the recording animation, used by the dropzone voice recorder
// (audio-recorder.js) and the offload page (offload.js).
//
// The per-frame level math lives in audio-recorder-utils.js (pure, unit
// tested); this module is only the DOM/animation glue.
import { barLevels } from './audio-recorder-utils.js';

const BAR_COUNT = 24;
const BAR_CLASS = 'flex-1 bg-danger rounded-sm transition-[height] duration-75';
const IDLE_HEIGHT = '8%';

/**
 * Start animating `container` from `analyser`.
 *
 * `onFrame` (optional) runs before each paint — return `false` to abort the
 * loop (e.g. the recording UI was swapped out); use it for side work like
 * updating an elapsed-time readout.
 *
 * Returns a handle whose `stop()` cancels the animation and rests the bars.
 */
export function startLevelMeter(analyser, container, { onFrame } = {}) {
    container.innerHTML = '';
    const bars = [];
    for (let i = 0; i < BAR_COUNT; i++) {
        const bar = document.createElement('div');
        bar.className = BAR_CLASS;
        bar.style.height = IDLE_HEIGHT;
        container.appendChild(bar);
        bars.push(bar);
    }

    const freqData = new Uint8Array(analyser.frequencyBinCount);
    let rafId = null;

    function draw() {
        if (onFrame && onFrame() === false) return;
        analyser.getByteFrequencyData(freqData);
        const levels = barLevels(freqData, bars.length);
        for (let i = 0; i < bars.length; i++) {
            bars[i].style.height = Math.max(8, Math.round(levels[i] * 100)) + '%';
        }
        rafId = requestAnimationFrame(draw);
    }
    rafId = requestAnimationFrame(draw);

    return {
        stop() {
            cancelAnimationFrame(rafId);
            bars.forEach((bar) => {
                bar.style.height = IDLE_HEIGHT;
            });
        },
    };
}
