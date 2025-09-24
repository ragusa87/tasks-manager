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