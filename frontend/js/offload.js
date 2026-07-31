// Offload quick-capture page (templates/items/offload.html): one screen to
// throw a note, a photo or a voice memo into the inbox. Talks to the JSON
// API with the Django session cookie + CSRF token (no bearer key), then
// attaches files through POST /api/items/{id}/documents.
import '../css/main.css';
import '../css/offload.css';
import {
    MAX_RECORDING_MS as DEFAULT_RECORDING_MS,
    formatClock,
} from './audio-recorder-utils.js';
import { startCaptureSession } from './audio-capture.js';
import {
    MAX_TITLE_LENGTH as DEFAULT_TITLE_LIMIT,
    composeOffload,
    fmtSize,
} from './offload-utils.js';
import { initThemeToggle } from './theme.js';
import { startLevelMeter } from './audio-meter.js';
import { getCsrfToken as csrfToken } from './csrf.js';

const EP = {
    items: '/api/items',
    docs: (id) => `/api/items/${id}/documents`,
};
// Server policy, injected by the template so it cannot drift from
// settings.MAX_FILE_SIZE / the model title limit.
const MAX_BYTES = Number(document.body.dataset.maxBytes) || 10 * 1024 * 1024;
const MAX_TITLE_LENGTH = Number(document.body.dataset.maxTitleLength) || DEFAULT_TITLE_LIMIT;
const MAX_RECORDING_MS =
    Number(document.body.dataset.maxRecordingSeconds) * 1000 || DEFAULT_RECORDING_MS;
const LIMIT_LABEL = fmtSize(MAX_BYTES);

const $ = (id) => document.getElementById(id);

const state = { mode: 0, photo: null, audio: null, audioMs: 0, busy: false };

/* -- readout: this thing never lies and never says "something went wrong" -- */
const READOUT_KINDS = {
    idle: 'text-muted',
    ok: 'text-accent',
    err: 'text-danger',
};

function say(text, kind) {
    const el = $('readout');
    el.textContent = text;
    el.classList.remove(...Object.values(READOUT_KINDS));
    el.classList.add(READOUT_KINDS[kind || 'idle']);
}

/* -- mode strip + swipe --------------------------------------- */
const track = $('track');
const tabs = [...$('modes').querySelectorAll('button')];
const panels = [...track.querySelectorAll('[role="tabpanel"]')];

function paintMode(i) {
    state.mode = i;
    if (i !== 1) closeCamera(); // don't keep the camera live off-screen
    $('rule').style.transform = `translateX(${i * 100}%)`;
    tabs.forEach((t, n) => {
        t.setAttribute('aria-selected', String(n === i));
        t.tabIndex = n === i ? 0 : -1;
    });
    // Off-screen panels stay in the snap track but must not be reachable by
    // Tab: focusing one would scroll it into view without updating the mode,
    // desyncing what gets submitted.
    panels.forEach((p, n) => { p.inert = n !== i; });
}
function selectMode(i) {
    track.scrollTo({ left: track.clientWidth * i, behavior: 'smooth' });
    paintMode(i);
}
tabs.forEach((t) => t.addEventListener('click', () => selectMode(+t.dataset.i)));
$('modes').addEventListener('keydown', (e) => {
    const delta = { ArrowRight: 1, ArrowLeft: -1 }[e.key];
    if (!delta) return;
    e.preventDefault();
    const i = (state.mode + delta + tabs.length) % tabs.length;
    selectMode(i);
    tabs[i].focus();
});
let scrollTick;
track.addEventListener('scroll', () => {
    clearTimeout(scrollTick);
    scrollTick = setTimeout(() => {
        const i = Math.round(track.scrollLeft / track.clientWidth);
        if (i !== state.mode && i >= 0 && i <= 2) paintMode(i);
    }, 60);
}, { passive: true });

/* -- note ----------------------------------------------------- */
$('note').addEventListener('input', (e) => {
    const n = e.target.value.trim().split('\n')[0].length;
    const c = $('count');
    c.textContent = `${n} / ${MAX_TITLE_LENGTH}`;
    c.classList.toggle('text-danger', n > MAX_TITLE_LENGTH);
    refreshOffload();
});

