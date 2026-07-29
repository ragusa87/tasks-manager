// Shared microphone capture session: raw PCM in, 16 kHz mono WAV File out.
//
// Capture is raw PCM encoded client-side to WAV rather than MediaRecorder:
// MediaRecorder only offers webm/mp4 containers, which content sniffers
// (including the server's magic-byte check) report as video/*, whereas WAV
// is detected as audio everywhere and stays portable.
//
// Used by the in-app voice-note recorder (audio-recorder.js) and the
// offload page (offload.js), which differ only in visualization and in
// what they do with the finished file.
import {
    MAX_RECORDING_MS,
    WAV_SAMPLE_RATE,
    mergeChunks,
    downsample,
    encodeWavPcm16,
    recordingFilename,
} from './audio-recorder-utils.js';

// startCaptureSession(stream, { fftSize, maxMs, onStop })
//     -> { analyser, startedAt, stop }
//
// Owns the AudioContext graph (source -> analyser + ScriptProcessor), the
// auto-stop timer (`maxMs`, normally the server-injected recording limit;
// MAX_RECORDING_MS is only the fallback) and the WAV encoding. `analyser` is
// for the caller's visualization loop. stop() is idempotent: it tears the
// graph down, then calls onStop(file) exactly once -- file is null when
// nothing was captured. The caller keeps its own rAF loop and cancels it in
// onStop.
export function startCaptureSession(stream, options) {
    var onStop = options.onStop;
    var maxMs = options.maxMs || MAX_RECORDING_MS;

    var audioContext = new (window.AudioContext || window.webkitAudioContext)();
    var source = audioContext.createMediaStreamSource(stream);

    var analyser = audioContext.createAnalyser();
    analyser.fftSize = options.fftSize || 256;
    source.connect(analyser);

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

    var maxTimer = setTimeout(function() {
        session.stop();
    }, maxMs);

    var stopped = false;
    var session = {
        analyser: analyser,
        startedAt: Date.now(),
        stop: function() {
            if (stopped) return;
            stopped = true;

            clearTimeout(maxTimer);
            processor.disconnect();
            source.disconnect();
            stream.getTracks().forEach(function(track) {
                track.stop();
            });
            var sampleRate = audioContext.sampleRate;
            audioContext.close();

            var file = null;
            if (chunks.length > 0) {
                var samples = downsample(
                    mergeChunks(chunks), sampleRate, WAV_SAMPLE_RATE
                );
                var wav = encodeWavPcm16(samples, WAV_SAMPLE_RATE);
                file = new File([wav], recordingFilename(new Date()), {
                    type: 'audio/wav',
                });
            }
            onStop(file);
        },
    };
    return session;
}
