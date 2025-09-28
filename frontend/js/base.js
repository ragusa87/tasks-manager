import htmx from 'htmx.org';
window.htmx = htmx
// Simple dropdown toggle functionality
function initializeDropdowns() {
    // Remove existing listeners to avoid duplicates
    document.querySelectorAll('[id^="options-menu-"]').forEach(function(button) {
        // Clone button to remove existing listeners
        const newButton = button.cloneNode(true);
        button.parentNode.replaceChild(newButton, button);
    });

    // Handle dropdown toggles
    document.querySelectorAll('[id^="options-menu-"]').forEach(function(button) {
        button.addEventListener('click', function(e) {
            e.preventDefault();
            e.stopPropagation();
            const dropdown = this.nextElementSibling;

            // Close other dropdowns
            document.querySelectorAll('.dropdown-menu').forEach(function(menu) {
                if (menu !== dropdown) {
                    menu.classList.add('hidden');
                }
            });

            // Check if dropdown is currently hidden to determine if we're opening it
            const isCurrentlyHidden = dropdown.classList.contains('hidden');

            // Toggle current dropdown
            dropdown.classList.toggle('hidden');

            // Position dropdown to avoid overflow (only when opening)
            if (isCurrentlyHidden) {
                const buttonRect = this.getBoundingClientRect();
                const viewportWidth = window.innerWidth;
                const viewportHeight = window.innerHeight;

                // Position dropdown relative to button
                dropdown.style.position = 'fixed';
                dropdown.style.top = (buttonRect.bottom + 8) + 'px';

                // Check if dropdown would go off-screen horizontally
                if (buttonRect.right - 192 < 0) {
                    // Position from left edge of button
                    dropdown.style.left = buttonRect.left + 'px';
                    dropdown.style.right = 'auto';
                } else {
                    // Position from right edge of button
                    dropdown.style.right = (viewportWidth - buttonRect.right) + 'px';
                    dropdown.style.left = 'auto';
                }

                // Check if dropdown would go off-screen vertically
                const dropdownHeight = dropdown.offsetHeight;

                if (buttonRect.bottom + dropdownHeight > viewportHeight) {
                    dropdown.style.top = (buttonRect.top - dropdownHeight - 8) + 'px';
                }
            }
        });
    });
}

// Initialize on page load
document.addEventListener('DOMContentLoaded', initializeDropdowns);

// Re-initialize when HTMX loads new content
document.addEventListener('htmx:afterSwap', initializeDropdowns);

// Close dropdowns when clicking outside
document.addEventListener('click', function(e) {
    if (!e.target.closest('[id^="options-menu-"]')) {
        document.querySelectorAll('.dropdown-menu').forEach(function(menu) {
            menu.classList.add('hidden');
        });
    }
});

// Custom radio button group functionality
function initializeCustomRadioGroups() {
    // Remove existing listeners to avoid duplicates
    document.querySelectorAll('.custom-radio-group').forEach(function(group) {
        const options = group.querySelectorAll('.custom-radio-option');
        options.forEach(function(option) {
            // Clone option to remove existing listeners
            const newOption = option.cloneNode(true);
            option.parentNode.replaceChild(newOption, option);
        });
    });

    // Initialize custom radio groups
    document.querySelectorAll('.custom-radio-group').forEach(function(group) {
        const options = group.querySelectorAll('.custom-radio-option');

        // Set initial selection state
        function updateSelection() {
            options.forEach(function(option) {
                const input = option.querySelector('input[type="radio"]');
                const visual = option.querySelector('.custom-radio-visual');

                if (input && visual) {
                    if (input.checked) {
                        visual.classList.add('bg-blue-50', 'border-blue-500');
                        visual.classList.remove('border-gray-300');
                    } else {
                        visual.classList.remove('bg-blue-50', 'border-blue-500');
                        visual.classList.add('border-gray-300');
                    }
                }
            });
        }

        // Handle clicks
        options.forEach(function(option) {
            option.addEventListener('click', function(e) {
                const input = this.querySelector('input[type="radio"]');
                if (input) {
                    input.checked = true;
                    updateSelection();
                }
            });
        });

        // Initial selection update
        updateSelection();
    });
}

