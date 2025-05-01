document.addEventListener('DOMContentLoaded', function () {
    const form = document.getElementById('login-form');
    if (!form) {
        console.log('Login form not found on this page');
        return;
    }

    form.addEventListener('submit', async function (event) {
        event.preventDefault();

        const username = document.getElementById('username').value;
        const password = document.getElementById('password').value;

        try {
            const response = await fetch('/login', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify({ username, password })
            });

            const data = await response.json();

            if (response.ok) {
                if (data.access_token && typeof data.access_token === 'string') {
                    localStorage.setItem('access_token', data.access_token);
                    window.location.href = '/dashboard';
                } else {
                    console.error('Invalid access_token:', data.access_token);
                    alert('Login failed: Invalid token received');
                }
            } else {
                console.error('Login error:', data);
                alert(`Login failed: ${data.error || 'Unknown error'}`);
            }
        } catch (error) {
            console.error('Fetch error:', error);
            alert('An error occurred during login');
        }
    });
});