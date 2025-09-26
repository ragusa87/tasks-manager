// Update last updated timestamp
document.addEventListener('htmx:afterSwap', function(evt) {
    const lastUpdated = document.getElementById('last-updated');
    if (lastUpdated) {
        const now = new Date();
        lastUpdated.textContent = now.toLocaleTimeString('en-US', {
            hour12: false,
            hour: '2-digit',
            minute: '2-digit'
        });
    }
});

// Global refresh function
function refreshDashboard() {
    htmx.trigger(document.body, 'refresh-dashboard');
}

// Connection status indicator
window.isOnline = navigator.onLine;
document.addEventListener('htmx:responseError', function(evt) {
    if (!navigator.onLine) {
        // Show offline indicator
        const offlineIndicator = document.createElement('div');
        offlineIndicator.className = 'fixed top-4 right-4 bg-red-500 text-white px-4 py-2 rounded-lg shadow-lg z-50';
        offlineIndicator.textContent = 'Connection lost - Updates paused';
        offlineIndicator.id = 'offline-indicator';
        document.body.appendChild(offlineIndicator);
    }
});

window.addEventListener('online', function() {
    window.isOnline = true;
    const indicator = document.getElementById('offline-indicator');
    if (indicator) {
        indicator.remove();
    }
    // Refresh dashboard when coming back online
    refreshDashboard();
});

window.addEventListener('offline', function() {
    window.isOnline = false;
});

// Clickable data attributes for filtering
document.addEventListener('click', function(e) {
    const target = e.target.closest('[data-project], [data-area], [data-context], [data-energy], [data-tag]');
    if (!target) return;

    e.preventDefault();
    e.stopPropagation();

    let filter = '';

    if (target.hasAttribute('data-project')) {
        filter = `parent:"${target.getAttribute('data-project')}"`;
        removeFilter("in:project")
    } else if (target.hasAttribute('data-area')) {
        filter = `area:"${target.getAttribute('data-area')}"`;
    } else if (target.hasAttribute('data-context')) {
        filter = `context:"${target.getAttribute('data-context')}"`;
    } else if (target.hasAttribute('data-energy')) {
        filter = `energy:"${target.getAttribute('data-energy')}"`;
    } else if (target.hasAttribute('data-tag')) {
        filter = `tag:"${target.getAttribute('data-tag')}"`;
    }

    if (filter) {
        // Find the search input
        const searchInput = document.getElementById('search-input');
        if (searchInput) {
            addFilter(filter);
        }
    }
});

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

        updateFilterStates();
        updateUrl('');
    });
})

function isFilterActive(filter) {
    const searchInput = document.getElementById('search-input');
    const currentValue = searchInput.value.trim();

    // Escape special regex characters
    const escapedFilter = filter.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');

    // For quoted filters (area/context), use more flexible matching
    if (filter.includes('"')) {
        // Match the filter surrounded by word boundaries or spaces
        const regex = new RegExp('(^|\\s)' + escapedFilter + '(\\s|$)');
        return regex.test(currentValue);
    } else {
        // Use word boundary for simple filters
        const regex = new RegExp('\\b' + escapedFilter + '\\b');
        return regex.test(currentValue);
    }
}

function addFilter(filter) {
    const searchInput = document.getElementById('search-input');
    const currentValue = searchInput.value.trim();

    // Check if filter already exists - if so, remove it
    if (isFilterActive(filter)) {
        removeFilter(filter);
        return;
    }

    // Add the filter with a space if there's existing content
    const newValue = currentValue ? `${currentValue} ${filter}` : filter;
    searchInput.value = newValue;

    // Trigger the search
    htmx.trigger(searchInput, 'input');

    // Update filter button states and URL
    updateFilterStates();
    updateUrl(newValue);

    // Focus back on the input
    searchInput.focus();
}

function removeFilter(filter) {
    const searchInput = document.getElementById('search-input');
    const currentValue = searchInput.value.trim();

    // Escape special regex characters
    const escapedFilter = filter.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');

    // Remove the filter using appropriate regex based on whether it's quoted
    let regex;
    if (filter.includes('"')) {
        // For quoted filters, match with flexible spacing
        regex = new RegExp('\\s*(^|\\s)' + escapedFilter + '(\\s|$)\\s*', 'g');
    } else {
        // Use word boundary for simple filters
        regex = new RegExp('\\s*\\b' + escapedFilter + '\\b\\s*', 'g');
    }

    const newValue = currentValue.replace(regex, ' ').replace(/\s+/g, ' ').trim();

    searchInput.value = newValue;

    // Trigger the search
    htmx.trigger(searchInput, 'input');

    // Update filter button states and URL
    updateFilterStates();
    updateUrl(newValue);

    // Focus back on the input
    searchInput.focus();
}

function updateFilterStates() {
    document.querySelectorAll('.filter-suggestion').forEach(function(button) {
        const filter = button.getAttribute('data-filter');
        const isActive = isFilterActive(filter);
        const colorCategory = button.getAttribute('data-color') || 'gray';

        // Toggle between inactive and active states
        // Inactive state classes
        button.classList.toggle(`bg-${colorCategory}-100`, !isActive);
        button.classList.toggle(`text-${colorCategory}-700`, !isActive);
        button.classList.toggle(`hover:bg-${colorCategory}-200`, !isActive);

        // Active state classes
        button.classList.toggle(`bg-${colorCategory}-600`, isActive);
        button.classList.toggle('text-white', isActive);
        button.classList.toggle(`hover:bg-${colorCategory}-700`, isActive);
        button.classList.toggle('ring-2', isActive);
        button.classList.toggle(`ring-${colorCategory}-300`, isActive);
    });
}

