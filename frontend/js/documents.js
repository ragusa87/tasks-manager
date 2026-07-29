export function initDocumentUpload() {
    initFileInputs();
    initDropzones();
    initDeleteButtons();
    initAudioPreviews();
    initAttachmentPaste();
}

// Files pasted into a <markdown-editor> become attachments, exactly like a
// dropzone drop: the editor emits a cancelable 'markdown-editor:attach'
// event, and we claim it whenever the surrounding form has a document
// dropzone (i.e. the item is saved and has an upload URL). Unclaimed pastes
// fall back to the editor's default behavior.
function initAttachmentPaste() {
    if (document.body.dataset.attachmentPasteInit) return;
    document.body.dataset.attachmentPasteInit = 'true';

    document.body.addEventListener('markdown-editor:attach', function(e) {
        var form = e.target.closest('form');
        var zone = form ? form.querySelector('.document-dropzone[data-upload-url]') : null;
        if (!zone) return;

        e.preventDefault();
        openDocumentsAccordion(zone);
        uploadFiles(zone.dataset.itemId, zone.dataset.uploadUrl, e.detail.files, e.detail.done);
    });
}

// Reveal the Documents accordion so the pasted file's progress and result
// are visible (same open mechanics as base.js initializeAccordions).
function openDocumentsAccordion(zone) {
    var item = zone.closest('.accordion-item');
    if (!item) return;
    var content = item.querySelector('.accordion-content');
    var icon = item.querySelector('.accordion-icon');
    if (content) content.classList.remove('hidden');
    if (icon) icon.classList.add('rotate-180');
}

function initDropzones() {
    document.querySelectorAll('.document-dropzone:not([data-initialized])').forEach(function(zone) {
        zone.setAttribute('data-initialized', 'true');
        var itemId = zone.dataset.itemId;
        var uploadUrl = zone.dataset.uploadUrl;
        if (!itemId || !uploadUrl) return;

        zone.addEventListener('dragover', function(e) {
            e.preventDefault();
            e.stopPropagation();
            zone.classList.add('border-accent', 'bg-accent/10', 'text-accent');
        });

        zone.addEventListener('dragleave', function(e) {
            e.preventDefault();
            e.stopPropagation();
            zone.classList.remove('border-accent', 'bg-accent/10', 'text-accent');
        });

        zone.addEventListener('drop', function(e) {
            e.preventDefault();
            e.stopPropagation();
            zone.classList.remove('border-accent', 'bg-accent/10', 'text-accent');
            var files = e.dataTransfer.files;
            if (!files || files.length === 0) return;
            uploadFiles(itemId, uploadUrl, files);
        });
    });
}

function initFileInputs() {
    document.querySelectorAll('.document-file-input:not([data-initialized])').forEach(function(input) {
        input.setAttribute('data-initialized', 'true');
        input.addEventListener('change', handleFileSelect);
    });
}

function initDeleteButtons() {
    document.querySelectorAll('.delete-doc-btn:not([data-initialized])').forEach(function(button) {
        button.setAttribute('data-initialized', 'true');
        button.addEventListener('click', handleDeleteClick);
    });
}

// In-browser preview of audio attachments: the play button expands the row's
// native <audio controls> element and starts playback; clicking again
// collapses and pauses it. The src is only set on first play (the element is
// preload="none") so listing documents never fetches audio.
var openAudioPreview = null; // one playing preview at a time

function initAudioPreviews() {
    document.querySelectorAll('.audio-preview-btn:not([data-initialized])').forEach(function(button) {
        button.setAttribute('data-initialized', 'true');
        button.addEventListener('click', handleAudioPreviewClick);
    });
}

function handleAudioPreviewClick(e) {
    var button = e.currentTarget;
    var row = button.closest('[data-document-id]');
    var audio = row ? row.querySelector('.audio-preview') : null;
    if (!audio) return;

    if (openAudioPreview && openAudioPreview.audio !== audio) {
        setAudioPreviewOpen(openAudioPreview.button, openAudioPreview.audio, false);
    }

    var open = audio.hidden;
    setAudioPreviewOpen(button, audio, open);
    openAudioPreview = open ? { button: button, audio: audio } : null;
}

function setAudioPreviewOpen(button, audio, open) {
    if (open && !audio.src) {
        audio.src = button.dataset.audioUrl;
        // Reset the icon when playback finishes so the button reads
        // "play again" (the player itself stays visible).
        audio.addEventListener('ended', function() {
            setPreviewButtonState(button, false);
        });
        audio.addEventListener('play', function() {
            setPreviewButtonState(button, true);
        });
    }
    audio.hidden = !open;
    if (open) {
        audio.play().catch(function() { /* surfaced by the player UI */ });
    } else {
        audio.pause();
    }
    setPreviewButtonState(button, open);
    button.setAttribute('aria-expanded', open ? 'true' : 'false');
}