/* -- photo -----------------------------------------------------
   Camera = a real getUserMedia preview in the stage with a capture
   button. The hidden file input (capture=environment) stays as the
   fallback: it is what opens the native camera app on phones, and
   it still works when live video is unavailable or denied. */
let camStream = null;
let camDeviceId = null; // last camera the user switched to, sticky for the session

$('camBtn').onclick = openCamera;
$('libBtn').onclick = () => $('libIn').click();

/* Camera and Library are mutually exclusive: a live getUserMedia preview
   collides with the native library picker on mobile, so while the camera
   is running Library goes dead, and while it isn't Camera is the only way
   to start one. Driven entirely by whether camStream is live. */
function syncCaptureButtons() {
    const live = !!camStream;
    $('camBtn').disabled = live;
    $('libBtn').disabled = live;
}

async function acquireCamera() {
    if (camDeviceId) {
        try {
            return await navigator.mediaDevices.getUserMedia({
                video: { deviceId: { exact: camDeviceId } },
                audio: false,
            });
        } catch { camDeviceId = null; } // device gone -- fall back to the default
    }
    return navigator.mediaDevices.getUserMedia({
        video: { facingMode: 'environment' },
        audio: false,
    });
}

/* Selfie cameras preview mirrored everywhere else; match that. The
   captured frame stays unmirrored, like a native camera app. */
function paintPreviewMirror(video) {
    const track = camStream && camStream.getVideoTracks()[0];
    video.classList.toggle('-scale-x-100', !!track && track.getSettings().facingMode === 'user');
}

async function switchCamera() {
    if (!camStream) return;
    let inputs;
    try {
        inputs = (await navigator.mediaDevices.enumerateDevices()).filter((d) => d.kind === 'videoinput');
    } catch { return; }
    if (inputs.length < 2) return;
    const current = camStream.getVideoTracks()[0].getSettings().deviceId;
    const i = inputs.findIndex((d) => d.deviceId === current);
    const next = inputs[(i + 1) % inputs.length];
    stopCamera(); // mobile browsers refuse two live cameras at once
    try {
        camStream = await navigator.mediaDevices.getUserMedia({
            video: { deviceId: { exact: next.deviceId } },
            audio: false,
        });
    } catch (err) {
        clearPhoto();
        say(`Could not switch camera (${(err && err.name) || 'unknown'}).`, 'err');
        return;
    }
    camDeviceId = next.deviceId;
    syncCaptureButtons(); // new stream live -- keep Library dead
    const video = $('shot').querySelector('video');
    video.srcObject = camStream;
    paintPreviewMirror(video);
    say(next.label ? `Camera: ${next.label}` : 'Camera switched.', 'idle');
}

async function openCamera() {
    if (camStream) return; // preview already live
    if (!window.isSecureContext || !navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
        $('camIn').click();
        return;
    }
    // getUserMedia can take seconds before the permission dialog or the
    // stream shows up; the pulsing chip owns up to the wait right away.
    setCam('starting');
    say('Starting camera…', 'idle');
    try {
        camStream = await acquireCamera();
    } catch (err) {
        camError(err); // keeps the chip honest about why
        say(`Live camera unavailable (${(err && err.name) || 'unknown'}) — using the system picker.`, 'idle');
        $('camIn').click();
        return;
    }
    setCam('granted');
    syncCaptureButtons(); // preview is live -- Library goes dead
    state.photo = null; // the preview replaces any previous shot
    const stage = $('shot');
    stage.innerHTML = '';
    const video = document.createElement('video');
    video.autoplay = true;
    video.muted = true;
    video.setAttribute('playsinline', ''); // iOS: inline, not fullscreen
    video.srcObject = camStream;
    video.className = 'block h-full w-full object-contain';
    paintPreviewMirror(video);
    const snap = document.createElement('button');
    snap.className = 'absolute bottom-2 left-1/2 -translate-x-1/2 rounded-xs border border-accent bg-ground px-3 py-1.5 font-mono text-[10px] tracking-[.1em] text-accent';
    snap.textContent = 'CAPTURE';
    snap.onclick = snapPhoto;
    const cancel = document.createElement('button');
    cancel.className = 'absolute top-2 right-2 rounded-xs border border-line bg-ground px-2 py-1.5 font-mono text-[10px] tracking-[.1em] text-muted';
    cancel.textContent = 'CANCEL';
    cancel.onclick = closeCamera;
    const flip = document.createElement('button');
    flip.className = 'absolute top-2 left-2 rounded-xs border border-line bg-ground px-2 py-1.5 font-mono text-[10px] tracking-[.1em] text-muted';
    flip.textContent = 'SWITCH';
    flip.hidden = true; // revealed only when there is something to switch to
    flip.onclick = switchCamera;
    stage.append(video, snap, cancel, flip);
    navigator.mediaDevices.enumerateDevices()
        .then((devices) => {
            flip.hidden = devices.filter((d) => d.kind === 'videoinput').length < 2;
        })
        .catch(() => {});
    refreshOffload();
    say('Camera live — tap Capture.', 'idle');
}

