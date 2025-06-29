/**
 * Video player functionality and controls
 */

/**
 * Initialize video player functionality
 */
function initVideoPlayer() {
    const mainVideo = document.getElementById('videoPlayer');
    const adVideo = document.getElementById('adPlayer');
    const adOverlay = document.getElementById('adOverlay');
    const loadingOverlay = document.getElementById('loadingOverlay');
    
    // Initialize theater mode
    initTheaterMode();
    
    // Initialize analytics tracking
    if (mainVideo) {
        initAnalyticsTracking(mainVideo);
        // Закомментировано, так как теперь используется новый SeekTracker из seek-tracker.js
        // initSeekTracking(mainVideo);
    }
    
    // Hide loading overlay when video is ready to play
    if (mainVideo && loadingOverlay) {
        // Events to check for video loading completion
        ['loadeddata', 'canplay'].forEach(event => {
            mainVideo.addEventListener(event, function() {
                console.log('Video loaded successfully, hiding loading overlay');
                loadingOverlay.style.display = 'none';
            });
        });
        
        // Fallback timeout to hide loading overlay after 10 seconds even if video is still loading
        // This prevents infinite loading display if video is playing but events didn't fire
        setTimeout(function() {
            if (loadingOverlay && loadingOverlay.style.display !== 'none') {
                console.log('Force hiding loading overlay after timeout');
                loadingOverlay.style.display = 'none';
            }
        }, 10000);
    }
    
    // Only for local videos and only if ad player exists and has a valid source
    if (mainVideo && adVideo && adOverlay) {
        // Проверяем, есть ли источник у рекламного видео
        const hasAdSource = adVideo.querySelector('source') && adVideo.querySelector('source').src;
        if (hasAdSource) {
            mainVideo.addEventListener('loadedmetadata', function() {
                var duration = mainVideo.duration;
                if (!duration || isNaN(duration) || duration < 10) return;
                var mid = duration / 2;
                var adPlayed = false;
                
                mainVideo.addEventListener('timeupdate', function() {
                    if (!adPlayed && mainVideo.currentTime > mid) {
                        adPlayed = true;
                        mainVideo.pause();
                        adOverlay.style.display = 'block';
                        adVideo.play();
                    }
                });
                
                adVideo.addEventListener('ended', function() {
                    adOverlay.style.display = 'none';
                    mainVideo.play();
                });
            });
        } else {
            console.log('No ad source found, skipping ad playback');
        }
    }
    
    // Error handling for video player
    if (mainVideo) {
        mainVideo.addEventListener('error', function() {
            console.error('Video playback error:', mainVideo.error);
            const videoId = window.location.pathname.split('/').filter(Boolean).pop();
            reportVideoError(mainVideo, videoId);
        });
    }
}

/**
 * Initialize theater mode functionality
 */
function initTheaterMode() {
    const theaterModeBtn = document.querySelector('.theater-mode-button');
    const videoPageContainer = document.getElementById('videoPageContainer');
    const commentsSection = document.querySelector('.comments-section');
    const sidebarContent = document.querySelector('.sidebar-content');
    const originalParent = sidebarContent ? sidebarContent.parentNode : null;
    
    // Сохраняем ссылку на исходного родителя, если это не комментарии
    if (sidebarContent && originalParent === commentsSection.parentNode) {
        // Сохраняем оригинальное местоположение в DOM
        sidebarContent.setAttribute('data-original-position', Array.from(originalParent.children).indexOf(sidebarContent));
    }
    
    if (theaterModeBtn && videoPageContainer && commentsSection && sidebarContent) {
        theaterModeBtn.addEventListener('click', function() {
            videoPageContainer.classList.toggle('theater-mode');
            
            // При включении театрального режима перемещаем рекомендуемые видео под комментарии
            if (videoPageContainer.classList.contains('theater-mode')) {
                // Изменяем текст и иконку кнопки
                const iconElement = theaterModeBtn.querySelector('i');
                const textElement = theaterModeBtn.querySelector('span');
                
                if (iconElement) {
                    iconElement.classList.remove('fa-expand');
                    iconElement.classList.add('fa-compress');
                }
                
                if (textElement) {
                    textElement.textContent = 'Обычный режим';
                }
                
                // Сохраняем текущего родителя перед перемещением
                if (sidebarContent.parentNode) {
                    sidebarContent.setAttribute('data-theater-parent', '.video-page-container');
                }
                
                // Перемещаем сайдбар под комментарии
                commentsSection.parentNode.insertBefore(sidebarContent, commentsSection.nextSibling);
                console.log('Sidebar moved below comments');
            } else {
                // Возвращаем к обычному виду
                const iconElement = theaterModeBtn.querySelector('i');
                const textElement = theaterModeBtn.querySelector('span');
                
                if (iconElement) {
                    iconElement.classList.remove('fa-compress');
                    iconElement.classList.add('fa-expand');
                }
                
                if (textElement) {
                    textElement.textContent = 'Театральный режим';
                }
                
                // Возвращаем сайдбар на место
                // Возвращаем сайдбар назад в основной контейнер
                videoPageContainer.insertBefore(sidebarContent, videoPageContainer.querySelector('.comments-section'));
                
                console.log('Sidebar returned to original position in container');
            }
        });
    }
}

