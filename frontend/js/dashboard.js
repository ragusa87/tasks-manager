
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
