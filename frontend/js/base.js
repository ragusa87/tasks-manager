import '../css/main.css';
import AirDatepicker from 'air-datepicker';
import 'air-datepicker/air-datepicker.css';
import localeEn from 'air-datepicker/locale/en';
import localeFr from 'air-datepicker/locale/fr';
import htmx from 'htmx.org';
import { initDocumentUpload, showToast } from './documents.js';
import { initAudioRecorders } from './audio-recorder.js';
import { initThemeToggle } from './theme.js';
import { getCsrfToken } from './csrf.js';
import { MODAL_SELECTOR } from './modal.js';
window.htmx = htmx

// Heavy custom elements (Milkdown/ProseMirror, rrule.js) are only needed
// inside the item-detail modal, so they are code-split out of the base bundle
// and imported the first time their tag shows up in the DOM. Once the module
// runs customElements.define(), existing tags upgrade in place.
const LAZY_ELEMENTS = {
    'markdown-editor': () => import('./markdown-editor.js'),
    'rrule-picker': () => import('./rrule-picker.js'),
};
function loadLazyElements() {
    Object.entries(LAZY_ELEMENTS).forEach(([tag, load]) => {
        if (!customElements.get(tag) && document.querySelector(tag)) {
            load().catch((error) => console.error(`Failed to load <${tag}>:`, error));
        }
    });
}
htmx.config.responseHandling = [
    {code: "204", swap: false},
    {code: "[23]..", swap: true},
    {code: "[5]..", swap: false, error: true},
    {code: "[4]..", swap: true, error: false},
    {code: "...", swap: false}
]


document.body.addEventListener('htmx:configRequest', function(evt) {
    var csrfToken = getCsrfToken();
    if (csrfToken) {
        evt.detail.headers['X-CSRFToken'] = csrfToken;
    }
});

// Recover from a proxy auth lapse that would otherwise kill a background
// request silently. Global on purpose: htmx events bubble to document.body, so
// this covers every htmx request in the app (deletes, transitions, modal
// saves, batch actions, ...), not just one page.
//
// The Keycloak plugin in front of the app (Gwojda/keycloakopenid) has no way to
// answer an XHR with 401 -- when AUTH_TOKEN has expired it always 302s to the
// Keycloak login on another origin, and the browser blocks that cross-origin
// redirect for an XHR (CORS). htmx surfaces this as htmx:sendError (a
// network-level failure, distinct from htmx:responseError which carries a real
// HTTP status), so the action just fails with nothing on screen. A full-page
// reload *can* follow that same redirect as a top-level navigation and re-auth
// transparently while the Keycloak SSO session is still alive -- so recover by
// reloading. The sessionStorage guard stops this from looping when the real
// cause is the network being down or the server being unreachable.
var REAUTH_KEY = 'htmx-reauth-reload-at';
var REAUTH_WINDOW_MS = 20000;
document.body.addEventListener('htmx:afterOnLoad', function() {
    // A real response came back, so auth is fine again -- reset the guard.
    sessionStorage.removeItem(REAUTH_KEY);
});
document.body.addEventListener('htmx:sendError', function() {
    if (!navigator.onLine) {
        showToast('You appear to be offline — reconnect and try again.', 'error', 5000);
        return;
    }
    var now = Date.now();
    var last = Number(sessionStorage.getItem(REAUTH_KEY) || 0);
    if (now - last < REAUTH_WINDOW_MS) {
        // We just reloaded and the next request still failed: don't loop,
        // let the user retry by hand rather than reload endlessly.
        showToast('Could not reach the server. Reload the page to sign back in.', 'error', 8000);
        return;
    }
    sessionStorage.setItem(REAUTH_KEY, String(now));
    showToast('Session expired — reloading to sign you back in…', 'error', 4000);
    setTimeout(function() { window.location.reload(); }, 1200);
});

// Generic modal handling (item detail, @requires_form transition forms,
// batch previews) lives in modal.js — imported above, shared with batch.js.

// Refresh the item list after a modal action. Two triggers:
//  - a 200 swap of the #modal itself (item-detail save), and
//  - the `refreshItems` event fired by a successful transition (HX-Trigger).
// Guarded so it is a no-op on pages without the search box (e.g. stats).
function refreshItemList() {
    const searchInput = document.getElementById('search-input');
    if (searchInput) {
        searchInput.dispatchEvent(new Event('search'));
    }
}
document.addEventListener('htmx:afterSwap', function(evt) {
    if (evt.target.matches('#' + MODAL_SELECTOR) && evt.detail.xhr.status === 200) {
        refreshItemList();
    }
});
document.body.addEventListener('refreshItems', refreshItemList);

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
                        visual.classList.add('bg-accent/10', 'border-accent');
                        visual.classList.remove('border-line');
                    } else {
                        visual.classList.remove('bg-accent/10', 'border-accent');
                        visual.classList.add('border-line');
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
                        visual.classList.remove('bg-accent/10', 'border-accent');
                        visual.classList.add('border-line');
                    }
                }
            });

            // Check this radio and update visual
            input.checked = true;
            const visual = radioOption.querySelector('.custom-radio-visual');
            if (visual) {
                visual.classList.add('bg-accent/10', 'border-accent');
                visual.classList.remove('border-line');
            }

            // Trigger change event for any listening code
            input.dispatchEvent(new Event('change', { bubbles: true }));
        }
    }
});

