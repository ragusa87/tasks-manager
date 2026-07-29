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
    composeNote,
    fmtSize,
} from './offload-utils.js';
import { initThemeToggle } from './theme.js';
import { startLevelMeter } from './audio-meter.js';

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

function csrfToken() {
    const input = document.querySelector('[name=csrfmiddlewaretoken]');
    return input ? input.value : '';
}

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
});

/* -- photo ---------------------------------------------------- */
$('camBtn').onclick = () => $('camIn').click();
$('libBtn').onclick = () => $('libIn').click();
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
    say('Image ready.', 'idle');
}

function clearPhoto() {
    state.photo = null;
    $('shot').innerHTML = '<span class="font-mono text-[10px] tracking-[.12em] text-muted">No image</span>';
    $('shotHint').textContent = `Max ${LIMIT_LABEL}.`;
}

/* -- microphone permission -----------------------------------
   Four things can block a mic, and they need different fixes:
   an iframe policy, an insecure origin, a browser-level block,
   or a missing device. Guessing wastes the user's time, so we
   name which one it is and how to undo it.
   ------------------------------------------------------------ */
const MIC = { state: 'checking', perm: null };

const EMBEDDED = (() => {
    try { return window.self !== window.top; } catch { return true; }
})();

function recovery() {
    const ua = navigator.userAgent;
    const iOS = /iP(hone|ad|od)/.test(ua) || (/Macintosh/.test(ua) && navigator.maxTouchPoints > 1);
    if (iOS) return 'Safari: tap \u201caA\u201d beside the address bar \u2192 Website Settings \u2192 Microphone \u2192 Allow. Then check iOS Settings \u2192 Safari \u2192 Microphone.';
    if (/Firefox/.test(ua)) return 'Firefox: click the padlock in the address bar, clear the blocked Microphone permission, then reload.';
    if (/Android/.test(ua)) return 'Chrome: tap the sliders icon left of the address bar \u2192 Permissions \u2192 Microphone \u2192 Allow, then reload.';
    return 'Chrome/Edge: click the padlock in the address bar \u2192 Microphone \u2192 Allow, then reload. On macOS also check System Settings \u2192 Privacy & Security \u2192 Microphone.';
}