function snapPhoto() {
    const video = $('shot').querySelector('video');
    if (!video || !video.videoWidth) {
        say('Camera not ready yet — give it a second.', 'err');
        return;
    }
    const canvas = document.createElement('canvas');
    canvas.width = video.videoWidth;
    canvas.height = video.videoHeight;
    canvas.getContext('2d').drawImage(video, 0, 0);
    stopCamera();
    canvas.toBlob((blob) => {
        if (!blob) {
            clearPhoto();
            say('Could not read a frame from the camera.', 'err');
            return;
        }
        takePhoto(new File([blob], `camera-${Date.now()}.jpg`, { type: 'image/jpeg' }));
    }, 'image/jpeg', 0.92);
}

function stopCamera() {
    if (!camStream) return false;
    camStream.getTracks().forEach((t) => t.stop());
    camStream = null;
    syncCaptureButtons(); // stream gone -- Library live again
    return true;
}

/* Cancel: stop the stream and put the stage back to its empty state. */
function closeCamera() {
    if (stopCamera()) clearPhoto();
}
[$('camIn'), $('libIn')].forEach((inp) => inp.addEventListener('change', (e) => {
    const f = e.target.files && e.target.files[0];
    if (f) takePhoto(f);
    e.target.value = '';
}));

function takePhoto(file) {
    if (file.size > MAX_BYTES) {
        say(`Image is ${fmtSize(file.size)} \u2014 the ${LIMIT_LABEL} limit rejects it. Try a smaller one.`, 'err');
        return;
    }
    state.photo = file;
    const stage = $('shot');
    stage.innerHTML = '';
    const img = document.createElement('img');
    img.className = 'block h-full w-full object-contain';
    img.src = URL.createObjectURL(file);
    img.alt = 'Selected image';
    img.onload = () => URL.revokeObjectURL(img.src);
    const drop = document.createElement('button');
    drop.className = 'absolute top-2 right-2 rounded-xs border border-line bg-ground px-2 py-1.5 font-mono text-[10px] tracking-[.1em] text-muted';
    drop.textContent = 'REMOVE';
    drop.onclick = clearPhoto;
    stage.append(img, drop);
    $('shotHint').textContent = `${file.type || 'image'} \u00b7 ${fmtSize(file.size)}`;
    refreshOffload();
    say('Image ready.', 'idle');
}

function clearPhoto() {
    state.photo = null;
    $('shot').innerHTML = '<span class="font-mono text-[10px] tracking-[.12em] text-muted">No image</span>';
    $('shotHint').textContent = `Max ${LIMIT_LABEL}.`;
    refreshOffload();
}

/* -- device permissions (mic + camera) ------------------------
   Four things can block a capture device, and they need
   different fixes: an iframe policy, an insecure origin, a
   browser-level block, or a missing device. Guessing wastes the
   user's time, so we name which one it is and how to undo it.
   Each device gets a status chip; the probing is shared.
   ------------------------------------------------------------ */
const MIC = { state: 'checking' };
const CAM = { state: 'checking' };
// PermissionStatus objects must stay referenced or the browser may
// garbage-collect them along with their onchange listener.
const permRefs = [];

const EMBEDDED = (() => {
    try { return window.self !== window.top; } catch { return true; }
})();

