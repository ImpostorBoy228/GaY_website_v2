/**
 * ПРОСТАЯ ВЕРСИЯ СКРИПТА АНАЛИТИКИ ДЛЯ ОТЛАДКИ
 * Версия 2.0 - Прямые вызовы с максимальным логированием
 */

console.log('%c[АНАЛИТИКА v2.0] СКРИПТ АНАЛИТИКИ ЗАГРУЖЕН!', 'color: red; font-size: 18px; font-weight: bold;');
console.log('Текущее время:', new Date().toLocaleTimeString());

// Функция для получения CSRF токена
function getCSRFToken() {
    const name = 'csrftoken';
    let cookieValue = null;
    if (document.cookie && document.cookie !== '') {
        const cookies = document.cookie.split(';');
        for (let i = 0; i < cookies.length; i++) {
            const cookie = cookies[i].trim();
            if (cookie.substring(0, name.length + 1) === (name + '=')) {
                cookieValue = decodeURIComponent(cookie.substring(name.length + 1));
                break;
            }
        }
    }
    console.log('[CSRF] Токен получен:', cookieValue ? 'ДА' : 'НЕТ');
    return cookieValue;
}

// Проверка работоспособности сети и AJAX
function testNetwork() {
    console.log('%c[ТЕСТ СЕТИ] Начало проверки сетевых соединений...', 'color: blue; font-weight: bold');
    console.log('- navigator.onLine:', navigator.onLine);
    console.log('- AJAX поддерживается:', typeof fetch !== 'undefined');
    console.log('- cookies доступны:', document.cookie ? 'ДА' : 'НЕТ');
    
    // Вывод всех cookies
    console.log('Все cookies:');
    document.cookie.split(';').forEach(cookie => {
        console.log('  -', cookie.trim());
    });
    
    // Тестовый запрос
    fetch('/analytics/track/video/view/', {
        method: 'OPTIONS',
        headers: {
            'Content-Type': 'application/json',
            'X-Requested-With': 'XMLHttpRequest'
        }
    })
    .then(response => {
        console.log('[ТЕСТ СЕТИ] Ответ от сервера:', response.status, response.statusText);
    })
    .catch(error => {
        console.error('[ТЕСТ СЕТИ] Ошибка сети:', error);
    });
}


/**
 * Global state for analytics tracking
 */
const analyticsState = {
    // Video tracking
    videoViewActive: false,
    videoStartTime: null,
    videoId: null,
    
    // Channel tracking
    channelViewActive: false,
    channelStartTime: null,
    channelId: null
};

// Функция прямого отслеживания видео для отладки
function directTrackVideo(videoId) {
    console.log('%c[ПРЯМОЕ ОТСЛЕЖИВАНИЕ ВИДЕО]', 'color: purple; font-weight: bold');
    console.log('Начало отслеживания видео ID:', videoId);
    
    // Получение CSRF токена
    const csrfToken = getCSRFToken();
    
    // Прямой запрос к API
    const data = { video_id: videoId };
    
    // Логируем тело запроса
    console.log('Тело запроса:', JSON.stringify(data));
    
    fetch('/analytics/track/video/view/', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
            'X-CSRFToken': csrfToken,
            'X-Requested-With': 'XMLHttpRequest'
        },
        credentials: 'same-origin',
        body: JSON.stringify(data)
    })
    .then(response => {
        console.log('Ответ сервера:', response.status, response.statusText);
        return response.text();
    })
    .then(text => {
        console.log('Текст ответа:', text);
        try {
            const json = JSON.parse(text);
            console.log('Ответ JSON:', json);
        } catch (e) {
            console.warn('Не удалось парсить JSON');
        }
    })
    .catch(error => {
        console.error('Ошибка при отслеживании видео:', error);
    });
}

