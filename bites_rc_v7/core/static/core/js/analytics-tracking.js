/**
 * Функции для отслеживания аналитики на сайте
 */

/**
 * Отслеживание перемотки видео
 */
function trackVideoSeek(videoId, fromPosition, toPosition) {
    // Отслеживаем только для авторизованных пользователей
    if (!document.cookie.includes('sessionid')) {
        console.log('Не удалось отследить перемотку: пользователь не авторизован');
        return;
    }
    
    const csrfToken = getCsrfToken();
    if (!csrfToken) {
        console.log('Не удалось отследить перемотку: не найден CSRF-токен');
        return;
    }
    
    console.log(`Отправка перемотки: video_id=${videoId}, from=${fromPosition}, to=${toPosition}`);
    
    // Используем правильный путь из analytics/urls.py
    fetch('/api/analytics/track/seek/', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
            'X-CSRFToken': csrfToken
        },
        body: JSON.stringify({
            video_id: videoId,
            from_position: fromPosition,
            to_position: toPosition
        }),
        credentials: 'same-origin'
    })
    .then(response => {
        console.log(`Получен ответ от сервера: статус ${response.status}`);
        if (!response.ok) {
            return response.text().then(text => {
                console.error(`Ошибка при отслеживании перемотки видео: статус ${response.status}`);
                console.error('Текст ошибки:', text);
                // Попробуем альтернативный путь, если статус 404
                if (response.status === 404) {
                    console.log('Пробуем записать перемотку напрямую через хак');
                    
                    // Прямая запись в базу данных
                    return fetch('/direct_seek_log/', {
                        method: 'POST',
                        headers: {
                            'Content-Type': 'application/json',
                            'X-CSRFToken': csrfToken
                        },
                        body: JSON.stringify({
                            video_id: videoId,
                            from_position: fromPosition,
                            to_position: toPosition
                        }),
                        credentials: 'same-origin'
                    });
                }
            });
        } else {
            console.log('Перемотка видео успешно отслежена');
            return response.json();
        }
    })
    .then(data => {
        if (data) console.log('Ответ сервера:', data);
    })
    .catch(error => {
        console.error('Ошибка при отслеживании перемотки видео:', error);
    });
}

/**
 * Отслеживание окончания просмотра видео
 */
function trackVideoViewEnd(videoId, duration) {
    // Отслеживаем только для авторизованных пользователей
    if (!document.cookie.includes('sessionid')) return;
    
    const csrfToken = getCsrfToken();
    if (!csrfToken) return;
    
    // Используем правильный путь к API (согласно urls.py)
    fetch('/api/analytics/track/video/end/', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
            'X-CSRFToken': csrfToken
        },
        body: JSON.stringify({
            video_id: videoId,
            duration: duration
        }),
        credentials: 'same-origin'
    })
    .then(response => {
        if (!response.ok) {
            console.error('Ошибка при отслеживании окончания просмотра видео');
        } else {
            console.log('Окончание просмотра видео успешно отслежено');
        }
    })
    .catch(error => {
        console.error('Ошибка при отслеживании окончания просмотра видео:', error);
    });
}

/**
 * Инициализация отслеживания аналитики для видеоплеера
 */
