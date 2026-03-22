export function initDocumentUpload() {
    initFileInputs();
    initDropzones();
    initDeleteButtons();
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
            zone.classList.add('border-blue-400', 'bg-blue-50', 'text-blue-600');
        });

        zone.addEventListener('dragleave', function(e) {
            e.preventDefault();
            e.stopPropagation();
            zone.classList.remove('border-blue-400', 'bg-blue-50', 'text-blue-600');
        });

        zone.addEventListener('drop', function(e) {
            e.preventDefault();
            e.stopPropagation();
            zone.classList.remove('border-blue-400', 'bg-blue-50', 'text-blue-600');
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

function uploadFiles(itemId, uploadUrl, files) {
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
        }
    })
    .catch(function(error) {
        console.error('Upload error:', error);
        if (progressEl) progressEl.classList.add('hidden');
        showToast('Error uploading files', 'error');
    });
}

function getCsrfToken() {
    var csrfInput = document.querySelector('[name=csrfmiddlewaretoken]');
    return csrfInput ? csrfInput.value : '';
}

function showToast(message, type) {
    var toast = document.createElement('div');
    toast.className = 'fixed bottom-4 right-4 px-4 py-3 rounded-lg shadow-lg z-50 ' + (type === 'error' ? 'bg-red-500 text-white' : 'bg-green-500 text-white');
    toast.textContent = message;
    document.body.appendChild(toast);
    setTimeout(function() { toast.remove(); }, 3000);
}