const MIC_UI = {
    checking: { chip: 'Mic \u00b7 checking', label: 'Record', live: true, hint: '' },
    granted: { chip: 'Mic \u00b7 ready', label: 'Record', live: true, hint: '' },
    prompt: {
        chip: 'Mic \u00b7 not asked yet', label: 'Enable microphone', live: true,
        hint: 'Grant access once up front, so Record starts instantly instead of losing your first words to the permission dialog.',
    },
    denied: { chip: 'Mic \u00b7 blocked', label: 'Try again', live: true, hint: recovery },
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

function setMic(micState) {
    MIC.state = micState;
    const ui = MIC_UI[micState];
    const chip = $('micChip');
    chip.textContent = ui.chip;
    chip.dataset.state = micState;
    chip.classList.remove(...CHIP_GOOD, ...CHIP_BAD);
    if (micState === 'granted') chip.classList.add(...CHIP_GOOD);
    else if (micState !== 'checking' && micState !== 'prompt') chip.classList.add(...CHIP_BAD);
    $('recLbl').textContent = ui.label;
    $('recBtn').disabled = !ui.live;
    $('recDot').hidden = micState !== 'granted';
    $('micHint').textContent = typeof ui.hint === 'function' ? ui.hint() : ui.hint;
    $('micRecheck').hidden = micState === 'granted' || micState === 'checking' || micState === 'prompt';
}

/* Read the current state without triggering a prompt. */
async function probeMic() {
    if (!window.isSecureContext) return setMic('insecure');
    const AudioContextClass = window.AudioContext || window.webkitAudioContext;
    if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia || !AudioContextClass) {
        return setMic('unsupported');
    }

    if (EMBEDDED) {
        // Permissions-Policy tells us outright, where the browser exposes it.
        const policy = document.featurePolicy || document.permissionsPolicy;
        try {
            if (policy && policy.allowsFeature && !policy.allowsFeature('microphone')) {
                return setMic('embedded');
            }
        } catch { /* not exposed -- fall through and let getUserMedia decide */ }
    }

    if (navigator.permissions && navigator.permissions.query) {
        try {
            const p = await navigator.permissions.query({ name: 'microphone' });
            MIC.perm = p;
            // Fires when the user fixes it in site settings -- no reload needed.
            p.onchange = () => setMic(p.state === 'prompt' ? 'prompt' : p.state);
            if (p.state === 'granted') return setMic('granted');
            if (p.state === 'denied') return setMic('denied');
        } catch { /* Firefox and Safari reject the descriptor */ }
    }

    try {
        const devices = await navigator.mediaDevices.enumerateDevices();
        if (devices.length && !devices.some((d) => d.kind === 'audioinput')) return setMic('nodevice');
    } catch { /* non-fatal */ }

    return setMic('prompt');
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

/* They may have left to fix it in settings; Safari has no onchange. */
document.addEventListener('visibilitychange', () => {
    if (!document.hidden && MIC.state !== 'granted' && MIC.state !== 'checking') probeMic();
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
    $('play').hidden = true;
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
        say('Nothing captured.', 'err');
        return;
    }
    state.audio = file;
    const a = $('play');
    if (a.src) URL.revokeObjectURL(a.src); // previous take, if any
    a.src = URL.createObjectURL(file);
    a.hidden = false;
    if (file.size > MAX_BYTES) {
        say(`Memo is ${fmtSize(file.size)} \u2014 over the ${LIMIT_LABEL} limit.`, 'err');
    } else {
        say(`Memo ready \u00b7 ${formatClock(state.audioMs)} \u00b7 ${fmtSize(file.size)}`, 'idle');
    }
}

/* -- send ----------------------------------------------------- */
const stamp = () => new Date().toLocaleString(undefined, { day: '2-digit', month: 'short', hour: '2-digit', minute: '2-digit' });

function compose() {
    if (state.mode === 0) {
        const note = composeNote($('note').value, MAX_TITLE_LENGTH);
        if (note.error) return { error: note.error };
        return { body: note };
    }
    if (state.mode === 1) {
        if (!state.photo) return { error: 'No image picked yet.' };
        const ext = (state.photo.name.match(/\.\w+$/) || ['.jpg'])[0];
        return {
            body: { title: $('shotCap').value.trim() || 'Photo \u00b7 ' + stamp(), description: '' },
            file: state.photo,
            name: 'photo-' + Date.now() + ext,
        };
    }
    if (!state.audio) return { error: 'No memo recorded yet.' };
    return {
        body: { title: $('memoCap').value.trim() || `Voice memo \u00b7 ${formatClock(state.audioMs)} \u00b7 ${stamp()}`, description: '' },
        file: state.audio,
        name: state.audio.name,
    };
}

async function offload() {
    if (state.busy) return;

    const plan = compose();
    if (plan.error) { say(plan.error, 'err'); return; }
    if (plan.file && plan.file.size > MAX_BYTES) {
        say(`Attachment is ${fmtSize(plan.file.size)} \u2014 over the ${LIMIT_LABEL} limit.`, 'err');
        return;
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

    /* No attachment -> done. */
    if (!plan.file) {
        land(`201 \u00b7 item #${item.id} \u00b7 inbox`);
        return release();
    }

    /* Attachment -> second request. Fails loudly, the item is already saved. */
    try {
        const fd = new FormData();
        fd.append('file', plan.file, plan.name);
        const r = await fetch(EP.docs(item.id), {
            method: 'POST',
            headers: { 'X-CSRFToken': csrfToken() }, // no Content-Type: the browser sets the boundary
            body: fd,
        });
        if (r.ok) {
            land(`201 \u00b7 item #${item.id} \u00b7 inbox \u00b7 ${plan.name} attached`);
        } else {
            const text = await r.text();
            say(`Item #${item.id} saved, but the upload failed: ${httpMessage(r, text)}`, 'err');
        }
    } catch (err) {
        say(`Item #${item.id} saved, but the upload never left (${err.name}).`, 'err');
    }
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

function land(msg) {
    say(msg, 'ok');
    if (navigator.vibrate) navigator.vibrate(18);
    const f = $('flight');
    f.dataset.fly = '1';
    setTimeout(() => f.dataset.fly = '0', 520);
    if (state.mode === 0) {
        $('note').value = '';
        $('count').textContent = `0 / ${MAX_TITLE_LENGTH}`;
    }
    if (state.mode === 1) {
        clearPhoto();
        $('shotCap').value = '';
    }
    if (state.mode === 2) {
        state.audio = null;
        const a = $('play');
        if (a.src) URL.revokeObjectURL(a.src);
        a.removeAttribute('src');
        a.hidden = true;
        $('memoCap').value = '';
        $('clock').textContent = '0:00';
        $('recLbl').textContent = 'Record';
    }
}

function release() {
    state.busy = false;
    $('offloadBtn').disabled = false;
}

$('offloadBtn').onclick = offload;
addEventListener('keydown', (e) => {
    if ((e.metaKey || e.ctrlKey) && e.key === 'Enter') {
        e.preventDefault();
        offload();
    }
});

/* -- boot ----------------------------------------------------- */
paintMode(0);
probeMic();
initThemeToggle();
say('Ready');