// Функция прямого отслеживания канала для отладки
function directTrackChannel(channelId) {
    console.log('%c[ПРЯМОЕ ОТСЛЕЖИВАНИЕ КАНАЛА]', 'color: purple; font-weight: bold');
    console.log('Начало отслеживания канала ID:', channelId);
    
    // Получение CSRF токена
    const csrfToken = getCSRFToken();
    
    // Прямой запрос к API
    const data = { channel_id: channelId };
    
    // Логируем тело запроса
    console.log('Тело запроса:', JSON.stringify(data));
    
    fetch('/analytics/track/channel/view/', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
            'X-CSRFToken': csrfToken,
            'X-Requested-With': 'XMLHttpRequest'
        },
        credentials: 'same-origin',
        body: JSON.stringify(data)
    })
    .then(response => {
        console.log('Ответ сервера:', response.status, response.statusText);
        return response.text();
    })
    .then(text => {
        console.log('Текст ответа:', text);
        try {
            const json = JSON.parse(text);
            console.log('Ответ JSON:', json);
        } catch (e) {
            console.warn('Не удалось парсить JSON');
        }
    })
    .catch(error => {
        console.error('Ошибка при отслеживании канала:', error);
    });
}

/**
 * Get CSRF token from cookies
 * @returns {string} CSRF token
 */
function getCSRFToken() {
    const name = 'csrftoken';
    let cookieValue = null;
    if (document.cookie && document.cookie !== '') {
        const cookies = document.cookie.split(';');
        for (let i = 0; i < cookies.length; i++) {
            const cookie = cookies[i].trim();
            if (cookie.substring(0, name.length + 1) === (name + '=')) {
                cookieValue = decodeURIComponent(cookie.substring(name.length + 1));
                break;
            }
        }
    }
    return cookieValue;
}

/**
 * Send data to analytics API endpoint
 * @param {string} endpoint - API endpoint path
 * @param {object} data - Data to send
 * @returns {Promise} Fetch promise
 */
function sendAnalyticsData(endpoint, data) {
    const csrfToken = getCSRFToken();
    
    analyticsLogger.debug(`Подготовка запроса к ${endpoint}`, data);
    analyticsLogger.debug(`CSRF токен получен: ${csrfToken ? 'Да' : 'Нет'}`);
    
    // Убедимся, что endpoint не содержит лишних слешей
    const cleanEndpoint = endpoint.replace(/^\/+|\/+$/g, '');
    
    // Проверяем наличие 'api' в пути
    let url = '';
    if (endpoint.includes('api/')) {
        url = `/${cleanEndpoint}`;
    } else {
        url = `/analytics/${cleanEndpoint}/`;
    }
    
    analyticsLogger.info(`Отправка данных аналитики на ${url}`, data);
    
    return fetch(url, {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
            'X-CSRFToken': csrfToken,
            'X-Requested-With': 'XMLHttpRequest'
        },
        credentials: 'same-origin',
        body: JSON.stringify(data)
    })
    .then(response => {
        analyticsLogger.debug(`Получен ответ от сервера: ${response.status} ${response.statusText}`);
        
        if (!response.ok) {
            analyticsLogger.error(`Ошибка при отправке аналитики (${endpoint}): ${response.status} ${response.statusText}`);
            return response.text().then(errorText => {
                try {
                    const errorData = JSON.parse(errorText);
                    analyticsLogger.error('Детали ошибки:', errorData);
                    throw new Error(JSON.stringify(errorData));
                } catch (e) {
                    analyticsLogger.error('Текст ошибки:', errorText);
                    throw new Error(errorText);
                }
            });
        }
        
        analyticsLogger.debug('Ответ успешный, обрабатываем JSON');
        return response.json();
    })
    .then(responseData => {
        analyticsLogger.success(`Данные аналитики успешно отправлены (${endpoint})`, responseData);
        return responseData;
    })
    .catch(error => {
        analyticsLogger.error(`Не удалось отправить данные аналитики (${endpoint})`, error);
        // Пробуем вывести больше информации о проблеме
        analyticsLogger.error('Стек ошибки:', error.stack);
        // We don't rethrow, since analytics errors shouldn't break the user experience
    });
}

/**
 * Start tracking a video view
 * @param {number} videoId - ID of the video being viewed
 */
