
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

        // Clearing the search also collapses the extra filters right away
        // (no waiting for the swap), back to the "See more" state.
        moreFiltersExpanded = false;
        applyFilterExpansion();
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

// "See more" toggle for the filter suggestions: status chips are always
// visible, the remaining categories live in #filter-more. htmx re-swaps
// #filter_container (OOB) on every search input, so the expanded state is
// held here and re-applied after each swap. Until the user toggles it
// (null), the section auto-expands whenever it holds an active chip, so an
// applied filter is never invisible.
let moreFiltersExpanded = null;

function applyFilterExpansion() {
    const more = document.getElementById('filter-more');
    const toggle = document.getElementById('filter-more-toggle');
    if (!more || !toggle) return;
    const expanded = moreFiltersExpanded ?? Boolean(more.querySelector('.filter-suggestion-active'));
    more.classList.toggle('hidden', !expanded);
    toggle.setAttribute('aria-expanded', String(expanded));
    toggle.querySelector('[data-label]').textContent = expanded ? 'See less' : 'See more';
    const chevron = toggle.querySelector('svg');
    if (chevron) chevron.classList.toggle('rotate-180', expanded);
}

document.addEventListener('click', function(e) {
    if (!e.target.closest('#filter-more-toggle')) return;
    moreFiltersExpanded = document.getElementById('filter-more').classList.contains('hidden');
    applyFilterExpansion();
});

document.addEventListener('DOMContentLoaded', applyFilterExpansion);
// afterSettle, not (oob)afterSwap: during the settle window htmx puts the old
// element's attributes on the swapped-in node and restores the server-rendered
// ones ~20ms later, which would overwrite a class set in an afterSwap handler.
document.addEventListener('htmx:afterSettle', function(e) {
    if (e.target.id === 'filter_container') applyFilterExpansion();
});
