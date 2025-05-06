document.getElementById('comment-form')?.addEventListener('submit', async function(e) {
    e.preventDefault();
    const form = e.target;
    const textarea = form.querySelector('textarea');
    const text = textarea.value.trim();
    
    if (!text) {
        alert('Комментарий не может быть пустым');
        return;
    }

    try {
        const response = await fetch(window.location.pathname + 'comment/', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/x-www-form-urlencoded',
                'X-CSRFToken': document.querySelector('[name=csrfmiddlewaretoken]').value
            },
            body: new URLSearchParams({
                'text': text
            })
        });

        const data = await response.json();
        
        if (data.success) {
            const commentsList = document.querySelector('.comments-section');
            const newComment = document.createElement('div');
            newComment.className = 'border-b border-gray-200 py-4';
            
            // Determine sentiment indicator
            let sentimentIndicator = '';
            if (data.comment.sentiment === 1.0) {
                sentimentIndicator = '<span class="ml-2 text-xs px-2 py-1 rounded-full bg-green-100 text-green-800">😊 Позитивный</span>';
            } else if (data.comment.sentiment === 0.0) {
                sentimentIndicator = '<span class="ml-2 text-xs px-2 py-1 rounded-full bg-red-100 text-red-800">😞 Негативный</span>';
            } else {
                sentimentIndicator = '<span class="ml-2 text-xs px-2 py-1 rounded-full bg-yellow-100 text-yellow-800">😐 Нейтральный</span>';
            }
            
            newComment.innerHTML = `
                <div class="flex items-start space-x-3">
                    <img src="${data.comment.avatar_url}" 
                         alt="${data.comment.username}" 
                         class="w-10 h-10 rounded-full object-cover">
                    <div class="flex-1">
                        <div class="flex items-center space-x-2">
                            <a href="/channel/${data.comment.user_id}/" 
                               class="font-semibold hover:text-[#DA5552]">
                                ${data.comment.username}
                            </a>
                            <span class="text-sm text-gray-500">
                                Только что
                            </span>
                            ${sentimentIndicator}
                        </div>
                        <p class="mt-1">${data.comment.text}</p>
                    </div>
                </div>
            `;
            
            const firstComment = commentsList.querySelector('.border-b');
            if (firstComment) {
                commentsList.insertBefore(newComment, firstComment);
            } else {
                commentsList.appendChild(newComment);
            }
            textarea.value = '';
        } else {
            alert(data.error || 'Произошла ошибка при добавлении комментария');
        }
    } catch (error) {
        console.error('Error:', error);
        alert('Произошла ошибка при добавлении комментария');
    }
});