document.addEventListener('DOMContentLoaded', function() {
    const dropArea = document.getElementById('dropArea');
    const fileInput = document.getElementById('fileInput');
    const videoPreview = document.getElementById('videoPreview');
    const previewVideo = document.getElementById('previewVideo');
    const fileName = document.getElementById('fileName');
    const fileSize = document.getElementById('fileSize');
    const removeVideo = document.getElementById('removeVideo');
    const uploadForm = document.getElementById('uploadForm');
    const uploadProgress = document.getElementById('uploadProgress');
    const progressBar = document.getElementById('progressBar');
    const progressText = document.getElementById('progressText');
    const uploadSpeed = document.getElementById('uploadSpeed');
    const thumbnailOptions = document.getElementById('thumbnailOptions');
    const thumbnailGrid = document.getElementById('thumbnailGrid');
    const submitButton = document.getElementById('submitButton');
    const generateTagsButton = document.getElementById('generateTagsButton');

    // Prevent default drag behaviors
    ['dragenter', 'dragover', 'dragleave', 'drop'].forEach(eventName => {
        dropArea.addEventListener(eventName, preventDefaults, false);
        document.body.addEventListener(eventName, preventDefaults, false);
    });

    // Highlight drop area when item is dragged over it
    ['dragenter', 'dragover'].forEach(eventName => {
        dropArea.addEventListener(eventName, highlight, false);
    });

    ['dragleave', 'drop'].forEach(eventName => {
        dropArea.addEventListener(eventName, unhighlight, false);
    });

    // Handle dropped files
    dropArea.addEventListener('drop', handleDrop, false);
    dropArea.addEventListener('click', () => fileInput.click());
    fileInput.addEventListener('change', handleFiles);

    function preventDefaults(e) {
        e.preventDefault();
        e.stopPropagation();
    }

    function highlight() {
        dropArea.classList.add('border-blue-500');
    }

    function unhighlight() {
        dropArea.classList.remove('border-blue-500');
    }

    function handleDrop(e) {
        const dt = e.dataTransfer;
        const files = dt.files;
        handleFiles({ target: { files } });
    }

    function handleFiles(e) {
        const files = e.target.files;
        if (files.length === 0) return;

        const file = files[0];
        if (!file.type.startsWith('video/')) {
            alert('Пожалуйста, выберите видео файл');
            return;
        }

        // Show video preview
        const videoURL = URL.createObjectURL(file);
        previewVideo.src = videoURL;
        fileName.textContent = file.name;
        fileSize.textContent = formatFileSize(file.size);
        videoPreview.classList.remove('hidden');

        // Reset form
        thumbnailOptions.classList.add('hidden');
        thumbnailGrid.innerHTML = '';
    }

    function formatFileSize(bytes) {
        if (bytes === 0) return '0 Bytes';
        const k = 1024;
        const sizes = ['Bytes', 'KB', 'MB', 'GB'];
        const i = Math.floor(Math.log(bytes) / Math.log(k));
        return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i];
    }

    removeVideo.addEventListener('click', () => {
        previewVideo.src = '';
        videoPreview.classList.add('hidden');
        thumbnailOptions.classList.add('hidden');
        thumbnailGrid.innerHTML = '';
    });

    uploadForm.addEventListener('submit', handleSubmit);

    function handleSubmit(e) {
        e.preventDefault();

        const formData = new FormData();
        const videoFile = fileInput.files[0];
        if (!videoFile) {
            alert('Пожалуйста, выберите видео файл');
            return;
        }

        formData.append('video', videoFile);
        formData.append('title', document.getElementById('title').value);
        formData.append('description', document.getElementById('description').value);
        formData.append('tags', document.getElementById('tags').value);

        // Show progress
        uploadProgress.classList.remove('hidden');
        submitButton.disabled = true;

        const xhr = new XMLHttpRequest();
        xhr.open('POST', '/upload/', true);
        
        // Add CSRF token to request headers
        const csrfToken = document.querySelector('[name=csrfmiddlewaretoken]').value;
        xhr.setRequestHeader('X-CSRFToken', csrfToken);

        // Track upload progress
        let startTime = Date.now();
        let lastLoaded = 0;

        xhr.upload.onprogress = function(e) {
            if (e.lengthComputable) {
                const percentComplete = (e.loaded / e.total) * 100;
                progressBar.style.width = percentComplete + '%';
                progressText.textContent = Math.round(percentComplete) + '%';

                // Calculate upload speed
                const currentTime = Date.now();
                const timeElapsed = (currentTime - startTime) / 1000; // in seconds
                const bytesLoaded = e.loaded - lastLoaded;
                const speed = bytesLoaded / timeElapsed / 1024 / 1024; // MB/s
                uploadSpeed.textContent = speed.toFixed(2) + ' MB/s';

                lastLoaded = e.loaded;
                startTime = currentTime;
            }
        };

        xhr.onload = function() {
            if (xhr.status === 200) {
                const response = JSON.parse(xhr.responseText);
                if (response.success) {
                    // Store video_id in form dataset
                    uploadForm.dataset.videoId = response.video_id;
                    // Show thumbnail options
                    showThumbnailOptions(response.thumbnails);
                } else {
                    alert(response.error || 'Произошла ошибка при загрузке видео');
                }
            } else {
                alert('Произошла ошибка при загрузке видео');
            }
            submitButton.disabled = false;
        };

        xhr.onerror = function() {
            alert('Произошла ошибка при загрузке видео');
            submitButton.disabled = false;
        };

        xhr.send(formData);
    }

    function showThumbnailOptions(thumbnails) {
        thumbnailGrid.innerHTML = '';
        thumbnails.forEach((thumbnail, index) => {
            const thumbnailDiv = document.createElement('div');
            thumbnailDiv.className = 'relative group cursor-pointer';
            thumbnailDiv.innerHTML = `
                <img src="${thumbnail.url}" alt="Превью ${index + 1}" class="w-full h-32 object-cover rounded-lg">
                <div class="absolute inset-0 bg-black bg-opacity-50 flex items-center justify-center opacity-0 group-hover:opacity-100 transition-opacity">
                    <button class="text-white bg-blue-600 px-4 py-2 rounded-md" onclick="selectThumbnail(${index})">
                        Выбрать
                    </button>
                </div>
            `;
            thumbnailGrid.appendChild(thumbnailDiv);
        });
        thumbnailOptions.classList.remove('hidden');
    }

    window.selectThumbnail = function(index) {
        const videoId = uploadForm.dataset.videoId;
        if (!videoId) {
            alert('Ошибка: ID видео не найден. Пожалуйста, попробуйте загрузить видео снова.');
            return;
        }

        // Disable all thumbnail buttons
        const buttons = document.querySelectorAll('#thumbnailGrid button');
        buttons.forEach(button => button.disabled = true);

        fetch(`/video/${videoId}/select_thumbnail/`, {
            method: 'POST',
            credentials: 'same-origin',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': document.querySelector('[name=csrfmiddlewaretoken]').value
            },
            body: JSON.stringify({ position: index })
        })
        .then(response => {
            if (!response.ok) {
                throw new Error('Ошибка сервера');
            }
            return response.json();
        })
        .then(data => {
            if (data.success) {
                window.location.href = `/video/${videoId}/`;
            } else {
                alert(data.error || 'Произошла ошибка при выборе превью');
                // Re-enable buttons
                buttons.forEach(button => button.disabled = false);
            }
        })
        .catch(error => {
            alert('Произошла ошибка при выборе превью. Пожалуйста, попробуйте снова.');
            // Re-enable buttons
            buttons.forEach(button => button.disabled = false);
        });
    };

    if (generateTagsButton) {
        generateTagsButton.addEventListener('click', async function(e) {
            e.preventDefault();
            const title = document.getElementById('title').value.trim();
            const description = document.getElementById('description').value.trim();
            if (!title && !description) {
                alert('Пожалуйста, введите название или описание для генерации тегов');
                return;
            }
            generateTagsButton.disabled = true;
            try {
                const response = await fetch('/api/generate-tags/', {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                        'X-CSRFToken': document.querySelector('[name=csrfmiddlewaretoken]').value
                    },
                    body: JSON.stringify({ title, description, max_tags: 10 })
                });
                const data = await response.json();
                if (response.ok && data.tags) {
                    document.getElementById('tags').value = data.tags.join(', ');
                } else {
                    alert(data.error || 'Ошибка при генерации тегов');
                }
            } catch (err) {
                console.error('Generate tags error:', err);
                alert('Ошибка при генерации тегов');
            } finally {
                generateTagsButton.disabled = false;
            }
        });
    }
}); 