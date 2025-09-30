
// URL management
function updateUrl(query) {
    const url = new URL(window.location);
    if (query && query.trim()) {
        url.searchParams.set('q', query.trim());
    } else {
        url.searchParams.delete('q');
    }
    history.replaceState(null, '', url);
}

document.addEventListener('DOMContentLoaded', function() {
    document.addEventListener('click', (e) => {
        const target = e.target.closest('#clear-search');
        if (!target) return;

        e.preventDefault()
        const searchInput = document.getElementById('search-input');
        searchInput.value = '';
        htmx.trigger(searchInput, 'input');

        updateUrl('');
    });
})

// Add event listeners for filters
document.addEventListener('click', function(e) {
    const target = e.target.closest('[data-filter]');
    if (!target) return;

    const value = target.getAttribute('data-next-query') || target.getAttribute('data-filter')
    if (!value) return;

    const searchInput = document.getElementById('search-input');
    searchInput.value = value;
    htmx.trigger(searchInput, 'input');
    searchInput.focus();
});

// Update URL when user types
document.getElementById('search-input').addEventListener('input', function() {
    updateUrl(this.value);
});

const modal_selector = "modal"
const get_modal = () => document.getElementById(modal_selector);
function closeItemModal() {
    const modal = get_modal();
    if (modal) {
        console.log("Closing modal");
        modal.style.display = 'none';
        modal.remove();
    }
}

let modalIsOpen = () => get_modal() && get_modal().style.display!=='hidden';
document.addEventListener("click", function(e) {
    if (modalIsOpen() && (e.target === get_modal() || e.target.id === 'close-modal' || e.target.id === 'close-modal-btn')) {
        closeItemModal();
    }
})
// Close on escape key
document.addEventListener('keydown', function escapeHandler(e) {
    if (e.key === 'Escape') {
        closeItemModal();
    }
});
// Modal functionality for item details
function openItemModal(url) {
    console.log("open modal", url, document.querySelector('#modal-container'));
    fetch(url,{
          headers: {
            'HX-Request': 'true',
          }
    })
    .then(response => response.text())
    .then(html => {
        document.querySelector('#modal-container').innerHTML = html;
        const modal = get_modal()
        if(modal) {
            modal.style.display = 'block';
            htmx.process(modal);
            document.dispatchEvent(new CustomEvent("openmodal"));
        }
    }).catch((error) => {
        console.error('Modal request failed:', error);
    });
}
// Open modal via [data-detail-url]
document.addEventListener('click', function(e) {
    const itemElement = e.target.closest('[data-detail-url]');
    if (!itemElement) {
        return
    }
    e.preventDefault();
    const url = itemElement.getAttribute('data-detail-url');
    openItemModal(url);
});

// Refresh the dashboard after modal actions
document.addEventListener('htmx:afterSwap', function(evt) {
    if (evt.target.matches("#" + modal_selector) && evt.detail.xhr.status === 200) {
        document.getElementById('search-input').dispatchEvent(new Event('search'));
    }
});
