// Reusable <rrule-picker> custom element for RFC-5545 RRULE strings.
//
// Progressive enhancement over server-rendered markup (see the RRULE block in
// templates/partials/item_form_detail.html): the element ships a
// <template data-gui> holding the GUI controls plus a real
// <input data-role="raw" name="..."> that participates in the enclosing
// <form>. On upgrade the GUI is cloned in front of the input and bound;
// without JS the input alone still submits its value unchanged. Display
// identity (classes, option/chip labels) stays in the Django template —
// weekday-chip state styling is keyed on aria-pressed in main.css — and this
// module only wires behavior. Because it is a custom element it auto-upgrades
// whenever HTMX swaps the modal in; no manual init.
//
// Pure parse/build/label helpers live in rrule-utils.js (no dependencies, unit
// testable); only the preview text and the DOM element need rrule.js.

import { RRule } from 'rrule';
import { parseRRule, buildRRule, unitLabel } from './rrule-utils.js';

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

// Guard so importing describeRRule in a non-DOM env (tests/SSR) is safe.
if (typeof HTMLElement !== 'undefined' && typeof customElements !== 'undefined') {
    class RRulePickerElement extends HTMLElement {
        connectedCallback() {
            // Guard so a re-connect (HTMX moving nodes) doesn't wipe input.
            if (this._initialized) return;

            const template = this.querySelector('template[data-gui]');
            this._raw = this.querySelector('[data-role="raw"]');
            if (!template || !this._raw) return; // nothing to enhance
            this._initialized = true;

            // Reveal the GUI: clone the server-rendered controls in front of
            // the raw input (the real form field, Django-escaped value).
            this.insertBefore(template.content.firstElementChild.cloneNode(true), this._raw);
            template.remove();

            const initial = this._raw.value;
            this.state = parseRRule(initial);

            this._freq = this.querySelector('[data-role="freq"]');
            this._intervalWrap = this.querySelector('[data-role="interval-wrap"]');
            this._interval = this.querySelector('[data-role="interval"]');
            this._unit = this.querySelector('[data-role="unit"]');
            this._weekdays = this.querySelector('[data-role="weekdays"]');
            this._chips = Array.from(this.querySelectorAll('.rrule-weekday'));
            this._preview = this.querySelector('[data-role="preview"]');
            this._advancedToggle = this.querySelector('[data-role="advanced-toggle"]');

            this._bind();
            this._writeGui();
            this._refreshVisibility();
            this._preview.textContent = describeRRule(initial);
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
                const visible = this._raw.classList.toggle('hidden') === false;
                this._advancedToggle.setAttribute('aria-expanded', String(visible));
            });
        }

        _setChip(chip, active) {
            // Appearance is keyed on aria-pressed by the .rrule-weekday rules
            // in main.css; only the state flips here.
            chip.dataset.active = active ? 'true' : 'false';
            chip.setAttribute('aria-pressed', active ? 'true' : 'false');
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
