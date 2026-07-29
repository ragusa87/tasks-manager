// Reusable <rrule-picker> custom element for RFC-5545 RRULE strings.
//
// Usage (light DOM so surrounding Tailwind styles apply and the internal
// input participates in the enclosing <form>):
//
//   <rrule-picker name="rrule" field-id="id_rrule" value="FREQ=WEEKLY;BYDAY=MO"></rrule-picker>
//
// It renders a small GUI (frequency / interval / weekday chips) plus an
// "advanced" raw text input, and keeps a real <input name="..."> in sync so
// the form submits the RRULE string exactly as before. Because it is a custom
// element it auto-upgrades whenever HTMX swaps the modal in -- no manual init.
//
// Pure parse/build/label helpers live in rrule-utils.js (no dependencies, unit
// testable); only the preview text and the DOM element need rrule.js.

import { RRule } from 'rrule';
import {
    WEEKDAYS,
    FREQUENCIES,
    parseRRule,
    buildRRule,
    unitLabel,
} from './rrule-utils.js';

/** Human-readable summary of an RRULE string (via rrule.js). Tries the raw
 *  string first (so fields the GUI doesn't model, e.g. BYMONTHDAY, still get
 *  described), then falls back to the canonical GUI form. */
export function describeRRule(value) {
    if (!value) return 'One-time only \u2014 will not repeat.';

    const stripped = String(value).trim().replace(/^RRULE:/i, '');
    const candidates = [stripped, buildRRule(parseRRule(value))];
    for (const candidate of candidates) {
        if (!candidate) continue;
        try {
            return `Repeats ${new RRule(RRule.parseString(candidate)).toText()}.`;
        } catch (err) {
            /* try next candidate */
        }
    }
    return 'Custom recurrence rule.';
}

const INPUT_CLASSES =
    'focus:ring-blue-500 focus:border-blue-500 block w-full shadow-sm sm:text-sm border-gray-300 rounded-md';
const CHIP_BASE =
    'rrule-weekday px-2.5 py-1 text-xs font-medium rounded-md border cursor-pointer transition-colors';
const CHIP_ON = 'bg-blue-600 text-white border-blue-600';
const CHIP_OFF = 'bg-white text-gray-700 border-gray-300 hover:bg-gray-50';

// Guard so importing describeRRule in a non-DOM env (tests/SSR) is safe.
if (typeof HTMLElement !== 'undefined' && typeof customElements !== 'undefined') {
    class RRulePickerElement extends HTMLElement {
        connectedCallback() {
            // Guard so a re-connect (HTMX moving nodes) doesn't wipe input.
            if (this._initialized) return;
            this._initialized = true;

            this.name = this.getAttribute('name') || 'rrule';
            this.fieldId = this.getAttribute('field-id') || '';
            const initial = this.getAttribute('value') || '';
            this.state = parseRRule(initial);

            this._render(initial);
            this._bind();
            this._writeGui();
            this._refreshVisibility();
            this._preview.textContent = describeRRule(initial);
        }

        _render(initial) {
            const freqOptions = FREQUENCIES.map(
                (f) =>
                    `<option value="${f.code}"${
                        f.code === this.state.freq ? ' selected' : ''
                    }>${f.label}</option>`
            ).join('');

            const chips = WEEKDAYS.map(
                (w) =>
                    `<button type="button" class="${CHIP_BASE} ${CHIP_OFF}" data-code="${w.code}" data-active="false">${w.label}</button>`
            ).join('');

            this.innerHTML = `
                <div class="space-y-2">
                    <div class="flex flex-wrap items-center gap-2">
                        <select data-role="freq" id="${this.fieldId}" class="${INPUT_CLASSES} w-auto">${freqOptions}</select>
                        <div data-role="interval-wrap" class="flex items-center gap-1.5 text-sm text-gray-600">
                            <span>every</span>
                            <input type="number" min="1" data-role="interval" value="${
                                this.state.interval || 1
                            }" class="${INPUT_CLASSES} w-16">
                            <span data-role="unit"></span>
                        </div>
                    </div>
                    <div data-role="weekdays" class="flex flex-wrap gap-1.5">${chips}</div>
                    <p data-role="preview" class="text-xs text-gray-500"></p>
                    <div>
                        <button type="button" data-role="advanced-toggle" class="text-xs text-blue-600 hover:underline">Edit raw pattern</button>
                        <input type="text" name="${this.name}" value="${initial}" data-role="raw"
                               class="${INPUT_CLASSES} mt-1 hidden font-mono"
                               placeholder="e.g. FREQ=MONTHLY;BYMONTHDAY=1">
                    </div>
                </div>
            `;

            this._freq = this.querySelector('[data-role="freq"]');
            this._intervalWrap = this.querySelector('[data-role="interval-wrap"]');
            this._interval = this.querySelector('[data-role="interval"]');
            this._unit = this.querySelector('[data-role="unit"]');
            this._weekdays = this.querySelector('[data-role="weekdays"]');
            this._chips = Array.from(this.querySelectorAll('.rrule-weekday'));
            this._preview = this.querySelector('[data-role="preview"]');
            this._raw = this.querySelector('[data-role="raw"]');
            this._advancedToggle = this.querySelector('[data-role="advanced-toggle"]');
        }

        _bind() {
            this._freq.addEventListener('change', () => {
                this._readGui();
                this._commit();
            });
            this._interval.addEventListener('input', () => {
                this._readGui();
                this._commit();
            });
            this._chips.forEach((chip) => {
                chip.addEventListener('click', () => {
                    this._setChip(chip, chip.dataset.active !== 'true');
                    this._readGui();
                    this._commit();
                });
            });
            // Typing a raw pattern re-syncs the GUI but keeps the user's text.
            this._raw.addEventListener('input', () => {
                this.state = parseRRule(this._raw.value);
                this._writeGui();
                this._refreshVisibility();
                this._preview.textContent = describeRRule(this._raw.value);
            });
            this._advancedToggle.addEventListener('click', () => {
                this._raw.classList.toggle('hidden');
            });
        }

        _setChip(chip, active) {
            chip.dataset.active = active ? 'true' : 'false';
            const on = CHIP_ON.split(' ');
            const off = CHIP_OFF.split(' ');
            chip.classList.remove(...(active ? off : on));
            chip.classList.add(...(active ? on : off));
        }

        /** Controls -> this.state. */
        _readGui() {
            this.state.freq = this._freq.value;
            this.state.interval = parseInt(this._interval.value, 10) || 1;
            this.state.byday = this._chips
                .filter((c) => c.dataset.active === 'true')
                .map((c) => c.dataset.code);
        }

        /** this.state -> controls. */
        _writeGui() {
            this._freq.value = this.state.freq;
            this._interval.value = this.state.interval || 1;
            this._chips.forEach((chip) =>
                this._setChip(chip, this.state.byday.includes(chip.dataset.code))
            );
        }

        _refreshVisibility() {
            const hasFreq = Boolean(this.state.freq);
            this._intervalWrap.classList.toggle('hidden', !hasFreq);
            this._weekdays.classList.toggle('hidden', this.state.freq !== 'WEEKLY');
            this._unit.textContent = unitLabel(this.state.freq, this.state.interval || 1);
        }

        /** Recompute the canonical string from the GUI and publish it. */
        _commit() {
            const value = buildRRule(this.state);
            this._raw.value = value;
            this._refreshVisibility();
            this._preview.textContent = describeRRule(value);
        }
    }

    if (!customElements.get('rrule-picker')) {
        customElements.define('rrule-picker', RRulePickerElement);
    }
}