function recovery(device) {
    const ua = navigator.userAgent;
    const iOS = /iP(hone|ad|od)/.test(ua) || (/Macintosh/.test(ua) && navigator.maxTouchPoints > 1);
    if (iOS) return `Safari: tap \u201caA\u201d beside the address bar \u2192 Website Settings \u2192 ${device} \u2192 Allow. Then check iOS Settings \u2192 Safari \u2192 ${device}.`;
    if (/Firefox/.test(ua)) return `Firefox: click the padlock in the address bar, clear the blocked ${device} permission, then reload.`;
    if (/Android/.test(ua)) return `Chrome: tap the sliders icon left of the address bar \u2192 Permissions \u2192 ${device} \u2192 Allow, then reload.`;
    return `Chrome/Edge: click the padlock in the address bar \u2192 ${device} \u2192 Allow, then reload. On macOS also check System Settings \u2192 Privacy & Security \u2192 ${device}.`;
}

/* Read the current state of a device permission without prompting. */
async function probePermission({ feature, deviceKind, onChange }) {
    if (!window.isSecureContext) return 'insecure';
    if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) return 'unsupported';

    if (EMBEDDED) {
        // Permissions-Policy tells us outright, where the browser exposes it.
        const policy = document.featurePolicy || document.permissionsPolicy;
        try {
            if (policy && policy.allowsFeature && !policy.allowsFeature(feature)) return 'embedded';
        } catch { /* not exposed -- fall through and let getUserMedia decide */ }
    }

    if (navigator.permissions && navigator.permissions.query) {
        try {
            const p = await navigator.permissions.query({ name: feature });
            permRefs.push(p);
            // Fires when the user fixes it in site settings -- no reload needed.
            p.onchange = () => onChange(p.state === 'prompt' ? 'prompt' : p.state);
            if (p.state === 'granted' || p.state === 'denied') return p.state;
        } catch { /* Firefox and Safari reject the descriptor */ }
    }

    try {
        const devices = await navigator.mediaDevices.enumerateDevices();
        if (devices.length && !devices.some((d) => d.kind === deviceKind)) return 'nodevice';
    } catch { /* non-fatal */ }

    return 'prompt';
}

const MIC_UI = {
    checking: { chip: 'Mic \u00b7 checking', label: 'Record', live: true, hint: '' },
    granted: { chip: 'Mic \u00b7 ready', label: 'Record', live: true, hint: '' },
    prompt: {
        chip: 'Mic \u00b7 not asked yet', label: 'Enable microphone', live: true,
        hint: 'Grant access once up front, so Record starts instantly instead of losing your first words to the permission dialog.',
    },
    denied: { chip: 'Mic \u00b7 blocked', label: 'Try again', live: true, hint: () => recovery('Microphone') },
    insecure: {
        chip: 'Mic \u00b7 needs https', label: 'Record', live: false,
        hint: () => `Recording needs a secure context, and ${location.protocol}//${location.host} is not one. Use localhost or https.`,
    },
    embedded: {
        chip: 'Mic \u00b7 frame blocked', label: 'Record', live: false,
        hint: 'This page is running inside an iframe that withholds microphone access. Open it directly in a browser tab \u2014 a preview pane cannot grant it.',
    },
    unsupported: {
        chip: 'Mic \u00b7 unsupported', label: 'Record', live: false,
        hint: 'This browser exposes no getUserMedia or AudioContext. Chrome, Edge, Firefox and Safari 14.1+ all work.',
    },
    nodevice: { chip: 'Mic \u00b7 no input', label: 'Record', live: false, hint: 'No audio input device is connected.' },
};

const CHIP_GOOD = ['text-accent', 'border-accent/40'];
const CHIP_BAD = ['text-danger', 'border-danger/40'];

const CHIP_WAIT = ['animate-pulse'];

function paintChip(chip, state, text) {
    chip.textContent = text;
    chip.dataset.state = state;
    chip.classList.remove(...CHIP_GOOD, ...CHIP_BAD, ...CHIP_WAIT);
    if (state === 'granted') chip.classList.add(...CHIP_GOOD);
    else if (state === 'checking' || state === 'starting') chip.classList.add(...CHIP_WAIT);
    else if (state !== 'prompt') chip.classList.add(...CHIP_BAD);
}