/**
 * Analytics tracking for video player
 */
function initAnalyticsTracking(videoElement) {
    if (!videoElement) return;
    
    // Get video ID from URL
    const pathParts = window.location.pathname.split('/');
    const videoId = pathParts[pathParts.indexOf('video') + 1];
    if (!videoId) return;
    
    // Variables to track seek behavior
    let lastSeekTime = 0;
    let seekStartPosition = 0;
    let isTracking = false;
    let seekTimeout = null;
    let videoStartTime = Date.now();
    
    // Track start of video view
    videoElement.addEventListener('play', function() {
        videoStartTime = Date.now();
        if (!isTracking) {
            // Only track first play or play after pause
            isTracking = true;
        }
    });
    
    // Track seeking events with merging logic
    videoElement.addEventListener('seeking', function() {
        // Store the position where seek started
        if (!seekStartPosition) {
            seekStartPosition = Math.floor(videoElement.currentTime);
        }
    });
    
    // When seek ends
    videoElement.addEventListener('seeked', function() {
        const currentSeekTime = Date.now();
        const seekEndPosition = Math.floor(videoElement.currentTime);
        
        // Only process seeks that actually changed position
        if (seekStartPosition !== seekEndPosition) {
            // Clear any pending seek tracking
            if (seekTimeout) {
                clearTimeout(seekTimeout);
            }
            
            // If less than 2 seconds have passed since last seek, don't track yet
            // This allows merging multiple seeks within 2 seconds
            if (currentSeekTime - lastSeekTime < 2000) {
                // Schedule tracking after 2 seconds of no seeking
                seekTimeout = setTimeout(() => {
                    // Track the seek with the latest end position
                    trackVideoSeek(videoId, seekStartPosition, seekEndPosition);
                    // Reset tracking variables
                    seekStartPosition = 0;
                    lastSeekTime = 0;
                }, 2000);
            } else {
                // More than 2 seconds since last seek, track immediately
                trackVideoSeek(videoId, seekStartPosition, seekEndPosition);
                seekStartPosition = 0;
            }
            
            lastSeekTime = currentSeekTime;
        }
    });
    
    // Track end of video view when user leaves the page
    window.addEventListener('beforeunload', function() {
        if (isTracking) {
            const viewDuration = Math.floor((Date.now() - videoStartTime) / 1000);
            trackVideoViewEnd(videoId, viewDuration);
        }
    });
    
    // Also track when video is paused for a significant time
    videoElement.addEventListener('pause', function() {
        const pauseStartTime = Date.now();
        const pauseTimeout = setTimeout(() => {
            // If paused for more than 30 seconds, consider the viewing session ended
            if (videoElement.paused) {
                const viewDuration = Math.floor((pauseStartTime - videoStartTime) / 1000);
                trackVideoViewEnd(videoId, viewDuration);
                isTracking = false;
            }
        }, 30000); // 30 seconds
        
        // If video is played again before timeout, clear the timeout
        videoElement.addEventListener('play', function clearPauseTimeout() {
            clearTimeout(pauseTimeout);
            videoElement.removeEventListener('play', clearPauseTimeout);
        });
    });
}

/**
 * Track video seek in analytics
 */
function trackVideoSeek(videoId, fromPosition, toPosition) {
    // Only track if user is authenticated
    if (!document.cookie.includes('sessionid')) return;
    
    const csrfToken = getCsrfToken();
    if (!csrfToken) return;
    
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
        if (!response.ok) {
            console.error('Error tracking video seek');
        }
    })
    .catch(error => {
        console.error('Error tracking video seek:', error);
    });
}