function trackVideoView(videoId) {
    if (!videoId) {
        analyticsLogger.error('Невозможно отслеживать просмотр видео: ID видео не указан');
        return;
    }
    
    analyticsLogger.debug(`Начало отслеживания просмотра видео: ${videoId}`);
    
    if (analyticsState.videoViewActive && analyticsState.videoId === videoId) {
        analyticsLogger.info('Отслеживание видео уже активно для этого видео');
        return;
    }
    
    // End any previous video view that wasn't properly closed
    if (analyticsState.videoViewActive) {
        analyticsLogger.warn('Обнаружено активное отслеживание другого видео, завершаем его');
        endVideoView();
    }
    
    analyticsLogger.info(`Отправка запроса на начало отслеживания видео: ${videoId}`);
    
    // Добавляем консольный вывод для отладки
    console.log('[DEBUG] Отправка запроса на начало отслеживания видео:', videoId);
    console.log('[DEBUG] URL:', '/analytics/track/video/view/');
    
    sendAnalyticsData('track/video/view', { video_id: videoId })
        .then(response => {
            analyticsState.videoViewActive = true;
            analyticsState.videoStartTime = Date.now();
            analyticsState.videoId = videoId;
            analyticsLogger.success(`Начато отслеживание просмотра видео ID: ${videoId}`);
        });

}

/**
 * End tracking a video view
 */
function endVideoView() {
    if (!analyticsState.videoViewActive) {
        return;
    }
    
    const duration = Math.floor((Date.now() - analyticsState.videoStartTime) / 1000);
    
    sendAnalyticsData('track/video/end', {
        video_id: analyticsState.videoId,
        duration: duration
    })
    .then(() => {
        console.log(`Ended video view tracking after ${duration} seconds`);
        analyticsState.videoViewActive = false;
        analyticsState.videoStartTime = null;
        analyticsState.videoId = null;
    });
}

/**
 * Track a video seek event
 * @param {number} videoId - ID of the video
 * @param {number} fromPosition - Starting position in seconds
 * @param {number} toPosition - Ending position in seconds
 */
function trackVideoSeek(videoId, fromPosition, toPosition) {
    if (!videoId || fromPosition === undefined || toPosition === undefined) {
        console.error('Cannot track video seek: Missing required parameters');
        return;
    }
    
    // Don't track seeks that are less than 1 second difference
    if (Math.abs(toPosition - fromPosition) < 1) {
        return;
    }
    
    sendAnalyticsData('track/seek', {
        video_id: videoId,
        from_position: Math.floor(fromPosition),
        to_position: Math.floor(toPosition)
    });
}

/**
 * Start tracking a channel view
 * @param {number} channelId - ID of the channel being viewed
 */
function trackChannelView(channelId) {
    if (!channelId) {
        console.error('Cannot track channel view: No channel ID provided');
        return;
    }
    
    if (analyticsState.channelViewActive && analyticsState.channelId === channelId) {
        console.log('Channel view tracking already active for this channel');
        return;
    }
    
    // End any previous channel view that wasn't properly closed
    if (analyticsState.channelViewActive) {
        endChannelView();
    }
    
    sendAnalyticsData('track/channel/view', { channel_id: channelId })
        .then(response => {
            analyticsState.channelViewActive = true;
            analyticsState.channelStartTime = Date.now();
            analyticsState.channelId = channelId;
            console.log('Started tracking channel view for channel ID:', channelId);
        });
}

/**
 * End tracking a channel view
 */
function endChannelView() {
    if (!analyticsState.channelViewActive) {
        return;
    }
    
    const duration = Math.floor((Date.now() - analyticsState.channelStartTime) / 1000);
    
    sendAnalyticsData('track/channel/end', {
        channel_id: analyticsState.channelId,
        duration: duration
    })
    .then(() => {
        console.log(`Ended channel view tracking after ${duration} seconds`);
        analyticsState.channelViewActive = false;
        analyticsState.channelStartTime = null;
        analyticsState.channelId = null;
    });
}

/**
 * Setup page unload handler to end active tracking
 */