function setMic(micState) {
    MIC.state = micState;
    const ui = MIC_UI[micState];
    paintChip($('micChip'), micState, ui.chip);
    $('recLbl').textContent = ui.label;
    $('recBtn').disabled = !ui.live;
    $('recDot').hidden = micState !== 'granted';
    $('micHint').textContent = typeof ui.hint === 'function' ? ui.hint() : ui.hint;
    $('micRecheck').hidden = micState === 'granted' || micState === 'checking' || micState === 'prompt';
}

async function probeMic() {
    // The recorder also needs an AudioContext, which the shared probe
    // does not know about.
    const AudioContextClass = window.AudioContext || window.webkitAudioContext;
    if (window.isSecureContext && !AudioContextClass) return setMic('unsupported');
    setMic(await probePermission({ feature: 'microphone', deviceKind: 'audioinput', onChange: setMic }));
}

function micError(err) {
    const name = err && err.name;
    if (name === 'NotAllowedError' || name === 'PermissionDeniedError') {
        setMic('denied');
        say(/system|policy/i.test(err.message || '')
            ? 'The operating system is withholding the microphone from this browser.'
            : 'Microphone denied. See the fix on the Voice tab.', 'err');
    } else if (name === 'NotFoundError' || name === 'DevicesNotFoundError') {
        setMic('nodevice');
        say('No microphone found.', 'err');
    } else if (name === 'NotReadableError' || name === 'TrackStartError') {
        setMic('granted');
        say('The microphone is held by another app. Close it and try again.', 'err');
    } else if (name === 'SecurityError') {
        setMic('insecure');
        say('Refused as an insecure context.', 'err');
    } else {
        say(`Microphone failed: ${name || 'unknown error'}.`, 'err');
    }
}

/* Ask for the grant on its own, so the first recording isn't half-eaten
   by the permission dialog. */
async function grantMic() {
    say('Asking for microphone access\u2026', 'idle');
    try {
        const probe = await navigator.mediaDevices.getUserMedia({ audio: true });
        probe.getTracks().forEach((t) => t.stop()); // we wanted the grant, not the stream
        setMic('granted');
        say('Microphone ready. Tap Record.', 'ok');
    } catch (err) { micError(err); }
}

$('micRecheck').onclick = () => { setMic('checking'); probeMic(); };

/* Camera chip: same states as the mic, but the Camera button never goes
   dead — every broken state falls back to the system picker instead. */
const CAM_UI = {
    checking: { chip: 'Camera · checking', hint: '' },
    starting: { chip: 'Camera · starting…', hint: '' },
    granted: { chip: 'Camera · ready', hint: '' },
    prompt: { chip: 'Camera · not asked yet', hint: 'The browser asks the first time you tap Camera.' },
    denied: {
        chip: 'Camera · blocked',
        hint: () => recovery('Camera') + ' Until then, Camera opens the system picker instead.',
    },
    insecure: {
        chip: 'Camera · needs https',
        hint: () => `The live preview needs a secure context, and ${location.protocol}//${location.host} is not one. Camera opens the system picker instead.`,
    },
    embedded: {
        chip: 'Camera · frame blocked',
        hint: 'This page is running inside an iframe that withholds camera access. Camera opens the system picker instead.',
    },
    unsupported: {
        chip: 'Camera · unsupported',
        hint: 'This browser exposes no getUserMedia, so Camera opens the system picker instead.',
    },
    nodevice: { chip: 'Camera · no camera', hint: 'No camera is connected. Library still works.' },
};

function setCam(camState) {
    CAM.state = camState;
    const ui = CAM_UI[camState];
    paintChip($('camChip'), camState, ui.chip);
    $('camHint').textContent = typeof ui.hint === 'function' ? ui.hint() : ui.hint;
    $('camRecheck').hidden = camState === 'granted' || camState === 'checking'
        || camState === 'starting' || camState === 'prompt';
}

async function probeCam() {
    setCam(await probePermission({ feature: 'camera', deviceKind: 'videoinput', onChange: setCam }));
}

function camError(err) {
    const name = (err && err.name) || '';
    if (name === 'NotAllowedError' || name === 'PermissionDeniedError') setCam('denied');
    else if (name === 'NotFoundError' || name === 'DevicesNotFoundError') setCam('nodevice');
    else if (name === 'SecurityError') setCam('insecure');
    else if (name === 'NotReadableError' || name === 'TrackStartError') setCam('granted');
    else probeCam(); // unknown failure -- re-probe rather than stay on "starting"
}

