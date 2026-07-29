// Voice-note recorder next to the document dropzone. The mic button asks
// for microphone permission, records for at most one minute while a live
// level meter mirrors the mic input, and on stop attaches the recording
// through the same upload pipeline as a dropzone drop.
//
// The capture itself (PCM -> 16 kHz mono WAV) lives in audio-capture.js,
// shared with the offload page.
import { uploadFiles, showToast } from './documents.js';
import { MAX_RECORDING_MS, formatClock } from './audio-recorder-utils.js';
import { startCaptureSession } from './audio-capture.js';
import { startLevelMeter } from './audio-meter.js';

// Recording cap injected by the template (settings.MAX_RECORDING_SECONDS);
// MAX_RECORDING_MS is only the fallback.
function maxRecordingMs(btn) {
    return Number(btn.dataset.maxRecordingSeconds) * 1000 || MAX_RECORDING_MS;
}

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

    var meterEl = document.getElementById('audio-record-meter-' + itemId);
    var barsEl = meterEl ? meterEl.querySelector('[data-meter-bars]') : null;
    var timeEl = meterEl ? meterEl.querySelector('[data-meter-time]') : null;
    if (meterEl) {
        meterEl.classList.remove('hidden');
        meterEl.classList.add('flex');
    }
    setRecordingUi(btn, true);

    var maxMs = maxRecordingMs(btn);
    var meter = null;
    var session = startCaptureSession(stream, {
        fftSize: 256,
        maxMs: maxMs,
        onStop: function(file) {
            if (meter) meter.stop();
            setRecordingUi(btn, false);
            if (meterEl) {
                meterEl.classList.add('hidden');
                meterEl.classList.remove('flex');
            }
            activeSession = null;

            // The modal can be closed mid-recording; treat that as an abort.
            if (!btn.isConnected || !file) return;
            uploadFiles(itemId, uploadUrl, [file]);
        },
    });
    session.btn = btn;

    if (barsEl) {
        meter = startLevelMeter(session.analyser, barsEl, {
            onFrame: function() {
                // The modal can be closed mid-recording; treat that as an abort.
                if (!btn.isConnected) {
                    session.stop();
                    return false;
                }
                if (timeEl) {
                    timeEl.textContent = formatClock(Date.now() - session.startedAt) + ' / ' + formatClock(maxMs);
                }
            },
        });
    }

    activeSession = session;
}

function setRecordingUi(btn, recording) {
    var micIcon = btn.querySelector('[data-icon-record]');
    var stopIcon = btn.querySelector('[data-icon-stop]');
    if (micIcon) micIcon.classList.toggle('hidden', recording);
    if (stopIcon) stopIcon.classList.toggle('hidden', !recording);
    btn.classList.toggle('border-danger', recording);
    btn.classList.toggle('text-danger', recording);
    btn.classList.toggle('bg-danger-ground', recording);
    // The icon swap is color/shape only; mirror the state for AT users. The
    // idle label is the template-rendered one (it embeds the recording limit),
    // so remember it rather than duplicating the wording here.
    if (!btn.dataset.idleLabel) {
        btn.dataset.idleLabel = btn.getAttribute('aria-label') || 'Record a voice note';
    }
    btn.setAttribute('aria-pressed', recording ? 'true' : 'false');
    btn.setAttribute('aria-label', recording ? 'Stop recording' : btn.dataset.idleLabel);
}
