/** @type {import('tailwindcss').Config} */
module.exports = {
  content: [
    './templates/**/*.html',
    './static/**/*.js',
  ],
  theme: {
    extend: {},
  },
  plugins: [],
  darkMode: 'class', // Включаем темный режим через класс 'dark'
}