$('camRecheck').onclick = () => { setCam('checking'); probeCam(); };

/* They may have left to fix it in settings; Safari has no onchange. */
document.addEventListener('visibilitychange', () => {
    if (document.hidden) return;
    if (MIC.state !== 'granted' && MIC.state !== 'checking') probeMic();
    if (CAM.state !== 'granted' && CAM.state !== 'checking') probeCam();
});

/* -- voice capture (shared WAV pipeline, see audio-capture.js;
      level meter shared with the dropzone recorder, see audio-meter.js) -- */
let session = null;
let meter = null;
let tick = null;

$('recBtn').onclick = () => {
    if (session) return session.stop();
    if (MIC.state === 'granted') return startRec();
    return grantMic(); // prompt, denied -> ask again and report honestly
};

function setRecLive(live) {
    $('recBtn').classList.toggle('border-danger', live);
    $('clock').classList.toggle('text-danger', live);
    const dot = $('recDot');
    dot.classList.toggle('bg-danger', live);
    dot.classList.toggle('bg-line', !live);
    dot.classList.toggle('offload-dot-live', live);
}

async function startRec() {
    let stream;
    try {
        stream = await navigator.mediaDevices.getUserMedia({ audio: true });
    } catch (err) {
        micError(err);
        return;
    }

    state.audio = null;
    refreshOffload();
    $('playRow').hidden = true;
    $('recLbl').textContent = 'Stop';
    setRecLive(true);
    say('Recording\u2026', 'idle');

    session = startCaptureSession(stream, {
        fftSize: 256,
        maxMs: MAX_RECORDING_MS,
        onStop: finishRec,
    });
    tick = setInterval(() => {
        $('clock').textContent = formatClock(Date.now() - session.startedAt);
    }, 200);
    meter = startLevelMeter(session.analyser, $('scope'));
}

function finishRec(file) {
    clearInterval(tick);
    if (meter) {
        meter.stop();
        meter = null;
    }
    state.audioMs = Math.min(Date.now() - session.startedAt, MAX_RECORDING_MS);
    session = null;
    setRecLive(false);
    $('recLbl').textContent = 'Record again';

    if (!file) {
        refreshOffload();
        say('Nothing captured.', 'err');
        return;
    }
    state.audio = file;
    refreshOffload();
    const a = $('play');
    if (a.src) URL.revokeObjectURL(a.src); // previous take, if any
    a.src = URL.createObjectURL(file);
    $('playRow').hidden = false;
    if (file.size > MAX_BYTES) {
        say(`Memo is ${fmtSize(file.size)} \u2014 over the ${LIMIT_LABEL} limit.`, 'err');
    } else {
        say(`Memo ready \u00b7 ${formatClock(state.audioMs)} \u00b7 ${fmtSize(file.size)}`, 'idle');
    }
}

function clearMemo() {
    state.audio = null;
    state.audioMs = 0;
    const a = $('play');
    if (a.src) URL.revokeObjectURL(a.src);
    a.removeAttribute('src');
    $('playRow').hidden = true;
    $('clock').textContent = '0:00';
    if (MIC.state === 'granted') $('recLbl').textContent = 'Record';
    refreshOffload();
}

$('memoDrop').onclick = () => {
    clearMemo();
    say('Memo removed.', 'idle');
};

/* -- send -------------------------------------------------------
   One press sends everything captured across the tabs as a single
   item: the note (and shared title) shape the item, the photo and
   the memo follow as documents. composeOffload (offload-utils.js)
   owns the wording; this side owns the files and the requests. */
const stamp = () => new Date().toLocaleString(undefined, { day: '2-digit', month: 'short', hour: '2-digit', minute: '2-digit' });

function compose() {
    const plan = composeOffload({
        note: $('note').value,
        title: $('itemTitle').value,
        hasPhoto: !!state.photo,
        hasAudio: !!state.audio,
        clock: state.audio ? formatClock(state.audioMs) : '',
        stamp: stamp(),
    }, MAX_TITLE_LENGTH);
    if (plan.error) return plan;

    const files = [];
    if (state.photo) {
        const ext = (state.photo.name.match(/\.\w+$/) || ['.jpg'])[0];
        files.push({ file: state.photo, name: 'photo-' + Date.now() + ext });
    }
    if (state.audio) files.push({ file: state.audio, name: state.audio.name });
    return {
        body: { title: plan.title, description: plan.description },
        files,
    };
}

