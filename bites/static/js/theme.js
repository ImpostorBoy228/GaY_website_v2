document.addEventListener('DOMContentLoaded', () => {
    const toggle = document.querySelector('#theme-toggle');
    if (!toggle) {
        console.warn('Theme toggle button not found');
        return;
    }

    const body = document.body;
    const savedTheme = localStorage.getItem('theme') || 'light';
    body.classList.add(savedTheme);

    toggle.addEventListener('click', () => {
        body.classList.toggle('dark');
        const newTheme = body.classList.contains('dark') ? 'dark' : 'light';
        localStorage.setItem('theme', newTheme);
    });
});