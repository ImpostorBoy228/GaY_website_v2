document.addEventListener('DOMContentLoaded', function () {
    const form = document.getElementById('upload-form');
    if (!form) {
        console.error('Form with ID "upload-form" not found');
        return;
    }

    form.addEventListener('submit', async function (event) {
        event.preventDefault();

        const token = localStorage.getItem('access_token');
        if (!token) {
            alert('Please log in to upload a video');
            window.location.href = '/login';
            return;
        }

        const formData = new FormData(form);

        try {
            const response = await fetch('/upload', {
                method: 'POST',
                headers: {
                    'Authorization': `Bearer ${token}`
                },
                body: formData
            });

            if (response.ok) {
                const text = await response.text();
                document.open();
                document.write(text);
                document.close();
            } else {
                const result = await response.json();
                console.error('Error:', result);
                alert(`Error: ${result.error || 'Failed to upload video'}`);
                if (response.status === 401 || response.status === 422) {
                    localStorage.removeItem('access_token');
                    window.location.href = '/login';
                }
            }
        } catch (error) {
            console.error('Fetch error:', error);
            alert('An error occurred while uploading the video');
        }
    });
});