// Voice-note recorder next to the document dropzone. The mic button asks
// for microphone permission, records for at most one minute while a live
// level meter mirrors the mic input, and on stop attaches the recording
// through the same upload pipeline as a dropzone drop.
//
// Capture is raw PCM encoded client-side to 16 kHz mono WAV rather than
// MediaRecorder: MediaRecorder only offers webm/mp4 containers, which
// content sniffers (including the server's magic-byte check) report as
// video/*, whereas WAV is detected as audio everywhere and stays portable.
import { uploadFiles, showToast } from './documents.js';
import {
    MAX_RECORDING_MS,
    WAV_SAMPLE_RATE,
    mergeChunks,
    downsample,
    encodeWavPcm16,
    recordingFilename,
    formatClock,
    barLevels,
} from './audio-recorder-utils.js';

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

    var audioContext = new (window.AudioContext || window.webkitAudioContext)();
    var source = audioContext.createMediaStreamSource(stream);

    var analyser = audioContext.createAnalyser();
    analyser.fftSize = 256;
    source.connect(analyser);
    var freqData = new Uint8Array(analyser.frequencyBinCount);

    // ScriptProcessorNode is deprecated but universally supported and needs
    // no separate worklet file; its output buffer stays silent (all zeros),
    // the destination connection only exists so onaudioprocess fires.
    var processor = audioContext.createScriptProcessor(4096, 1, 1);
    var chunks = [];
    processor.onaudioprocess = function(e) {
        chunks.push(new Float32Array(e.inputBuffer.getChannelData(0)));
    };
    source.connect(processor);
    processor.connect(audioContext.destination);

    var meter = document.getElementById('audio-record-meter-' + itemId);
    var bars = buildBars(meter);
    var timeEl = meter ? meter.querySelector('[data-meter-time]') : null;
    if (meter) {
        meter.classList.remove('hidden');
        meter.classList.add('flex');
    }
    setRecordingUi(btn, true);

    var startedAt = Date.now();
    var rafId = null;

    function draw() {
        // The modal can be closed mid-recording; treat that as an abort.
        if (!btn.isConnected) {
            session.stop();
            return;
        }
        analyser.getByteFrequencyData(freqData);
        var levels = barLevels(freqData, bars.length);
        for (var i = 0; i < bars.length; i++) {
            bars[i].style.height = Math.max(8, Math.round(levels[i] * 100)) + '%';
        }
        if (timeEl) {
            timeEl.textContent = formatClock(Date.now() - startedAt) + ' / ' + formatClock(MAX_RECORDING_MS);
        }
        rafId = requestAnimationFrame(draw);
    }
    rafId = requestAnimationFrame(draw);

    var maxTimer = setTimeout(function() {
        session.stop();
    }, MAX_RECORDING_MS);

    var stopped = false;
    var session = {
        btn: btn,
        stop: function() {
            if (stopped) return;
            stopped = true;

            clearTimeout(maxTimer);
            cancelAnimationFrame(rafId);
            processor.disconnect();
            source.disconnect();
            stream.getTracks().forEach(function(track) {
                track.stop();
            });
            var sampleRate = audioContext.sampleRate;
            audioContext.close();
            setRecordingUi(btn, false);
            if (meter) {
                meter.classList.add('hidden');
                meter.classList.remove('flex');
            }
            activeSession = null;

            if (!btn.isConnected || chunks.length === 0) return;
            var samples = downsample(mergeChunks(chunks), sampleRate, WAV_SAMPLE_RATE);
            var wav = encodeWavPcm16(samples, WAV_SAMPLE_RATE);
            var file = new File([wav], recordingFilename(new Date()), { type: 'audio/wav' });
            uploadFiles(itemId, uploadUrl, [file]);
        },
    };

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