function initializeFilterSuggestions() {
    document.addEventListener('click', function(e) {
        const target = e.target.closest('.filter-suggestion');
        if (!target) return;
        const filter = target.getAttribute('data-filter');
        if (!filter) return;
        addFilter(filter);
    })
}

// Add event listeners for filter suggestions
document.addEventListener('DOMContentLoaded', function() {
    initializeFilterSuggestions();

    // Initial state update
    updateFilterStates();

    // Trigger initial search if there's a query in the input
    const searchInput = document.getElementById('search-input');
    if (searchInput && searchInput.value.trim()) {
        htmx.trigger(searchInput, 'input');
    }
});

// Update filter states and URL when user types
document.getElementById('search-input').addEventListener('input', function() {
    updateFilterStates();
    updateUrl(this.value);
});

// Re-initialize filter suggestions when HTMX loads new content
document.addEventListener('htmx:afterSwap', function() {
    updateFilterStates()
});

// Initialize stats filter buttons
function initializeStatsFilters() {
    document.querySelectorAll('.stats-filter-btn').forEach(function(button) {
        // Remove existing listeners to avoid duplicates
        const newButton = button.cloneNode(true);
        button.parentNode.replaceChild(newButton, button);

        // Add new listener
        newButton.addEventListener('click', function() {
           const filter = this.getAttribute('data-filter');
           setSearchFilter(filter);
        });
    });
}

function setSearchFilter(filter) {
    const searchInput = document.getElementById('search-input');
    if (!searchInput) return;

    console.log("Set search filter",filter)

    // Replace the entire search query with this filter
    searchInput.value = filter;

    // Trigger the search
    htmx.trigger(searchInput, 'input');

    // Update filter button states if the function exists
    updateFilterStates();

    // Focus on the search input
    searchInput.focus();

    // Scroll to search results if they exist
    const searchContainer = document.getElementById('search-results-container');
    if (searchContainer) {
        searchContainer.scrollIntoView({ behavior: 'smooth', block: 'start' });
    }
}

// Initialize on page load
document.addEventListener('DOMContentLoaded', function() {
    initializeStatsFilters();
});

// Re-initialize when HTMX loads new content
document.addEventListener('htmx:afterSwap', function(evt) {
    if (evt.target.matches('[hx-get*="dashboard_stats"]')) {
        initializeStatsFilters();
    }
});

// Modal functionality for item details
function openItemModal(url) {
    console.log("open modal", url);

    function closeItemModal() {
        const modal = document.getElementById('item-detail-modal');
        if (modal) {
            modal.style.display = 'none';
            modal.remove();
        }
    }

    fetch(url, {
          headers: {
            'HX-Request': 'true',
            'Referer': location.href
          }
    })
        .then(response => response.text())
        .then(html => {
            // Remove existing modal if any
            const existingModal = document.getElementById('item-detail-modal');
            if (existingModal) {
                existingModal.remove();
            }

            // Add new modal to body
            document.body.insertAdjacentHTML('beforeend', html);

            // Show modal
            const modal = document.getElementById('item-detail-modal');
            modal.style.display = 'block';

            // Process HTMX attributes on the new modal content
            htmx.process(modal);

            // Add event listeners for closing
            const closeButtons = modal.querySelectorAll('#close-modal, #close-modal-btn');
            closeButtons.forEach(button => {
                button.addEventListener('click', closeItemModal);
            });

            // Close on outside click
            modal.addEventListener('click', function(e) {
                if (e.target === modal) {
                    closeItemModal();
                }
            });

            // Handle HTMX events
            modal.addEventListener('htmx:beforeSwap', function(e) {
                console.log('HTMX beforeSwap:', e.detail);
            });

            modal.addEventListener('htmx:afterSwap', function(e) {
                console.log('HTMX afterSwap:', e.detail);

                // Re-process HTMX on the swapped content
                htmx.process(modal);

                // Re-attach close button listeners after swap
                const newCloseButtons = modal.querySelectorAll('#close-modal, #close-modal-btn');
                newCloseButtons.forEach(button => {
                    button.removeEventListener('click', closeItemModal); // Remove old listeners
                    button.addEventListener('click', closeItemModal);
                });

                // Check if form was successfully submitted (no form in response means success)
                if (e.detail.xhr.status === 200 && modal.querySelector('form')) {
                    // Success - close modal and refresh
                    setTimeout(() => {
                        closeItemModal();
                        console.log("Reloading page to reflect changes");
                        window.location.reload();
                    }, 500);
                }
            });

            modal.addEventListener('htmx:responseError', function(e) {
                console.error('HTMX response error:', e.detail);
            });

            modal.addEventListener('htmx:sendError', function(e) {
                console.error('HTMX send error:', e.detail);
            });

            // Handle form submission manually if HTMX doesn't work
            const form = modal.querySelector('form');
            if (form) {
                form.addEventListener('submit', function(e) {
                    console.log('Form submit event triggered');
                    // Let HTMX handle it, but log for debugging
                });
            }

            // Close on escape key
            document.addEventListener('keydown', function escapeHandler(e) {
                if (e.key === 'Escape') {
                    closeItemModal();
                    document.removeEventListener('keydown', escapeHandler);
                }
            });

        })
        .catch(error => {
            console.error('Error loading item details:', error);
        });
}

// Add click handler for items with data-detail-url attribute
document.addEventListener('click', function(e) {
    const itemElement = e.target.closest('[data-detail-url]');
    if (!itemElement) {
        return
    }
    e.preventDefault();
    const url = itemElement.getAttribute('data-detail-url');
    openItemModal(url);
});