/**
 * Track end of video view in analytics
 */
function trackVideoViewEnd(videoId, duration) {
    // Only track if user is authenticated
    if (!document.cookie.includes('sessionid')) return;
    
    const csrfToken = getCsrfToken();
    if (!csrfToken) return;
    
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
            console.error('Error tracking video view end');
        }
    })
    .catch(error => {
        console.error('Error tracking video view end:', error);
    });
}

/**
 * Get CSRF token from cookies
 */
function getCsrfToken() {
    const cookieValue = document.cookie
        .split('; ')
        .find(row => row.startsWith('csrftoken='))
        ?.split('=')[1];
    return cookieValue;
}

/**
 * Инициализация прямого отслеживания перемоток видео
 */
function initSeekTracking(videoElement) {
    if (!videoElement) {
        console.log('Не удалось инициализировать отслеживание перемоток: элемент видео не найден');
        return;
    }
    
    // Получаем ID видео из URL
    const pathParts = window.location.pathname.split('/');
    const videoIndex = pathParts.indexOf('video');
    if (videoIndex === -1 || !pathParts[videoIndex + 1]) {
        console.log('Не удалось инициализировать отслеживание перемоток: не найден ID видео в URL');
        return;
    }
    
    const videoId = pathParts[videoIndex + 1];
    console.log('Инициализация прямого отслеживания перемоток для видео:', videoId);
    
    // Переменные для отслеживания перемоток
    let seekStartPosition = 0;
    let seekTimeoutId = null;
    
    // Отслеживаем начало перемотки
    videoElement.addEventListener('seeking', function() {
        // Фиксируем начальную позицию перемотки
        if (!seekStartPosition) {
            seekStartPosition = Math.floor(videoElement.currentTime);
            console.log('Начало перемотки с позиции:', seekStartPosition);
        }
    });
    
    // Отслеживаем окончание перемотки
    videoElement.addEventListener('seeked', function() {
        const seekEndPosition = Math.floor(videoElement.currentTime);
        
        // Обрабатываем только перемотки, которые действительно изменили позицию
        if (seekStartPosition !== seekEndPosition) {
            console.log('Перемотка завершена на позиции:', seekEndPosition);
            
            // Очищаем предыдущий таймаут, если он был установлен
            if (seekTimeoutId) {
                clearTimeout(seekTimeoutId);
            }
            
            // Устанавливаем новый таймаут для объединения перемоток
            seekTimeoutId = setTimeout(function() {
                // Отправляем данные о перемотке на сервер
                trackSeekDirectly(videoId, seekStartPosition, seekEndPosition);
                
                // Сбрасываем позицию начала перемотки
                seekStartPosition = 0;
                seekTimeoutId = null;
            }, 2000); // Объединяем перемотки в течение 2 секунд
        }
    });
}

/**
 * Отправка данных о перемотке напрямую на сервер
 */
function trackSeekDirectly(videoId, fromPosition, toPosition) {
    // Проверяем, что пользователь авторизован
    if (!document.cookie.includes('sessionid')) {
        console.log('Не удалось отследить перемотку: пользователь не авторизован');
        return;
    }
    
    // Получаем CSRF-токен
    const csrfToken = getCsrfToken();
    if (!csrfToken) {
        console.log('Не удалось отследить перемотку: не найден CSRF-токен');
        return;
    }
    
    console.log(`Отправка прямой перемотки: video_id=${videoId}, from=${fromPosition}, to=${toPosition}`);
    
    // Отправляем запрос на сервер
    fetch('/direct_seek_log/', {
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
        if (!response.ok) {
            console.error(`Ошибка при отслеживании перемотки: статус ${response.status}`);
            return response.text().then(text => {
                console.error('Текст ошибки:', text);
            });
        } else {
            return response.json().then(data => {
                console.log('Перемотка успешно отслежена:', data);
            });
        }
    })
    .catch(error => {
        console.error('Ошибка при отправке данных о перемотке:', error);
    });
}

/**
 * Document ready function to initialize all video-related functionality
 */
document.addEventListener('DOMContentLoaded', function() {
    // Initialize the video player
    initVideoPlayer();
    
    // Set up like/dislike buttons
    setupInteractionButtons();
});
