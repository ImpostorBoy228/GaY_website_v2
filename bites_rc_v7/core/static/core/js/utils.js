/**
 * Core utility functions for Bites application
 */

/**
 * Get cookie value by name
 * @param {string} name - Cookie name
 * @returns {string} Cookie value or empty string
 */
function getCookie(name) {
    let cookieValue = "";
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
 * Display an error toast notification to the user
 * @param {string} message - The error message to display
 * @param {number} duration - Duration in ms to display the toast (default: 3000)
 */
function showErrorToast(message, duration = 3000) {
    const errorToast = document.getElementById('errorToast');
    const errorToastMessage = document.getElementById('errorToastMessage');
    
    if (errorToast && errorToastMessage) {
        // Clear any existing timeout
        if (errorToast._hideTimeout) {
            clearTimeout(errorToast._hideTimeout);
        }
        
        // Set message and show toast
        errorToastMessage.textContent = message;
        errorToast.style.display = 'block';
        
        // Hide the toast after specified duration
        errorToast._hideTimeout = setTimeout(() => {
            errorToast.style.display = 'none';
        }, duration);
    } else {
        // Fallback to console if toast elements not found
        console.error(message);
    }
}

/**
 * Set button loading state with visual indication
 * @param {HTMLElement} button - The button element to update
 * @param {boolean} loading - Whether to set loading state on or off
 */
function setButtonLoading(button, loading) {
    if (!button) return;
    
    if (loading) {
        button.classList.add('loading');
        button.disabled = true;
        // Store original text if not already stored
        if (!button._originalText && button.querySelector('span:not(.fa)')) {
            button._originalText = button.querySelector('span:not(.fa)').textContent;
        }
    } else {
        button.classList.remove('loading');
        button.disabled = false;
        // Restore original text if stored
        if (button._originalText && button.querySelector('span:not(.fa)')) {
            button.querySelector('span:not(.fa)').textContent = button._originalText;
        }
    }
}

/**
 * Report video playback error to the server
 * @param {Object} video - Video element with error details
 * @param {string} videoId - ID of the video
 */
function reportVideoError(video, videoId) {
    const errorDetails = {
        videoId: videoId,
        errorCode: video.error ? video.error.code : 'unknown',
        errorMessage: video.error ? video.error.message : 'unknown',
        timestamp: new Date().toISOString(),
        userAgent: navigator.userAgent
    };
    
    console.log('Reporting error:', errorDetails);
    // Here you could add actual error reporting to server
    alert('Спасибо за сообщение о проблеме! Мы работаем над её устранением.');
}