function initAnalyticsTracking(videoElement) {
    if (!videoElement) {
        console.log('Не удалось инициализировать отслеживание: элемент видео не найден');
        return;
    }
    
    // Получаем ID видео из URL
    const pathParts = window.location.pathname.split('/');
    const videoIndex = pathParts.indexOf('video');
    if (videoIndex === -1) {
        console.log('Не удалось инициализировать отслеживание: в URL нет "video"');
        return;
    }
    
    // Идентификатор видео должен быть в URL после "/video/"
    const videoId = pathParts[videoIndex + 1];
    if (!videoId) {
        console.log('Не удалось инициализировать отслеживание: не найден ID видео в URL');
        return;
    }
    
    console.log('Инициализация отслеживания аналитики для видео:', videoId);
    
    // Переменные для отслеживания поведения перемотки
    let lastSeekTime = 0;
    let seekStartPosition = 0;
    let isTracking = false;
    let seekTimeout = null;
    let videoStartTime = Date.now();
    
    // Отслеживаем начало просмотра видео
    videoElement.addEventListener('play', function() {
        videoStartTime = Date.now();
        if (!isTracking) {
            // Отслеживаем только первое воспроизведение или после паузы
            isTracking = true;
            console.log('Начало отслеживания просмотра видео');
        }
    });
    
    // Отслеживаем события перемотки с логикой объединения
    videoElement.addEventListener('seeking', function() {
        // Сохраняем позицию, с которой началась перемотка
        if (!seekStartPosition) {
            seekStartPosition = Math.floor(videoElement.currentTime);
            console.log('Начало перемотки с позиции:', seekStartPosition);
        }
    });
    
    // Когда перемотка завершается
    videoElement.addEventListener('seeked', function() {
        const currentSeekTime = Date.now();
        const seekEndPosition = Math.floor(videoElement.currentTime);
        
        // Обрабатываем только перемотки, которые действительно изменили позицию
        if (seekStartPosition !== seekEndPosition) {
            console.log('Перемотка завершена на позиции:', seekEndPosition);
            
            // Очищаем любое ожидающее отслеживание перемотки
            if (seekTimeout) {
                clearTimeout(seekTimeout);
            }
            
            // Если с момента последней перемотки прошло менее 2 секунд, пока не отслеживаем
            // Это позволяет объединять несколько перемоток в течение 2 секунд
            if (currentSeekTime - lastSeekTime < 2000) {
                console.log('Менее 2 секунд с последней перемотки, объединяем');
                
                // Планируем отслеживание через 2 секунды без перемотки
                seekTimeout = setTimeout(() => {
                    console.log('Отправка объединенной перемотки:', seekStartPosition, '->', seekEndPosition);
                    // Отслеживаем перемотку с последней конечной позицией
                    trackVideoSeek(videoId, seekStartPosition, seekEndPosition);
                    // Сбрасываем переменные отслеживания
                    seekStartPosition = 0;
                    lastSeekTime = 0;
                }, 2000);
            } else {
                // Более 2 секунд с момента последней перемотки, отслеживаем немедленно
                console.log('Более 2 секунд с последней перемотки, отслеживаем сразу');
                trackVideoSeek(videoId, seekStartPosition, seekEndPosition);
                seekStartPosition = 0;
            }
            
            lastSeekTime = currentSeekTime;
        }
    });
    
    // Отслеживаем окончание просмотра видео, когда пользователь покидает страницу
    window.addEventListener('beforeunload', function() {
        if (isTracking) {
            const viewDuration = Math.floor((Date.now() - videoStartTime) / 1000);
            console.log('Пользователь покидает страницу, отслеживаем окончание просмотра');
            trackVideoViewEnd(videoId, viewDuration);
        }
    });
    
    // Также отслеживаем, когда видео приостановлено на значительное время
    videoElement.addEventListener('pause', function() {
        const pauseStartTime = Date.now();
        const pauseTimeout = setTimeout(() => {
            // Если пауза длится более 30 секунд, считаем сеанс просмотра завершенным
            if (videoElement.paused) {
                const viewDuration = Math.floor((pauseStartTime - videoStartTime) / 1000);
                console.log('Длительная пауза, отслеживаем окончание просмотра');
                trackVideoViewEnd(videoId, viewDuration);
                isTracking = false;
            }
        }, 30000); // 30 секунд
        
        // Если видео воспроизводится снова до истечения времени ожидания, очищаем таймаут
        videoElement.addEventListener('play', function clearPauseTimeout() {
            clearTimeout(pauseTimeout);
            videoElement.removeEventListener('play', clearPauseTimeout);
        });
    });
}

/**
 * Получение CSRF-токена из cookies
 */
function getCsrfToken() {
    const cookieValue = document.cookie
        .split('; ')
        .find(row => row.startsWith('csrftoken='))
        ?.split('=')[1];
    return cookieValue;
}

// Инициализация отслеживания при загрузке страницы
document.addEventListener('DOMContentLoaded', function() {
    const videoPlayer = document.getElementById('videoPlayer');
    if (videoPlayer) {
        console.log('Найден видеоплеер, инициализация отслеживания аналитики');
        initAnalyticsTracking(videoPlayer);
    }
});