function setupUnloadHandler() {
    analyticsLogger.info('Настройка обработчика завершения сессии при закрытии страницы');
    window.addEventListener('beforeunload', function() {
        analyticsLogger.debug('Событие beforeunload сработало');
        // End any active video view
        if (analyticsState.videoViewActive) {
            // Using synchronous approach for beforeunload
            const duration = Math.floor((Date.now() - analyticsState.videoStartTime) / 1000);
            
            analyticsLogger.info(`Отправка данных о завершении просмотра видео ${analyticsState.videoId} через Beacon API, длительность: ${duration} сек.`);
            
            // Use navigator.sendBeacon for more reliable data sending during page unload
            if (navigator.sendBeacon) {
                const data = JSON.stringify({
                    video_id: analyticsState.videoId,
                    duration: duration
                });
                
                const csrfToken = getCSRFToken();
                const headers = {
                    'Content-Type': 'application/json',
                    'X-CSRFToken': csrfToken
                };
                
                const blob = new Blob([data], { type: 'application/json' });
                const success = navigator.sendBeacon('/analytics/track/video/end/', blob);
                
                analyticsLogger.debug(`Beacon отправлен: ${success ? 'успешно' : 'неудачно'}`);
            } else {
                analyticsLogger.warn('Beacon API не поддерживается браузером');
            }
        }
        
        // End any active channel view
        if (analyticsState.channelViewActive) {
            const duration = Math.floor((Date.now() - analyticsState.channelStartTime) / 1000);
            
            analyticsLogger.info(`Отправка данных о завершении просмотра канала ${analyticsState.channelId} через Beacon API, длительность: ${duration} сек.`);
            
            if (navigator.sendBeacon) {
                const data = JSON.stringify({
                    channel_id: analyticsState.channelId,
                    duration: duration
                });
                
                const blob = new Blob([data], { type: 'application/json' });
                const success = navigator.sendBeacon('/analytics/track/channel/end/', blob);
                
                analyticsLogger.debug(`Beacon отправлен: ${success ? 'успешно' : 'неудачно'}`);
            } else {
                analyticsLogger.warn('Beacon API не поддерживается браузером');
            }
        }
    });
}

/**
 * Тестирование соединения с API аналитики
 */
function testAnalyticsConnection() {
    analyticsLogger.info('Тестирование соединения с API аналитики...');
    
    // Выводим структуру страницы
    debugPageStructure();
    
    // Выводим все cookies
    analyticsLogger.debug('Доступные cookies:');
    document.cookie.split(';').forEach(cookie => {
        analyticsLogger.debug(`- ${cookie.trim()}`);
    });
    
    // Проверяем CSRF токен
    const csrfToken = getCSRFToken();
    analyticsLogger.debug(`Статус CSRF токена: ${csrfToken ? 'получен' : 'не найден'}`);
    
    // Тестовый ping запрос
    fetch('/analytics/track/video/view/', {
        method: 'OPTIONS',
        headers: {
            'X-Requested-With': 'XMLHttpRequest',
            'X-CSRFToken': csrfToken
        }
    })
    .then(response => {
        analyticsLogger.info(`Тестовый ответ API: ${response.status} ${response.statusText}`);
    })
    .catch(error => {
        analyticsLogger.error('Ошибка при тестировании API:', error);
    });
}

/**
 * Инициализация видео-аналитики
 */
function initializeVideoAnalytics() {
    analyticsLogger.info('Инициализация аналитики видео...');
    
    const videoPlayer = document.getElementById('videoPlayer');
    const videoIdElement = document.querySelector('meta[name="video-id"]');
    
    if (!videoPlayer) {
        analyticsLogger.error('Элемент видеоплеера не найден');
        return;
    }
    
    if (!videoIdElement) {
        analyticsLogger.error('Метатег video-id не найден');
        return;
    }
    
    const videoId = videoIdElement.getAttribute('content');
    if (!videoId) {
        analyticsLogger.error('Метатег video-id не содержит значения');
        return;
    }
    
    analyticsLogger.info(`Запуск отслеживания видео ID: ${videoId}`);
    trackVideoView(videoId);
    
    // Track seeks when the user uses the progress bar
    let lastTime = 0;
    videoPlayer.addEventListener('seeking', function() {
        const currentTime = videoPlayer.currentTime;
        // Only track actual seeks, not autoplay progress
        if (Math.abs(currentTime - lastTime) > 3) {
            analyticsLogger.debug(`Обнаружена перемотка: ${lastTime.toFixed(1)}s → ${currentTime.toFixed(1)}s`);
            trackVideoSeek(videoId, lastTime, currentTime);
        }
        lastTime = currentTime;
    });
    
    // Update last time continuously
    videoPlayer.addEventListener('timeupdate', function() {
        // Only update if not seeking to avoid tracking small automatic adjustments
        if (!videoPlayer.seeking) {
            lastTime = videoPlayer.currentTime;
        }
    });
}