function setPreviewButtonState(button, playing) {
    var playIcon = button.querySelector('[data-icon-play]');
    var stopIcon = button.querySelector('[data-icon-stop]');
    if (playIcon) playIcon.classList.toggle('hidden', playing);
    if (stopIcon) stopIcon.classList.toggle('hidden', !playing);
}

function handleDeleteClick(e) {
    var button = e.currentTarget;
    var itemId = button.dataset.itemId;
    var deleteUrl = button.dataset.deleteUrl;

    if (!itemId || !deleteUrl) return;
    if (!confirm('Delete this document?')) return;

    var documentList = button.closest('.document-list');
    if (!documentList) return;

    var csrfInput = document.querySelector('[name=csrfmiddlewaretoken]');
    var csrfToken = csrfInput ? csrfInput.value : '';

    fetch(deleteUrl, {
        method: 'POST',
        headers: {
            'X-CSRFToken': csrfToken,
            'X-Requested-With': 'XMLHttpRequest'
        }
    })
    .then(function(response) {
        if (!response.ok) throw new Error('Delete failed');
        return response.text();
    })
    .then(function(html) {
        documentList.outerHTML = html;
        initDocumentUpload();
    })
    .catch(function(error) {
        console.error('Delete error:', error);
        showToast('Error deleting document', 'error');
    });
}

function handleFileSelect(e) {
    var input = e.target;
    var files = input.files;
    if (!files || files.length === 0) return;

    var itemId = input.dataset.itemId;
    var uploadUrl = input.dataset.uploadUrl;
    if (!itemId || !uploadUrl) return;

    uploadFiles(itemId, uploadUrl, files);
    input.value = '';
}

export function uploadFiles(itemId, uploadUrl, files, onDone) {
    var formData = new FormData();
    for (var i = 0; i < files.length; i++) {
        formData.append('files', files[i]);
    }

    var progressEl = document.getElementById('upload-progress-' + itemId);
    if (progressEl) {
        progressEl.classList.remove('hidden');
        progressEl.querySelector('[data-progress-bar]').style.width = '30%';
    }

    var documentList = document.querySelector('.document-list[data-item-id="' + itemId + '"]');

    fetch(uploadUrl, {
        method: 'POST',
        body: formData,
        headers: {
            'X-CSRFToken': getCsrfToken()
        }
    })
    .then(function(response) {
        if (!response.ok) throw new Error('Upload failed');
        return response.text();
    })
    .then(function(html) {
        if (progressEl) {
            progressEl.querySelector('[data-progress-bar]').style.width = '100%';
            setTimeout(function() {
                progressEl.classList.add('hidden');
                progressEl.querySelector('[data-progress-bar]').style.width = '0%';
            }, 500);
        }

        if (documentList) {
            documentList.outerHTML = html;
            initDocumentUpload();
            flashUploadErrors();
        }
    })
    .catch(function(error) {
        console.error('Upload error:', error);
        if (progressEl) progressEl.classList.add('hidden');
        showToast('Error uploading files', 'error');
    })
    .finally(function() {
        if (onDone) onDone();
    });
}

function getCsrfToken() {
    var csrfInput = document.querySelector('[name=csrfmiddlewaretoken]');
    return csrfInput ? csrfInput.value : '';
}

// Server-side upload errors (type not allowed, duplicate content, too large)
// arrive as a [data-upload-errors] block inside the swapped document-list
// partial. Lift them into an auto-dismissing toast so they don't linger --
// and don't pile up across successive failed uploads.
function flashUploadErrors() {
    var messages = [];
    document.querySelectorAll('[data-upload-errors]').forEach(function(block) {
        block.querySelectorAll('li').forEach(function(line) {
            messages.push(line.textContent.trim());
        });
        block.remove();
    });
    if (messages.length) showToast(messages.join('\n'), 'error', 5000);
}

export function showToast(message, type, duration) {
    var toast = document.createElement('div');
    toast.className = 'fixed bottom-4 right-4 px-4 py-3 rounded-lg shadow-lg z-50 whitespace-pre-line ' + (type === 'error' ? 'alert-danger bg-surface' : 'alert-success bg-surface');
    toast.textContent = message;
    document.body.appendChild(toast);
    setTimeout(function() { toast.remove(); }, duration || 3000);
}