// Initialize custom radio groups on page load
document.addEventListener('DOMContentLoaded', initializeCustomRadioGroups);

// Re-initialize when HTMX loads new content
document.addEventListener('htmx:afterSwap', initializeCustomRadioGroups);

// Autocomplete functionality
function initializeAutocomplete() {
    // Remove existing listeners to avoid duplicates
    document.querySelectorAll('.autocomplete-container').forEach(function(container) {
        const input = container.querySelector('.autocomplete-input');
        if (input) {
            // Clone input to remove existing listeners
            const newInput = input.cloneNode(true);
            input.parentNode.replaceChild(newInput, input);
        }
    });

    // Initialize autocomplete fields
    document.querySelectorAll('.autocomplete-container').forEach(function(container) {
        const input = container.querySelector('.autocomplete-input');
        const dropdown = container.querySelector('.autocomplete-dropdown');
        const selectedContainer = container.querySelector('.selected-items');
        const hiddenInput = container.querySelector('.autocomplete-hidden');
        const fieldType = container.dataset.fieldType;
        const allowMultiple = container.dataset.allowMultiple === 'true';
        const allowCreate = container.dataset.allowCreate === 'true';

        if (!input || !dropdown) return;

        let selectedItems = [];
        let searchTimeout;

        // Load initial selected items
        if (hiddenInput && hiddenInput.value && hiddenInput.value !== '') {
            try {
                // Check if we have preloaded data in the container
                const initialValues = container.dataset.initialValues;

                if (initialValues && initialValues.trim() !== '') {
                    // Parse format: "id1:text1,id2:text2"
                    selectedItems = initialValues.split(',').map(item => {
                        const [id, ...textParts] = item.split(':');
                        return {
                            id: parseInt(id.trim()),
                            text: textParts.join(':').trim() || `ID: ${id.trim()}`
                        };
                    });
                } else {
                    // Fallback: If no data-initial-values, just use IDs without text
                    console.warn('No initial values found for autocomplete field, items may show as IDs');
                    selectedItems = [];
                }

                updateSelectedDisplay();
            } catch (e) {
                console.error('Error loading initial values:', e);
                selectedItems = [];
            }
        }

        // Input event handler
        input.addEventListener('input', function() {
            const query = this.value.trim();

            clearTimeout(searchTimeout);
            searchTimeout = setTimeout(() => {
                    searchItems(query);
            }, 150);
        });

        // Focus handler
        input.addEventListener('focus', function() {
            const query = this.value.trim();
            searchItems(query); // Always search on focus, even with empty query
        });

        // Click outside to close
        document.addEventListener('click', function(e) {
            if (!container.contains(e.target)) {
                hideDropdown();
            }
        });

        function searchItems(query) {
            const url = `/api/autocomplete/${fieldType}/?q=${encodeURIComponent(query)}`;

            fetch(url)
                .then(response => {
                    if (!response.ok) {
                        throw new Error(`HTTP ${response.status}: ${response.statusText}`);
                    }
                    const contentType = response.headers.get('content-type');
                    if (!contentType || !contentType.includes('application/json')) {
                        return response.text().then(text => {
                            console.error('Non-JSON response:', text);
                            throw new Error('Server returned non-JSON response');
                        });
                    }
                    return response.json();
                })
                .then(data => {
                    if (data.error) {
                        console.error('API error:', data.error);
                        return;
                    }
                    showDropdown(data.results || [], query);
                })
                .catch(error => {
                    console.error('Autocomplete error:', error);
                    hideDropdown();
                });
        }

        function showDropdown(results, query) {
            dropdown.innerHTML = '';

            if (results.length === 0 && allowCreate && query) {
                // Show create option
                const createItem = document.createElement('div');
                createItem.className = 'px-3 py-2 cursor-pointer hover:bg-blue-50 border-b border-gray-100 text-blue-600';
                createItem.innerHTML = `
                    <div class="flex items-center space-x-2">
                        <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 6v6m0 0v6m0-6h6m-6 0H6"></path>
                        </svg>
                        <span>Create "${query}"</span>
                    </div>
                `;
                createItem.addEventListener('click', () => createNewTag(query));
                dropdown.appendChild(createItem);
            }

            results.forEach(item => {
                // Skip if already selected in multiple mode
                if (allowMultiple && selectedItems.some(selected => selected.id === item.id)) {
                    return;
                }

                const resultItem = document.createElement('div');
                resultItem.className = 'px-3 py-2 cursor-pointer hover:bg-gray-50 border-b border-gray-100 last:border-b-0';
                resultItem.textContent = item.text;
                resultItem.addEventListener('click', () => selectItem(item));
                dropdown.appendChild(resultItem);
            });

            dropdown.classList.remove('hidden');
        }

        function hideDropdown() {
            dropdown.classList.add('hidden');
        }

        function selectItem(item) {
            if (allowMultiple) {
                // Add to selected items if not already selected
                if (!selectedItems.some(selected => selected.id === item.id)) {
                    selectedItems.push(item);
                    updateSelectedDisplay();
                    updateHiddenInput();
                }
                input.value = '';
            } else {
                // Single selection
                selectedItems = [item];
                updateSelectedDisplay();
                updateHiddenInput();
                input.value = item.text;
            }
            hideDropdown();
        }

        function removeItem(itemId) {
            selectedItems = selectedItems.filter(item => item.id !== itemId);
            updateSelectedDisplay();
            updateHiddenInput();
        }

        function updateSelectedDisplay() {
            if (!selectedContainer) return;

            selectedContainer.innerHTML = '';

            if (allowMultiple) {
                selectedItems.forEach(item => {
                    const badge = document.createElement('span');
                    badge.className = 'inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-blue-100 text-blue-800';
                    badge.innerHTML = `
                        ${item.text}
                        <button type="button" class="ml-1 text-blue-600 hover:text-blue-800">
                            <svg class="w-3 h-3" fill="currentColor" viewBox="0 0 20 20">
                                <path fill-rule="evenodd" d="M4.293 4.293a1 1 0 011.414 0L10 8.586l4.293-4.293a1 1 0 111.414 1.414L11.414 10l4.293 4.293a1 1 0 01-1.414 1.414L10 11.414l-4.293 4.293a1 1 0 01-1.414-1.414L8.586 10 4.293 5.707a1 1 0 010-1.414z" clip-rule="evenodd"></path>
                            </svg>
                        </button>
                    `;
                    badge.querySelector('button').addEventListener('click', () => removeItem(item.id));
                    selectedContainer.appendChild(badge);
                });
            }
        }

        function updateHiddenInput() {
            if (hiddenInput) {
                if (allowMultiple) {
                    hiddenInput.value = selectedItems.map(item => item.id).join(',');
                } else {
                    hiddenInput.value = selectedItems.length > 0 ? selectedItems[0].id : '';
                }
            }
        }


        function createNewTag(name) {
            if (!allowCreate) return;

            fetch(`/api/create/${fieldType}/`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({ name: name })
            })
            .then(response => response.json())
            .then(data => {
                if (data.error) {
                    console.error(`Error creating ${fieldType}:`, data.error);
                } else {
                    selectItem(data);
                }
            })
            .catch(error => {
                console.error(`Error creating ${fieldType}:`, error);
            });
        }
    });
}

// Initialize autocomplete on page load
document.addEventListener('DOMContentLoaded', initializeAutocomplete);

// Re-initialize when HTMX loads new content
document.addEventListener('htmx:afterSwap', initializeAutocomplete);