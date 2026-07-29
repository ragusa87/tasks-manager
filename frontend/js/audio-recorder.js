// Voice-note recorder next to the document dropzone. The mic button asks
// for microphone permission, records for at most one minute while a live
// level meter mirrors the mic input, and on stop attaches the recording
// through the same upload pipeline as a dropzone drop.
//
// The capture itself (PCM -> 16 kHz mono WAV) lives in audio-capture.js,
// shared with the offload page.
import { uploadFiles, showToast } from './documents.js';
import {
    MAX_RECORDING_MS,
    formatClock,
    barLevels,
} from './audio-recorder-utils.js';
import { startCaptureSession } from './audio-capture.js';

const BAR_COUNT = 24;

// Only one recording at a time; the active session owns its stop() cleanup.
let activeSession = null;

export function initAudioRecorders() {
    document.querySelectorAll('.audio-record-btn:not([data-initialized])').forEach(function(btn) {
        btn.setAttribute('data-initialized', 'true');
        btn.addEventListener('click', function() {
            toggleRecording(btn);
        });
    });
}

function toggleRecording(btn) {
    if (activeSession) {
        if (activeSession.btn === btn) activeSession.stop();
        return;
    }
    var AudioContextClass = window.AudioContext || window.webkitAudioContext;
    if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia || !AudioContextClass) {
        showToast('Audio recording is not supported by this browser', 'error');
        return;
    }
    navigator.mediaDevices.getUserMedia({ audio: true })
        .then(function(stream) {
            startRecording(btn, stream);
        })
        .catch(function() {
            showToast('Microphone access was denied', 'error');
        });
}

function startRecording(btn, stream) {
    var itemId = btn.dataset.itemId;
    var uploadUrl = btn.dataset.uploadUrl;

    var meter = document.getElementById('audio-record-meter-' + itemId);
    var bars = buildBars(meter);
    var timeEl = meter ? meter.querySelector('[data-meter-time]') : null;
    if (meter) {
        meter.classList.remove('hidden');
        meter.classList.add('flex');
    }
    setRecordingUi(btn, true);

    var rafId = null;
    var session = startCaptureSession(stream, {
        fftSize: 256,
        onStop: function(file) {
            cancelAnimationFrame(rafId);
            setRecordingUi(btn, false);
            if (meter) {
                meter.classList.add('hidden');
                meter.classList.remove('flex');
            }
            activeSession = null;

            // The modal can be closed mid-recording; treat that as an abort.
            if (!btn.isConnected || !file) return;
            uploadFiles(itemId, uploadUrl, [file]);
        },
    });
    session.btn = btn;

    var freqData = new Uint8Array(session.analyser.frequencyBinCount);

    function draw() {
        // The modal can be closed mid-recording; treat that as an abort.
        if (!btn.isConnected) {
            session.stop();
            return;
        }
        session.analyser.getByteFrequencyData(freqData);
        var levels = barLevels(freqData, bars.length);
        for (var i = 0; i < bars.length; i++) {
            bars[i].style.height = Math.max(8, Math.round(levels[i] * 100)) + '%';
        }
        if (timeEl) {
            timeEl.textContent = formatClock(Date.now() - session.startedAt) + ' / ' + formatClock(MAX_RECORDING_MS);
        }
        rafId = requestAnimationFrame(draw);
    }
    rafId = requestAnimationFrame(draw);

    activeSession = session;
}

function setRecordingUi(btn, recording) {
    var micIcon = btn.querySelector('[data-icon-record]');
    var stopIcon = btn.querySelector('[data-icon-stop]');
    if (micIcon) micIcon.classList.toggle('hidden', recording);
    if (stopIcon) stopIcon.classList.toggle('hidden', !recording);
    btn.classList.toggle('border-red-400', recording);
    btn.classList.toggle('text-red-600', recording);
    btn.classList.toggle('bg-red-50', recording);
}

function buildBars(meter) {
    var container = meter ? meter.querySelector('[data-meter-bars]') : null;
    if (!container) return [];
    container.innerHTML = '';
    var bars = [];
    for (var i = 0; i < BAR_COUNT; i++) {
        var bar = document.createElement('div');
        bar.className = 'flex-1 bg-red-400 rounded-sm transition-[height] duration-75';
        bar.style.height = '8%';
        container.appendChild(bar);
        bars.push(bar);
    }
    return bars;
}
