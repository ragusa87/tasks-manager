import { getCsrfToken } from './csrf.js';

// Batch-action selection for list pages (dashboard, tags, areas).
//
// All selection state is per-page-load and lives here; it reaches the server
// as ids / select_all + q / excluded_ids (see task_processor/batch.py).
// Visibility of the checkboxes and the bar is CSS-driven by the `batch-mode`
// class on <body> (see main.css), so it survives htmx OOB swaps of the list.
let selectAll = false;
const excluded = new Set();

const bar = () => document.getElementById('batch-bar');
const rowBoxes = () => Array.from(document.querySelectorAll('input.batch-checkbox'));

function resetSelection() {
    selectAll = false;
    excluded.clear();
    rowBoxes().forEach((box) => { box.checked = false; });
    syncUi();
}

function syncUi() {
    const barEl = bar();
    if (!barEl) return;
    const boxes = rowBoxes();
    const checked = boxes.filter((box) => box.checked).length;
    const total = parseInt(barEl.dataset.totalCount || '0', 10);
    const count = selectAll ? Math.max(total - excluded.size, 0) : checked;

    document.getElementById('batch-select-all-input').value = selectAll ? '1' : '';
    document.getElementById('batch-excluded-input').value = Array.from(excluded).join(',');
    document.getElementById('batch-count').textContent =
        selectAll ? `All ${count} selected` : `${count} selected`;

    document.querySelectorAll('.batch-action-btn').forEach((btn) => {
        btn.disabled = count === 0;
    });

    const pageBox = document.getElementById('batch-select-page');
    if (pageBox) {
        pageBox.checked = boxes.length > 0 && checked === boxes.length;
        pageBox.indeterminate = checked > 0 && checked < boxes.length;
    }

    // "Select all N matching" appears once the whole page is ticked (and
    // becomes "Clear selection" while the select-all flag is active).
    const selectAllBtn = document.getElementById('batch-select-all');
    if (selectAllBtn) {
        const pageFullySelected = boxes.length > 0 && checked === boxes.length;
        selectAllBtn.classList.toggle('hidden', !(selectAll || pageFullySelected));
        selectAllBtn.textContent = selectAll
            ? selectAllBtn.dataset.labelClear
            : selectAllBtn.dataset.labelSelect;
    }
}

function selectionEntries() {
    const entries = [];
    if (selectAll) {
        entries.push(['select_all', '1']);
        const q = bar()?.querySelector('input[name="q"]')?.value;
        if (q) entries.push(['q', q]);
        if (excluded.size) entries.push(['excluded_ids', Array.from(excluded).join(',')]);
    } else {
        rowBoxes()
            .filter((box) => box.checked)
            .forEach((box) => entries.push(['ids', box.value]));
    }
    return entries;
}

function submitBatchAction(url) {
    const entries = selectionEntries();

    // Below the sm breakpoint the modal is cramped: submit a real form so the
    // server renders the full-page variant instead (mirrors the item-detail
    // behavior in base.js).
    if (window.matchMedia('(max-width: 639px)').matches) {
        const returnUrl = location.pathname + location.search;
        const form = document.createElement('form');
        form.method = 'post';
        form.action = url + '?returnUrl=' + encodeURIComponent(returnUrl);
        entries.push(['csrfmiddlewaretoken', getCsrfToken()]);
        entries.forEach(([name, value]) => {
            const input = document.createElement('input');
            input.type = 'hidden';
            input.name = name;
            input.value = value;
            form.appendChild(input);
        });
        document.body.appendChild(form);
        form.submit();
        return;
    }

    // Desktop: POST as an HTMX request and open the preview modal, the same
    // #modal-container flow as openItemModal in base.js (close button,
    // Escape, overlay and focus handling all come from there).
    const body = new FormData();
    entries.forEach(([name, value]) => body.append(name, value));
    fetch(url, {
        method: 'POST',
        headers: { 'HX-Request': 'true', 'X-CSRFToken': getCsrfToken() },
        body,
    })
        .then((response) => {
            if (!response.ok) {
                throw new Error(`HTTP ${response.status} loading ${url}`);
            }
            return response.text();
        })
        .then((html) => {
            const container = document.querySelector('#modal-container');
            if (!container) return;
            container.innerHTML = html;
            const modal = document.getElementById('modal');
            if (modal) {
                modal.style.display = 'block';
                htmx.process(modal);
                document.dispatchEvent(new CustomEvent('openmodal'));
                (modal.querySelector('input:not([type="hidden"]), select, button') || modal).focus();
            }
        })
        .catch((error) => console.error('Batch action failed:', error));
}

// In batch mode a row click must not open the item-detail modal: it toggles
// the row's checkbox instead. Capture phase + stopPropagation so this runs
// before (and suppresses) the [data-detail-url] handler in base.js.
document.addEventListener('click', (e) => {
    if (!document.body.classList.contains('batch-mode')) return;
    const trigger = e.target.closest('[data-detail-url]');
    if (!trigger) return;
    e.preventDefault();
    e.stopPropagation();
    const box = trigger.closest('li')?.querySelector('input.batch-checkbox');
    if (box) {
        box.checked = !box.checked;
        box.dispatchEvent(new Event('change', { bubbles: true }));
    }
}, true);

document.addEventListener('click', (e) => {
    if (e.target.closest('#batch-toggle')) {
        const enabled = document.body.classList.toggle('batch-mode');
        if (!enabled) resetSelection();
        return;
    }
    if (e.target.closest('#batch-select-all')) {
        selectAll = !selectAll;
        excluded.clear();
        rowBoxes().forEach((box) => { box.checked = selectAll; });
        syncUi();
        return;
    }
    const actionBtn = e.target.closest('.batch-action-btn');
    if (actionBtn && !actionBtn.disabled) {
        submitBatchAction(actionBtn.dataset.batchUrl);
    }
});

document.addEventListener('change', (e) => {
    if (e.target.id === 'batch-select-page') {
        rowBoxes().forEach((box) => { box.checked = e.target.checked; });
        if (!e.target.checked) {
            selectAll = false;
            excluded.clear();
        }
        syncUi();
        return;
    }
    if (e.target.classList.contains('batch-checkbox')) {
        if (selectAll) {
            // Unticking after a select-all excludes the row (Gmail-style)
            // instead of dropping back to a per-id selection.
            if (e.target.checked) excluded.delete(e.target.value);
            else excluded.add(e.target.value);
        }
        syncUi();
    }
});

// A successful batch action on the dashboard fires refreshItems (HX-Trigger):
// leave batch mode, the refreshed list comes back unselected. Tag/area pages
// reload the whole page (HX-Refresh) so the mode resets by itself.
document.body.addEventListener('refreshItems', () => {
    document.body.classList.remove('batch-mode');
    resetSelection();
});

// The dashboard search swaps #search-results-container (OOB) on every query
// change: the checkboxes and bar are brand-new nodes, so drop the selection.
document.addEventListener('htmx:afterSettle', (e) => {
    if (e.target.id === 'search-results-container') resetSelection();
});

document.addEventListener('DOMContentLoaded', syncUi);