// Clone an inert markup fragment rendered by base.html. Display identity
// (classes, icons) lives in the template; JS fills textContent and behavior.
function cloneTemplate(id) {
    const template = document.getElementById(id);
    if (!template || !template.content.firstElementChild) {
        console.warn(`Missing <template id="${id}"> in the page`);
        return null;
    }
    return template.content.firstElementChild.cloneNode(true);
}

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

        // Local mode: a real <select> carries the options (and the submitted
        // value) — filter it client-side instead of hitting the endpoint.
        // See LocalAutocompleteWidget / widgets/autocomplete_select.html.
        const select = container.querySelector('select.autocomplete-select');
        const isLocal = container.dataset.local === 'true' && !!select;
        let localOptions = [];
        if (isLocal) {
            // Progressive enhancement: swap the plain select for the filter input.
            input.classList.remove('hidden');
            select.classList.add('hidden');
            select.setAttribute('tabindex', '-1');
            // Ids stay strings in local mode (option values are strings), so
            // the === comparisons in showDropdown/removeItem are consistent.
            localOptions = Array.from(select.options)
                .filter(o => o.value !== '')
                .map(o => ({ id: o.value, text: o.text.trim() }));
            // Restore pre-selected option(s): the select itself carries the
            // state when the form re-renders (validation error, saved value).
            selectedItems = Array.from(select.selectedOptions)
                .filter(o => o.value !== '')
                .map(o => ({ id: o.value, text: o.text.trim() }));
            updateSelectedDisplay();  // chips; re-hides the input if picked
        }

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
                // Single-select: mirror the initial selection into the visible
                // input. Otherwise the field looks empty while the hidden
                // input still submits the stored id.
                if (!allowMultiple && selectedItems.length > 0) {
                    input.value = selectedItems[0].text;
                }
            } catch (e) {
                console.error('Error loading initial values:', e);
                selectedItems = [];
            }
        }

        // Input event handler
        input.addEventListener('input', function() {
            const query = this.value.trim();

            // Single-select: erasing the visible text clears the selection,
            // so an empty-looking field really submits an empty value.
            if (!allowMultiple && query === '' && selectedItems.length > 0) {
                selectedItems = [];
                updateHiddenInput();
            }

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
            if (isLocal) {
                const q = query.toLowerCase();
                showDropdown(localOptions.filter(o => o.text.toLowerCase().includes(q)), query);
                return;
            }

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
                const createItem = cloneTemplate('autocomplete-create-template');
                if (createItem) {
                    createItem.querySelector('[data-create-label]').textContent = `Create "${query}"`;
                    createItem.addEventListener('click', () => createNewTag(query));
                    dropdown.appendChild(createItem);
                }
            }

            results.forEach(item => {
                // Skip if already selected in multiple mode
                if (allowMultiple && selectedItems.some(selected => selected.id === item.id)) {
                    return;
                }

                const resultItem = cloneTemplate('autocomplete-result-template');
                if (!resultItem) return;
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
                // Without a badge container the input doubles as the display
                if (!selectedContainer) input.value = item.text;
            }
            hideDropdown();
        }

        function removeItem(itemId) {
            selectedItems = selectedItems.filter(item => item.id !== itemId);
            updateSelectedDisplay();
            updateHiddenInput();
            // Single-select: removing the chip means "pick something else" —
            // hand focus back to the (now visible) input, which reopens the list.
            if (!allowMultiple && selectedContainer) input.focus();
        }

        function updateSelectedDisplay() {
            if (!selectedContainer) return;

            selectedContainer.innerHTML = '';

            selectedItems.forEach(item => {
                const badge = cloneTemplate('autocomplete-badge-template');
                if (!badge) return;
                badge.querySelector('[data-badge-label]').textContent = item.text;
                badge.querySelector('button').addEventListener('click', (e) => {
                    // Removal detaches the badge, so if this click bubbled to
                    // the document-level close handler it would read as an
                    // outside click and immediately close the list removeItem
                    // just reopened.
                    e.stopPropagation();
                    removeItem(item.id);
                });
                selectedContainer.appendChild(badge);
            });

            // Single-select with a badge container: the chip IS the display
            // (remove it via its X to search again), so the search input only
            // shows while nothing is picked. Editing text back into the input
            // can then never disagree with the submitted value.
            if (!allowMultiple) {
                const hasSelection = selectedItems.length > 0;
                input.classList.toggle('hidden', hasSelection);
                if (hasSelection) input.value = '';
            }
        }

        function updateHiddenInput() {
            if (isLocal) {
                // The select is the submitted input — mirror the selection back.
                if (allowMultiple) {
                    const ids = new Set(selectedItems.map(item => item.id));
                    Array.from(select.options).forEach(o => { o.selected = ids.has(o.value); });
                } else {
                    select.value = selectedItems.length > 0 ? selectedItems[0].id : '';
                }
                return;
            }
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

    // Check if there are non-field errors (the alert-danger box rendered by
    // partials/item_form_detail.html)
    const hasNonFieldErrors = document.querySelector('.alert-danger') !== null;

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
    loadLazyElements();
    initializeAutocomplete();
    initializeAccordions();
    initializeDatePicker();
    initializeMobileMenu();
    initDocumentUpload();
    initAudioRecorders();
    initThemeToggle();
}
document.addEventListener('DOMContentLoaded', init);
document.addEventListener('htmx:afterSwap', init);
document.addEventListener('htmx:afterSettle', init);
document.addEventListener('htmx:load', init);
document.addEventListener('openmodal', init);