/**
 * Инициализация аналитики канала
 */
function initializeChannelAnalytics() {
    analyticsLogger.info('Инициализация аналитики канала...');
    
    const channelIdElement = document.querySelector('meta[name="channel-id"]');
    if (!channelIdElement) {
        analyticsLogger.error('Метатег channel-id не найден');
        return;
    }
    
    const channelId = channelIdElement.getAttribute('content');
    if (!channelId) {
        analyticsLogger.error('Метатег channel-id не содержит значения');
        return;
    }
    
    analyticsLogger.info(`Запуск отслеживания канала ID: ${channelId}`);
    trackChannelView(channelId);
}

/**
 * Функция для инициализации аналитики при загрузке страницы
 */
document.addEventListener('DOMContentLoaded', function() {
    console.log('%c[АНАЛИТИКА] DOM ЗАГРУЖЕН, НАЧАЛО ИНИЦИАЛИЗАЦИИ', 'color: green; font-size: 14px; font-weight: bold;');
    
    // Тестирование работы сети
    testNetwork();
    
    // Вывод всех мета-тегов на странице
    console.log('%c[МЕТА ТЕГИ] Список всех meta тегов:', 'color: blue; font-weight: bold');
    const metaTags = document.querySelectorAll('meta');
    metaTags.forEach(tag => {
        console.log('- meta tag:', tag.outerHTML);
    });
    
    // Проверка наличия тегов для аналитики
    const videoIdElement = document.querySelector('meta[name="video-id"]');
    const channelIdElement = document.querySelector('meta[name="channel-id"]');
    
    console.log('Мета-тег video-id:', videoIdElement ? 'НАЙДЕН' : 'НЕ НАЙДЕН');
    console.log('Мета-тег channel-id:', channelIdElement ? 'НАЙДЕН' : 'НЕ НАЙДЕН');
    
    if (videoIdElement) {
        const videoId = videoIdElement.getAttribute('content');
        console.log('%c[ВИДЕО СТРАНИЦА] Обнаружена страница видео с ID:', 'color: green; font-weight: bold', videoId);
        
        // Прямой вызов функции для тестирования
        directTrackVideo(videoId);
        
        // Также пробуем инициализировать стандартную аналитику
        try {
            initVideoAnalytics(videoId);
        } catch (e) {
            console.error('Ошибка при инициализации видео аналитики:', e);
        }
    } else if (channelIdElement) {
        const channelId = channelIdElement.getAttribute('content');
        console.log('%c[КАНАЛ СТРАНИЦА] Обнаружена страница канала с ID:', 'color: green; font-weight: bold', channelId);
        
        // Прямой вызов функции для тестирования
        directTrackChannel(channelId);
        
        // Также пробуем инициализировать стандартную аналитику
        try {
            initChannelAnalytics(channelId);
        } catch (e) {
            console.error('Ошибка при инициализации аналитики канала:', e);
        }
    } else {
        console.log('%c[ОБЫЧНАЯ СТРАНИЦА] Не обнаружены мета-теги для аналитики', 'color: orange');
    }
    
    // Добавляем обработчик закрытия страницы
    window.addEventListener('beforeunload', function() {
        console.log('%c[ЗАКРЫТИЕ СТРАНИЦЫ] Завершение аналитики', 'color: red; font-weight: bold');
        
        if (analyticsState.videoViewActive) {
            console.log('Завершение отслеживания видео при закрытии страницы');
            endVideoView();
        }
        if (analyticsState.channelViewActive) {
            console.log('Завершение отслеживания канала при закрытии страницы');
            endChannelView();
        }
    });
});

// Export functions for use by other modules
window.analyticsTracker = {
    trackVideoView,
    endVideoView,
    trackVideoSeek,
    trackChannelView,
    endChannelView
};
