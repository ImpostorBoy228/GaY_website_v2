/**
 * YouTube download status checker
 * Периодически проверяет статус загрузки YouTube видео и обновляет UI
 */

// Инициализация проверки статуса загрузки YouTube видео
function initYouTubeDownloadStatus() {
    const videoId = getVideoIdFromUrl();
    const downloadStatus = document.getElementById('download-status');
    const youtubePlayer = document.getElementById('youtube-player');
    const videoPlayer = document.getElementById('videoPlayer');
    
    if (!downloadStatus || !videoId) return;
    
    // Проверяем, является ли видео YouTube и не загружено ли оно
    const isYouTube = document.getElementById('videoPageContainer')?.dataset?.isYoutube === 'true';
    if (!isYouTube) return;
    
    console.log('Initializing YouTube download status checker for video ID:', videoId);
    
    // Запускаем периодическую проверку статуса загрузки
    checkDownloadStatus(videoId, downloadStatus, youtubePlayer, videoPlayer);
    const intervalId = setInterval(() => {
        checkDownloadStatus(videoId, downloadStatus, youtubePlayer, videoPlayer, () => {
            clearInterval(intervalId);
        });
    }, 5000); // Проверяем каждые 5 секунд
}

// Получение ID видео из URL
function getVideoIdFromUrl() {
    const urlParts = window.location.pathname.split('/');
    return urlParts[urlParts.length - 2]; // Предпоследний элемент должен быть ID видео
}

// Проверка статуса загрузки видео
function checkDownloadStatus(videoId, downloadStatus, youtubePlayer, videoPlayer, onComplete) {
    fetch(`/video/${videoId}/stream/`)
        .then(response => response.json())
        .then(data => {
            console.log('Download status response:', data);
            
            // Обновляем UI в зависимости от статуса
            if (data.status === 'downloading') {
                // Видео всё ещё загружается
                updateDownloadProgress(downloadStatus, data.progress || 0);
            } else if (data.status === 'completed' || !data.status) {
                // Загрузка завершена или нет данных о статусе (предполагаем, что загрузка завершена)
                console.log('Download completed, refreshing page to show video player');
                // Перезагружаем страницу для отображения видео плеера
                window.location.reload();
                if (onComplete) onComplete();
            } else if (data.status === 'youtube_fallback') {
                // Ошибка загрузки, показываем YouTube плеер
                showYouTubePlayer(youtubePlayer, data.youtube_id);
                hideDownloadStatus(downloadStatus);
                if (onComplete) onComplete();
            } else if (data.status === 'download_queued') {
                // Загрузка поставлена в очередь
                updateDownloadStatus(downloadStatus, 'Видео добавлено в очередь загрузки...', 0);
            }
        })
        .catch(error => {
            console.error('Error checking download status:', error);
            // При ошибке запроса проверяем доступность видеофайла напрямую
            checkVideoFileAvailability(videoId);
        });
}

// Проверка доступности видеофайла напрямую
function checkVideoFileAvailability(videoId) {
    // Создаем временный видео элемент
    const tempVideo = document.createElement('video');
    tempVideo.style.display = 'none';
    document.body.appendChild(tempVideo);
    
    // Пробуем загрузить видео
    const source = document.createElement('source');
    source.src = `/video/${videoId}/stream/`;
    source.type = 'video/mp4';
    tempVideo.appendChild(source);
    
    // Устанавливаем обработчики событий
    tempVideo.addEventListener('loadeddata', () => {
        console.log('Video file is available, reloading page');
        window.location.reload();
    });
    
    tempVideo.addEventListener('error', () => {
        console.log('Video file is not available yet');
        document.body.removeChild(tempVideo);
    });
    
    tempVideo.load();
    
    // Удаляем временный элемент через 5 секунд, если нет ответа
    setTimeout(() => {
        if (document.body.contains(tempVideo)) {
            document.body.removeChild(tempVideo);
        }
    }, 5000);
}

// Обновление прогресса загрузки
function updateDownloadProgress(downloadStatus, progress) {
    const progressBar = downloadStatus.querySelector('.progress');
    const statusMessage = downloadStatus.querySelector('.status-message');
    
    if (progressBar) {
        progressBar.style.width = `${progress}%`;
    }
    
    if (statusMessage) {
        statusMessage.textContent = `Видео загружается: ${Math.round(progress)}%`;
    }
}

// Обновление статуса загрузки
function updateDownloadStatus(downloadStatus, message, progress) {
    const statusMessage = downloadStatus.querySelector('.status-message');
    const progressBar = downloadStatus.querySelector('.progress');
    
    if (statusMessage) {
        statusMessage.textContent = message;
    }
    
    if (progressBar) {
        progressBar.style.width = `${progress}%`;
    }
}

// Скрытие статуса загрузки
function hideDownloadStatus(downloadStatus) {
    if (downloadStatus) {
        downloadStatus.style.display = 'none';
    }
}

// Показ YouTube плеера
function showYouTubePlayer(youtubePlayer, youtubeId) {
    if (youtubePlayer) {
        youtubePlayer.innerHTML = `
            <iframe width="100%" height="100%" 
                src="https://www.youtube.com/embed/${youtubeId}?autoplay=1" 
                frameborder="0" 
                allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture" 
                allowfullscreen>
            </iframe>
        `;
        youtubePlayer.style.display = 'block';
    }
}

// Инициализация при загрузке DOM
document.addEventListener('DOMContentLoaded', initYouTubeDownloadStatus);
