import '../css/main.css';
import AirDatepicker from 'air-datepicker';
import 'air-datepicker/air-datepicker.css';
import localeEn from 'air-datepicker/locale/en';
import localeFr from 'air-datepicker/locale/fr';
import htmx from 'htmx.org';
window.htmx = htmx
htmx.config.responseHandling = [
    {code: "204", swap: false},
    {code: "[23]..", swap: true},
    {code: "[5]..", swap: false, error: true},
    {code: "[4]..", swap: true, error: false},
    {code: "...", swap: false}
]

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
    // Initialize custom radio groups
    document.querySelectorAll('.custom-radio-group').forEach(function(group) {
        // Skip if already initialized to avoid duplicates
        if (group.hasAttribute('data-radio-initialized')) {
            return;
        }
        group.setAttribute('data-radio-initialized', 'true');

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

        // Also listen for direct radio button changes
        options.forEach(function(option) {
            const input = option.querySelector('input[type="radio"]');
            if (input) {
                input.addEventListener('change', updateSelection);
            }
        });

        // Initial selection update
        updateSelection();
    });
}

// Initialize custom radio groups on page load
document.addEventListener('DOMContentLoaded', initializeCustomRadioGroups);

// Re-initialize when HTMX loads new content
document.addEventListener('htmx:afterSwap', initializeCustomRadioGroups);

// Also initialize when content is settled (for modals and complex updates)
document.addEventListener('htmx:afterSettle', initializeCustomRadioGroups);

// Initialize when any new content is loaded
document.addEventListener('htmx:load', initializeCustomRadioGroups);

// Event delegation for radio groups (works with htmx-loaded content)
document.addEventListener('click', function(e) {
    // Check if clicked element is a custom radio option
    const radioOption = e.target.closest('.custom-radio-option');
    if (radioOption && radioOption.closest('.custom-radio-group')) {
        e.preventDefault();
        e.stopPropagation();

        const input = radioOption.querySelector('input[type="radio"]');
        if (input) {
            // Uncheck all radios in the same group first
            const groupName = input.name;
            document.querySelectorAll(`input[name="${groupName}"]`).forEach(function(radio) {
                radio.checked = false;
                const parentOption = radio.closest('.custom-radio-option');
                if (parentOption) {
                    const visual = parentOption.querySelector('.custom-radio-visual');
                    if (visual) {
                        visual.classList.remove('bg-blue-50', 'border-blue-500');
                        visual.classList.add('border-gray-300');
                    }
                }
            });

            // Check this radio and update visual
            input.checked = true;
            const visual = radioOption.querySelector('.custom-radio-visual');
            if (visual) {
                visual.classList.add('bg-blue-50', 'border-blue-500');
                visual.classList.remove('border-gray-300');
            }

            // Trigger change event for any listening code
            input.dispatchEvent(new Event('change', { bubbles: true }));
        }
    }
});

// Autocomplete functionality
function initializeAutocomplete() {
    console.log("Initializing autocomplete fields");
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
            const url = `/autocomplete/search/${fieldType}/?q=${encodeURIComponent(query)}`;

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

            fetch(`/autocomplete/create/${fieldType}/`, {
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



// Accordion functionality
function initializeAccordions() {
    console.log("Initializing accordions");

    // Remove existing listeners to avoid duplicates
    document.querySelectorAll('.accordion-header').forEach(function(header) {
        const newHeader = header.cloneNode(true);
        header.parentNode.replaceChild(newHeader, header);
    });

    // Initialize accordion headers
    document.querySelectorAll('.accordion-header').forEach(function(header) {
        header.addEventListener('click', function(e) {
            e.preventDefault();
            e.stopPropagation();

            const accordionItem = this.closest('.accordion-item');
            const content = accordionItem.querySelector('.accordion-content');
            const icon = this.querySelector('.accordion-icon');

            // Toggle accordion
            const isOpen = !content.classList.contains('hidden');

            if (isOpen) {
                // Close
                content.classList.add('hidden');
                icon.classList.remove('rotate-180');
            } else {
                // Open
                content.classList.remove('hidden');
                icon.classList.add('rotate-180');
            }
        });
    });

    // Check if there are non-field errors
    const hasNonFieldErrors = document.querySelector('.rounded-md.bg-red-50') !== null;

    // Auto-open accordions with errors or on modal open
    document.querySelectorAll('.accordion-item').forEach(function(item) {
        const hasErrors = item.dataset.hasErrors === 'true';
        const content = item.querySelector('.accordion-content');
        const icon = item.querySelector('.accordion-icon');

        if (hasErrors || hasNonFieldErrors) {
            // Open if has errors or if there are non-field errors
            content.classList.remove('hidden');
            if (icon) {
                icon.classList.add('rotate-180');
            }
        } else {
            // Close by default
            content.classList.add('hidden');
            if (icon) {
                icon.classList.remove('rotate-180');
            }
        }
    });
}

function initializeDatePicker(){
    const elements = document.querySelectorAll("input[data-airdatepicker]")
    elements.forEach(el => {
        if (typeof el._airDatepicker != "undefined") {
            el._airDatepicker.destroy();
        }
        el.type = 'INPUT';
        const config = JSON.parse(el.getAttribute('data-airdatepicker'))
        const map = {'en': localeEn, 'fr': localeFr}
        const desired_locale = config['locale'] || 'en'
        config['locale'] = map[desired_locale] || localeEn
        new AirDatepicker(el,config);
    })
}

// Mobile menu functionality
function initializeMobileMenu() {
    const menuButton = document.getElementById('mobile-menu-button');
    const mobileMenu = document.getElementById('mobile-menu');

    if (menuButton && mobileMenu) {
        // Remove existing listener by cloning
        const newMenuButton = menuButton.cloneNode(true);
        menuButton.parentNode.replaceChild(newMenuButton, menuButton);

        // Add click listener for main menu toggle
        newMenuButton.addEventListener('click', function() {
            const isExpanded = this.getAttribute('aria-expanded') === 'true';
            this.setAttribute('aria-expanded', !isExpanded);
            mobileMenu.classList.toggle('hidden');

            // Rotate the hamburger icon
            const svg = this.querySelector('svg');
            if (svg) {
                svg.classList.toggle('rotate-90');
            }
        });
    }

    // Handle mobile dropdown triggers
    document.querySelectorAll('.mobile-dropdown-trigger').forEach(trigger => {
        // Clone to remove existing listeners
        const newTrigger = trigger.cloneNode(true);
        trigger.parentNode.replaceChild(newTrigger, trigger);

        newTrigger.addEventListener('click', function() {
            const content = this.nextElementSibling;
            if (content && content.classList.contains('mobile-dropdown-content')) {
                content.classList.toggle('hidden');

                // Rotate chevron icon
                const svg = this.querySelector('svg');
                if (svg) {
                    svg.classList.toggle('rotate-180');
                }
            }
        });
    });
}

// Initialize on page load
const init = () => {
    initializeAutocomplete();
    initializeAccordions();
    initializeDatePicker();
    initializeMobileMenu();
}
document.addEventListener('DOMContentLoaded', init);
document.addEventListener('htmx:afterSwap', init);
document.addEventListener('htmx:afterSettle', init);
document.addEventListener('htmx:load', init);
document.addEventListener('openmodal', init);
