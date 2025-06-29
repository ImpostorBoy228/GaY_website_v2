/**
 * Video interaction functionality for like actions
 */

/**
 * Utility function to set button loading state
 * @param {HTMLElement} button - The button element
 * @param {boolean} isLoading - Whether the button is loading
 */
function setButtonLoading(button, isLoading) {
    if (isLoading) {
        button.classList.add('loading');
        button.setAttribute('disabled', 'disabled');
    } else {
        button.classList.remove('loading');
        button.removeAttribute('disabled');
    }
}

/**
 * Utility function to show error toast
 * @param {string} message - Error message to display
 */
function showErrorToast(message) {
    console.error(message);
    // Здесь можно добавить визуальное отображение ошибки, если нужно
}

/**
 * Get cookie by name (for CSRF token)
 * @param {string} name - Cookie name
 * @returns {string} Cookie value
 */
function getCookie(name) {
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
 * Set up interaction buttons (like and subscribe)
 */
function setupInteractionButtons() {
    // Cache DOM elements
    const likeForm = document.getElementById('likeForm');
    const likeButton = document.getElementById('likeBtn');
    const subscribeForm = document.getElementById('subscribeForm');
    const unsubscribeForm = document.getElementById('unsubscribeForm');
    
    // Set up like form handler
    if (likeForm) {
        likeForm.addEventListener('submit', function(event) {
            event.preventDefault();
            console.log('Like form submission intercepted at ' + new Date().toISOString());
            
            if (!likeButton.disabled) {
                // Показываем состояние загрузки
                setButtonLoading(likeButton, true);
                
                // Сохраняем текущее состояние
                const wasActive = likeButton.classList.contains('active');
                const likeCountSpan = likeButton.querySelector('.like-count');
                const likeCount = parseInt(likeCountSpan.textContent);
                
                // Отправляем форму через AJAX
                const formData = new FormData(likeForm);
                
                console.log('Sending like request to: ' + likeForm.action);
                
                fetch(likeForm.action, {
                    method: 'POST',
                    body: formData,
                    credentials: 'same-origin',
                    headers: {
                        'X-Requested-With': 'XMLHttpRequest'
                    }
                })
                .then(response => {
                    console.log('Like response received with status: ' + response.status);
                    if (!response.ok) {
                        throw new Error('Network response was not ok');
                    }
                    return response.json();
                })
                .then(data => {
                    console.log('Server response:', data);
                    
                    // Меняем состояние кнопки на основе ответа сервера
                    if (data.liked) {
                        likeButton.classList.add('active');
                        console.log('Like added successfully');
                    } else {
                        likeButton.classList.remove('active');
                        console.log('Like removed successfully');
                    }
                    
                    // Обновляем счетчик лайков
                    likeCountSpan.textContent = data.likes;
                    
                    // Обновляем рейтинг
                    const ratingValue = document.querySelector('.rating-value');
                    if (ratingValue && data.absolute_rating !== undefined) {
                        ratingValue.textContent = Number(data.absolute_rating).toFixed(1);
                        console.log('Rating updated to:', data.absolute_rating);
                    }
                    
                    console.log('Like action completed successfully');
                })
                .catch(error => {
                    console.error('Error processing like:', error);
                    showErrorToast('Произошла ошибка при обработке лайка');
                    
                    // Восстанавливаем исходное состояние
                    if (wasActive) {
                        likeButton.classList.add('active');
                    } else {
                        likeButton.classList.remove('active');
                    }
                    likeCountSpan.textContent = likeCount;
                })
                .finally(() => {
                    setButtonLoading(likeButton, false);
                    console.log('Like action processing completed at ' + new Date().toISOString());
                });
            }
        });
    }
    
    // Set up subscribe form handler
    if (subscribeForm) {
        setupSubscriptionForm(subscribeForm, true);
    }
    
    // Set up unsubscribe form handler
    if (unsubscribeForm) {
        setupSubscriptionForm(unsubscribeForm, false);
    }
}

/**
 * Setup subscription form (subscribe or unsubscribe)
 * @param {HTMLFormElement} form - The form element
 * @param {boolean} isSubscribe - Whether this is a subscribe or unsubscribe form
 */
function setupSubscriptionForm(form, isSubscribe) {
    const buttonText = isSubscribe ? 'Подписаться' : 'Отписаться';
    const successText = isSubscribe ? 'Вы подписались' : 'Вы отписались';
    const buttonClass = isSubscribe ? 'btn-primary' : 'btn-secondary';
    const iconClass = isSubscribe ? 'fa-bell' : 'fa-bell-slash';
    
    form.addEventListener('submit', function(event) {
        event.preventDefault();
        console.log(`${isSubscribe ? 'Subscribe' : 'Unsubscribe'} form submission intercepted at ${new Date().toISOString()}`);
        
        const button = form.querySelector('.subscribe-btn');
        if (!button || button.disabled) return;
        
        // Показываем состояние загрузки
        setButtonLoading(button, true);
        
        // Отправляем форму через AJAX
        const formData = new FormData(form);
        
        console.log(`Sending ${isSubscribe ? 'subscribe' : 'unsubscribe'} request to: ${form.action}`);
        
        fetch(form.action, {
            method: 'POST',
            body: formData,
            credentials: 'same-origin'
        })
        .then(response => {
            console.log(`Response received with status: ${response.status}`);
            if (!response.ok) {
                throw new Error('Network response was not ok');
            }
            
            // Создаем противоположную форму
            const newForm = document.createElement('form');
            newForm.id = isSubscribe ? 'unsubscribeForm' : 'subscribeForm';
            newForm.className = 'subscribe-form';
            newForm.method = 'post';
            
            // Получаем URL из текущего action, заменяя subscribe на unsubscribe или наоборот
            const newAction = form.action.replace(
                isSubscribe ? 'subscribe' : 'unsubscribe', 
                isSubscribe ? 'unsubscribe' : 'subscribe'
            );
            newForm.action = newAction;
            
            // Добавляем CSRF токен
            const csrfInput = document.createElement('input');
            csrfInput.type = 'hidden';
            csrfInput.name = 'csrfmiddlewaretoken';
            csrfInput.value = getCookie('csrftoken');
            newForm.appendChild(csrfInput);
            
            // Создаем новую кнопку
            const newButton = document.createElement('button');
            newButton.type = 'submit';
            newButton.className = `btn ${!isSubscribe ? 'btn-primary' : 'btn-secondary'} subscribe-btn`;
            
            const icon = document.createElement('i');
            icon.className = `fas ${!isSubscribe ? 'fa-bell' : 'fa-bell-slash'}`;
            newButton.appendChild(icon);
            
            const text = document.createTextNode(` ${!isSubscribe ? 'Подписаться' : 'Отписаться'}`);
            newButton.appendChild(text);
            
            newForm.appendChild(newButton);
            
            // Заменяем текущую форму на новую
            form.parentNode.replaceChild(newForm, form);
            
            // Добавляем обработчик на новую форму
            setupSubscriptionForm(newForm, !isSubscribe);
            
            console.log(`${isSubscribe ? 'Subscription' : 'Unsubscription'} successful`);
        })
        .catch(error => {
            console.error(`Error processing ${isSubscribe ? 'subscription' : 'unsubscription'}:`, error);
            showErrorToast(`Произошла ошибка при ${isSubscribe ? 'подписке' : 'отписке'}`);
            setButtonLoading(button, false);
        });
    });
}
