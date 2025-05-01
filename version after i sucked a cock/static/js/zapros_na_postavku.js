document.addEventListener('DOMContentLoaded', function () {
    const form = document.getElementById('zapros-form');
    if (!form) {
        console.error('Form with ID "zapros-form" not found');
        return;
    }

    form.addEventListener('submit', async function (event) {
        event.preventDefault();

        const token = localStorage.getItem('access_token');
        if (!token) {
            alert('Please log in to submit a download request');
            window.location.href = '/login';
            return;
        }

        const action = document.getElementById('action-type')?.value || 'single';
        const query = document.getElementById('query')?.value;
        const videoUrl = document.getElementById('video-url')?.value;
        const tags = document.getElementById('tags')?.value?.split(',').map(tag => tag.trim()) || [];
        const channel = document.getElementById('channel')?.value;
        const urls = document.getElementById('urls')?.value?.split('\n').map(url => url.trim()) || [];
        const minViews = parseInt(document.getElementById('min-views')?.value || '0', 10);
        const minDuration = parseInt(document.getElementById('min-duration')?.value || '0', 10);
        const maxDuration = parseInt(document.getElementById('max-duration')?.value || '3600', 10);
        const maxResults = parseInt(document.getElementById('max-results')?.value || '10', 10);

        const data = { type: action };
        if (action === 'search') {
            data.query = query;
            data.minViews = minViews;
            data.minDuration = minDuration;
            data.maxDuration = maxDuration;
            data.maxResults = maxResults;
        } else if (action === 'tags') {
            data.tags = tags;
            data.minViews = minViews;
            data.minDuration = minDuration;
            data.maxDuration = maxDuration;
            data.maxResults = maxResults;
        } else if (action === 'channel') {
            data.channel = channel;
            data.minViews = minViews;
            data.minDuration = minDuration;
            data.maxDuration = maxDuration;
            data.maxResults = maxResults;
        } else if (action === 'single') {
            data.videoUrl = videoUrl;
        } else if (action === 'mass') {
            data.urls = urls;
        }

        try {
            const response = await fetch('/zapros_na_postavku', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'Authorization': `Bearer ${token}`
                },
                body: JSON.stringify(data)
            });

            const result = await response.json();

            if (response.ok) {
                alert(`Download request submitted. Task ID: ${result.task_id}`);
                form.reset();
            } else {
                console.error('Error:', result);
                alert(`Error: ${result.error || 'Failed to submit download request'}`);
                if (response.status === 401 || response.status === 422) {
                    localStorage.removeItem('access_token');
                    window.location.href = '/login';
                }
            }
        } catch (error) {
            console.error('Fetch error:', error);
            alert('An error occurred while submitting the request');
        }
    });
});