async function offload() {
    if (state.busy) return;

    const plan = compose();
    if (plan.error) { say(plan.error, 'err'); return; }
    for (const { file, name } of plan.files) {
        if (file.size > MAX_BYTES) {
            say(`${name} is ${fmtSize(file.size)} \u2014 over the ${LIMIT_LABEL} limit.`, 'err');
            return;
        }
    }

    state.busy = true;
    $('offloadBtn').disabled = true;
    say('Sending\u2026', 'idle');

    let item;
    try {
        const r = await fetch(EP.items, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json', 'X-CSRFToken': csrfToken() },
            body: JSON.stringify({ ...plan.body, status: 'inbox' }),
        });
        const text = await r.text();
        if (!r.ok) {
            say(httpMessage(r, text), 'err');
            return release();
        }
        item = JSON.parse(text);
    } catch (err) {
        say(`Never reached the server (${err.name}). Check the network.`, 'err');
        return release();
    }

    /* Attachments follow one by one. A failure is loud but not fatal:
       the item and any earlier files are already saved, so the state is
       kept for a retry (which would create a fresh item). */
    let attached = 0;
    for (const { file, name } of plan.files) {
        const saved = attached
            ? `Item #${item.id} saved with ${attached}/${plan.files.length} files`
            : `Item #${item.id} saved`;
        try {
            const fd = new FormData();
            fd.append('file', file, name);
            const r = await fetch(EP.docs(item.id), {
                method: 'POST',
                headers: { 'X-CSRFToken': csrfToken() }, // no Content-Type: the browser sets the boundary
                body: fd,
            });
            if (!r.ok) {
                const text = await r.text();
                say(`${saved}, but ${name} failed: ${httpMessage(r, text)}`, 'err');
                return release();
            }
            attached += 1;
        } catch (err) {
            say(`${saved}, but ${name} never left (${err.name}).`, 'err');
            return release();
        }
    }

    land(`201 \u00b7 item #${item.id} \u00b7 inbox${attached ? ` \u00b7 ${attached} file${attached > 1 ? 's' : ''} attached` : ''}`);
    release();
}

function httpMessage(r, text) {
    if (r.status === 401) return 'Session expired \u2014 reload the page and sign in.';
    if (r.status === 403) return 'Request blocked (CSRF/session) \u2014 reload the page.';
    let detail = text.slice(0, 180);
    try {
        const j = JSON.parse(text);
        detail = j.detail || detail;
    } catch { /* not JSON -- keep the excerpt */ }
    return `${r.status} \u00b7 ${detail}`;
}

/* Everything went out as one item, so every tab starts over. */
function land(msg) {
    say(msg, 'ok');
    if (navigator.vibrate) navigator.vibrate(18);
    const f = $('flight');
    f.dataset.fly = '1';
    setTimeout(() => f.dataset.fly = '0', 520);
    $('note').value = '';
    $('count').textContent = `0 / ${MAX_TITLE_LENGTH}`;
    $('itemTitle').value = '';
    closeCamera();
    clearPhoto();
    clearMemo();
}

function release() {
    state.busy = false;
    refreshOffload();
}

/* The button always names what the next press sends ("Offload note +
   photo") and goes dead when there is nothing to send. */
function refreshOffload() {
    const plan = composeOffload({
        note: $('note').value,
        title: $('itemTitle').value,
        hasPhoto: !!state.photo,
        hasAudio: !!state.audio,
    });
    $('offloadBtn').textContent = plan.error ? 'Offload' : plan.label;
    $('offloadBtn').disabled = state.busy || !!plan.error;
}

$('offloadBtn').onclick = offload;
$('itemTitle').addEventListener('input', refreshOffload);
addEventListener('keydown', (e) => {
    if ((e.metaKey || e.ctrlKey) && e.key === 'Enter') {
        e.preventDefault();
        offload();
    }
});

/* -- boot ----------------------------------------------------- */
paintMode(0);
refreshOffload();
probeMic();
probeCam();
initThemeToggle();
say('Ready');
