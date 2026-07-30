import htmx from 'htmx.org';

// ---------------------------------------------------------------------------
// Generic modal handling (item detail, @requires_form transition forms and
// batch-action previews). The modal is loaded into #modal-container (see
// base.html). Shared by the base and batch bundles: the return-focus state
// below must live in exactly one module so closing a modal restores focus
// regardless of which bundle opened it.
// ---------------------------------------------------------------------------
export const MODAL_SELECTOR = 'modal';
const getModal = () => document.getElementById(MODAL_SELECTOR);

// Element that had focus before the modal opened, restored on close so
// keyboard/screen-reader users don't lose their place in the page.
let modalReturnFocus = null;

const FOCUSABLE = 'a[href], button:not([disabled]), input:not([disabled]):not([type="hidden"]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])';

function focusModal(modal) {
    if (document.activeElement && !modal.contains(document.activeElement)) {
        modalReturnFocus = document.activeElement;
    }
    const target = modal.querySelector('[autofocus]') || modal.querySelector(FOCUSABLE) || modal;
    target.focus();
}

// Inject rendered modal HTML into #modal-container and open it (htmx wiring,
// openmodal event, focus capture). Returns the modal element, or null when
// the page has no container. Close button, Escape, overlay and focus restore
// are handled by the listeners below.
export function showModal(html) {
    const container = document.querySelector('#modal-container');
    if (!container) return null;
    container.innerHTML = html;
    const modal = getModal();
    if (modal) {
        modal.style.display = 'block';
        htmx.process(modal);
        document.dispatchEvent(new CustomEvent('openmodal'));
        focusModal(modal);
    }
    return modal;
}

function closeItemModal(options) {
    const modal = getModal();
    const wasOpen = Boolean(modal);
    if (modal) {
        modal.style.display = 'none';
        modal.remove();
    }
    if (modalReturnFocus) {
        if (modalReturnFocus.isConnected) {
            modalReturnFocus.focus();
        }
        modalReturnFocus = null;
    }
    // Drop the /item/<id>/detail/ history entry pushed on open — unless the
    // close IS the browser's back navigation (popstate), which already did.
    const fromHistory = options && options.fromHistory;
    if (wasOpen && !fromHistory && history.state && history.state.itemModal) {
        history.back();
    }
}

const modalIsOpen = () => {
    const modal = getModal();
    return modal && modal.style.display !== 'none';
};

// Close on overlay / close-button click, or Escape.
document.addEventListener('click', function(e) {
    if (modalIsOpen() && (e.target === getModal() || e.target.id === 'close-modal' || e.target.id === 'close-modal-btn')) {
        closeItemModal();
    }
});
document.addEventListener('keydown', function(e) {
    if (e.key === 'Escape') {
        closeItemModal();
        return;
    }
    // Keep Tab cycling inside the open modal (focus trap).
    if (e.key === 'Tab' && modalIsOpen()) {
        const modal = getModal();
        const focusable = Array.from(modal.querySelectorAll(FOCUSABLE))
            .filter(el => el.offsetParent !== null);
        if (focusable.length === 0) return;
        const first = focusable[0];
        const last = focusable[focusable.length - 1];
        if (e.shiftKey && (document.activeElement === first || !modal.contains(document.activeElement))) {
            e.preventDefault();
            last.focus();
        } else if (!e.shiftKey && (document.activeElement === last || !modal.contains(document.activeElement))) {
            e.preventDefault();
            first.focus();
        }
    }
});

// Open the item-detail modal via [data-detail-url] (fetch + inject). The
// item URL is pushed onto the history so the modal is reflected in the
// address bar; closing it (button, Escape, overlay or the browser's back
// button) restores the previous URL.
function openItemModal(url, options) {
    fetch(url, { headers: { 'HX-Request': 'true' } })
        .then(response => {
            if (!response.ok) {
                throw new Error(`HTTP ${response.status} loading ${url}`);
            }
            return response.text();
        })
        .then(html => {
            const modal = showModal(html);
            if (modal && !(options && options.skipHistory)) {
                history.pushState({ itemModal: true }, '', url);
            }
        })
        .catch((error) => console.error('Modal request failed:', error));
}

// Back closes the modal; forward onto a pushed item entry reopens it.
window.addEventListener('popstate', function(e) {
    const onItemEntry = e.state && e.state.itemModal;
    if (modalIsOpen() && !onItemEntry) {
        closeItemModal({ fromHistory: true });
    } else if (!modalIsOpen() && onItemEntry) {
        openItemModal(location.pathname, { skipHistory: true });
    }
});

// Modals injected by HTMX itself (delete confirmation, transition forms swap
// into #modal-container) go through afterSwap, not showModal, so hook
// focus handling there too.
document.addEventListener('htmx:afterSwap', function(evt) {
    if (evt.target.id === 'modal-container' && modalIsOpen()) {
        focusModal(getModal());
    }
});
document.addEventListener('click', function(e) {
    const itemElement = e.target.closest('[data-detail-url]');
    if (!itemElement) return;
    e.preventDefault();
    const url = itemElement.getAttribute('data-detail-url');
    // Below the sm breakpoint the modal is cramped: navigate to the same URL
    // instead — the non-HTMX branch of ItemDetailView renders it as a full
    // edit page (items/detail.html).
    if (window.matchMedia('(max-width: 639px)').matches) {
        window.location.assign(url);
        return;
    }
    openItemModal(url);
});
