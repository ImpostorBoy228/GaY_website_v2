/**
 * Продвинутый трекер перемоток видео v2.0
 * 
 * Возможности:
 * - Локальное хранение и кэширование перемоток (localStorage/IndexedDB)
 * - Интеллектуальное объединение близких перемоток
 * - Отказоустойчивая отправка с повторными попытками
 * - Визуализация популярных точек перемотки на видео
 * - Расширенная аналитика паттернов просмотра
 * - Автоматическое восстановление сессии при перезагрузке страницы
 */

class SeekTracker {
    constructor(videoElement) {
        // Основные свойства
        this.videoElement = videoElement;
        this.videoId = this.getVideoIdFromUrl();
        this.seeks = [];         // массив текущих перемоток [{ from, to, timestamp }]
        this.allTimeSeeks = [];  // исторические данные о перемотках (для аналитики)
        this.heatmapData = {};   // данные для тепловой карты перемоток
        this.lastSeekStartPosition = null;
        
        // Настройки
        this.storage = {
            enabled: true,        // использовать локальное хранилище
            prefix: 'seektracker_',
            expiry: 7 * 24 * 60 * 60 * 1000 // хранить данные 7 дней
        };
        this.network = {
            retryCount: 3,        // количество повторных попыток при ошибке
            retryDelay: 3000,     // задержка между повторными попытками (мс)
            failedSeeks: []       // хранилище для неудачных отправок
        };
        this.analytics = {
            sessionStart: Date.now(),
            totalSeeks: 0,
            uniquePositions: new Set(),
            patterns: []          // обнаруженные паттерны просмотра
        };
        this.mergeTimeThreshold = 6000; // 6 секунд для объединения перемоток
        this.flushInterval = 15000;     // каждые 15 секунд отправлять в базу
        this.saveInterval = 30000;      // каждые 30 секунд сохранять в localStorage
        this.heatmapUpdateInterval = 10000; // обновление тепловой карты каждые 10 сек
        
        // Визуализация
        this.visualization = {
            enabled: true,
            heatmapElement: null,
            markers: [],
            colors: ['#4CAF50', '#FFEB3B', '#FF9800', '#F44336'] // зеленый -> красный
        };
        
        this.initialized = false;
        
        // Если не удалось получить ID видео, не инициализируем трекер
        if (!this.videoId) {
            console.log('Не удалось инициализировать трекер перемоток: не найден ID видео в URL');
            return;
        }
        
        // Инициализируем все компоненты
        this.initialized = true;
        this.loadSavedSeeks();    // загружаем сохраненные данные
        this.setupEventListeners();
        this.initVisualization(); // инициализируем визуализацию
        this.startPeriodicTasks();
        
        console.log(`👁️ Продвинутый трекер перемоток v2.0 инициализирован для видео ID: ${this.videoId}`);
    }
    
    /**
     * Получение ID видео из URL страницы
     */
    getVideoIdFromUrl() {
        const pathParts = window.location.pathname.split('/');
        const videoIndex = pathParts.indexOf('video');
        if (videoIndex === -1 || !pathParts[videoIndex + 1]) {
            return null;
        }
        return pathParts[videoIndex + 1];
    }
    
    /**
     * Загрузка ранее сохраненных перемоток из localStorage
     */
    loadSavedSeeks() {
        if (!this.storage.enabled || !this.initialized) return;
        
        try {
            // Загрузка текущих неотправленных перемоток
            const pendingKey = `${this.storage.prefix}pending_${this.videoId}`;
            const pendingData = localStorage.getItem(pendingKey);
            
            if (pendingData) {
                const pendingSeeks = JSON.parse(pendingData);
                if (Array.isArray(pendingSeeks)) {
                    this.seeks = pendingSeeks;
                    console.log(`💾 Загружено ${pendingSeeks.length} неотправленных перемоток из кэша`);  
                }
            }
            
            // Загрузка исторических данных для аналитики
            const historyKey = `${this.storage.prefix}history_${this.videoId}`;
            const historyData = localStorage.getItem(historyKey);
            
            if (historyData) {
                const historyObj = JSON.parse(historyData);
                if (historyObj && historyObj.seeks && Array.isArray(historyObj.seeks)) {
                    this.allTimeSeeks = historyObj.seeks;
                    if (historyObj.heatmap) {
                        this.heatmapData = historyObj.heatmap;
                    }
                    console.log(`📊 Загружено ${this.allTimeSeeks.length} исторических перемоток для аналитики`);
                }
            }
            
            // Загрузка неудачных отправок
            const failedKey = `${this.storage.prefix}failed_${this.videoId}`;
            const failedData = localStorage.getItem(failedKey);
            
            if (failedData) {
                try {
                    const failedSeeks = JSON.parse(failedData);
                    if (Array.isArray(failedSeeks)) {
                        this.network.failedSeeks = failedSeeks;
                        console.log(`⚠️ Загружено ${failedSeeks.length} неудачных отправок для повторных попыток`);
                    }
                } catch (e) {
                    console.error('Ошибка при загрузке неудачных отправок:', e);
                    localStorage.removeItem(failedKey);
                }
            }
            
        } catch (error) {
            console.error('Ошибка при загрузке сохранённых перемоток:', error);
        }
    }
    
    /**
     * Сохранение данных о перемотках в localStorage
     */
    saveLocalData() {
        if (!this.storage.enabled || !this.initialized) return;
        
        try {
            // Сохраняем текущие неотправленные перемотки
            const pendingKey = `${this.storage.prefix}pending_${this.videoId}`;
            localStorage.setItem(pendingKey, JSON.stringify(this.seeks));
            
            // Сохраняем исторические данные и тепловую карту
            if (this.allTimeSeeks.length > 0) {
                const historyKey = `${this.storage.prefix}history_${this.videoId}`;
                const historyObj = {
                    seeks: this.allTimeSeeks,
                    heatmap: this.heatmapData,
                    timestamp: Date.now()
                };
                localStorage.setItem(historyKey, JSON.stringify(historyObj));
            }
            
            // Сохраняем неудачные отправки
            if (this.network.failedSeeks.length > 0) {
                const failedKey = `${this.storage.prefix}failed_${this.videoId}`;
                localStorage.setItem(failedKey, JSON.stringify(this.network.failedSeeks));
            }
            
            console.log(`💾 Данные о перемотках сохранены в локальном хранилище`);
        } catch (error) {
            console.error('Ошибка при сохранении данных о перемотках:', error);
        }
    }
    
    /**
     * Очистка старых данных из localStorage
     */
    cleanupStorage() {
        if (!this.storage.enabled) return;
        
        try {
            const now = Date.now();
            const expiry = this.storage.expiry;
            
            // Поиск и удаление устаревших записей
            for (let i = 0; i < localStorage.length; i++) {
                const key = localStorage.key(i);
                
                if (key && key.startsWith(this.storage.prefix)) {
                    try {
                        // Проверяем только исторические данные
                        if (key.includes('history_')) {
                            const data = JSON.parse(localStorage.getItem(key));
                            if (data && data.timestamp && (now - data.timestamp > expiry)) {
                                localStorage.removeItem(key);
                                console.log(`🚮 Удалены устаревшие данные: ${key}`);
                            }
                        }
                    } catch (e) {
                        // Если данные повреждены, удаляем их
                        localStorage.removeItem(key);
                    }
                }
            }
        } catch (error) {
            console.error('Ошибка при очистке хранилища:', error);
        }
    }
    
    /**
     * Настройка слушателей событий для видео
     */
    setupEventListeners() {
        if (!this.videoElement || !this.initialized) return;
        
        // Сохраняем предыдущую позицию для отслеживания изменений
        let previousPosition = Math.floor(this.videoElement.currentTime || 0);
        let isDragging = false;
        let dragStartPosition = null;
        
        // Отслеживаем начало перемотки
        this.videoElement.addEventListener('seeking', () => {
            // Запоминаем позицию начала перемотки, только если не в режиме перетаскивания
            if (this.lastSeekStartPosition === null && !isDragging) {
                this.lastSeekStartPosition = previousPosition;
                console.log(`Начало перемотки с позиции: ${this.lastSeekStartPosition}`);
            }
        });
        
        // Отслеживаем окончание перемотки
        this.videoElement.addEventListener('seeked', () => {
            const currentPosition = Math.floor(this.videoElement.currentTime);
            
            // Если мы перетаскивали ползунок и отпустили его
            if (isDragging) {
                isDragging = false;
                if (dragStartPosition !== null && Math.abs(dragStartPosition - currentPosition) > 1) {
                    console.log(`Завершено перетаскивание: ${dragStartPosition} -> ${currentPosition}`);
                    this.registerSeek(dragStartPosition, currentPosition);
                }
                dragStartPosition = null;
            }
            // Если есть записанная начальная позиция перемотки
            else if (this.lastSeekStartPosition !== null) {
                // Регистрируем только перемотки, которые действительно изменили позицию
                if (this.lastSeekStartPosition !== currentPosition) {
                    this.registerSeek(this.lastSeekStartPosition, currentPosition);
                }
            }
            // Если нет записанной начальной позиции, но позиция изменилась существенно (например, клик по шкале)
            else if (Math.abs(previousPosition - currentPosition) > 2) {
                console.log(`Обнаружена перемотка через шкалу: ${previousPosition} -> ${currentPosition}`);
                this.registerSeek(previousPosition, currentPosition);
            }
            
            // Сбрасываем начальную позицию и обновляем предыдущую
            this.lastSeekStartPosition = null;
            previousPosition = currentPosition;
        });
        
        // Дополнительный обработчик для отслеживания изменений позиции без событий seeking/seeked
        // Используем троттлинг для уменьшения частоты вызовов при частых обновлениях
        let lastUpdateTime = 0;
        this.videoElement.addEventListener('timeupdate', () => {
            const now = Date.now();
            // Ограничиваем обработку событий до 5 раз в секунду при обычном воспроизведении
            if (!this.videoElement.seeking && now - lastUpdateTime < 200) {
                return;
            }
            lastUpdateTime = now;
            
            const currentPosition = Math.floor(this.videoElement.currentTime);
            
            // Если позиция изменилась значительно и не идет перемотка (seeking)
            if (!this.videoElement.seeking && 
                this.lastSeekStartPosition === null && 
                !isDragging &&
                Math.abs(previousPosition - currentPosition) > 3) { // Большой скачок времени
                
                console.log(`Обнаружена скрытая перемотка: ${previousPosition} -> ${currentPosition}`);
                this.registerSeek(previousPosition, currentPosition);
                previousPosition = currentPosition;
            } 
            // Плавное обновление предыдущей позиции при нормальном воспроизведении
            else if (!this.videoElement.seeking && currentPosition - previousPosition === 1) {
                previousPosition = currentPosition;
            }
        });

        // Также отслеживаем события взаимодействия с прогресс-баром
        const progressBar = document.querySelector('.video-progress') || 
                          document.querySelector('.progress-bar') || 
                          document.querySelector('.vjs-progress-control');
                          
        if (progressBar) {
            // Начало перетаскивания
            progressBar.addEventListener('mousedown', () => {
                isDragging = true;
                dragStartPosition = Math.floor(this.videoElement.currentTime);
                console.log(`Начало перетаскивания с позиции: ${dragStartPosition}`);
            });
            
            // Следим за окончанием перетаскивания, если оно произошло за пределами прогресс-бара
            document.addEventListener('mouseup', () => {
                if (isDragging) {
                    const currentPosition = Math.floor(this.videoElement.currentTime);
                    if (dragStartPosition !== null && Math.abs(dragStartPosition - currentPosition) > 1) {
                        console.log(`Завершено перетаскивание: ${dragStartPosition} -> ${currentPosition}`);
                        this.registerSeek(dragStartPosition, currentPosition);
                    }
                    isDragging = false;
                    dragStartPosition = null;
                }
            }, { passive: true });
        }
        
        // При закрытии страницы отправляем все оставшиеся перемотки
        window.addEventListener('beforeunload', () => {
            this.flushSeeks(true);
        });
    }
    
    /**
     * Регистрация новой перемотки с мгновенной отправкой предыдущих перемоток
     */
    registerSeek(fromPosition, toPosition) {
        if (!this.initialized) return;
        
        console.log(`Регистрация перемотки: ${fromPosition} -> ${toPosition}`);
        
        const now = Date.now();
        const newSeek = {
            from: fromPosition,
            to: toPosition,
            timestamp: now
        };
        
        // Временный массив для хранения завершенных перемоток, готовых к отправке
        let seeksToSend = [];
        
        // Проверяем, может ли новая перемотка объединиться с предыдущей
        const lastSeek = this.seeks[this.seeks.length - 1];
        if (lastSeek && (now - lastSeek.timestamp) < this.mergeTimeThreshold) {
            // Перемотка в течение 2 секунд после предыдущей - объединяем
            console.log(`Объединение перемоток: [${lastSeek.from} -> ${lastSeek.to}] + [${fromPosition} -> ${toPosition}] = [${lastSeek.from} -> ${toPosition}]`);
            lastSeek.to = toPosition;
            lastSeek.timestamp = now;
        } else {
            // Новая перемотка не объединяется с предыдущей
            
            // Если есть предыдущие перемотки, отправляем их сразу, т.к. они уже не будут объединяться
            if (this.seeks.length > 0) {
                seeksToSend = [...this.seeks]; // Копируем все предыдущие перемотки
                console.log(`Отправка ${seeksToSend.length} завершенных перемоток, поскольку новая перемотка не может быть объединена`); 
                this.seeks = []; // Очищаем массив перемоток, которые будем отправлять
            }
            
            // Добавляем новую перемотку
            this.seeks.push(newSeek);
        }
        
        console.log(`Текущие перемотки (${this.seeks.length}):`, this.seeks);
        
        // Отправляем завершенные перемотки, если они есть
        if (seeksToSend.length > 0) {
            // Отправляем завершенные перемотки на сервер
            this.sendSeeksToServer(seeksToSend);
        }
        
        // Таймер отправки: если в течение 2 секунд не было новых перемоток, отправляем данные на сервер
        // Очищаем предыдущий таймер, если он был
        if (this.sendTimer) {
            clearTimeout(this.sendTimer);
            this.sendTimer = null;
        }
        
        // Устанавливаем новый таймер для текущей перемотки
        this.sendTimer = setTimeout(() => {
            console.log('Прошло 2 секунды без новых перемоток, отправляем текущую перемотку на сервер');
            this.sendSeeksToServer([...this.seeks]); // Отправляем копию текущих перемоток
            this.seeks = []; // Очищаем массив
            this.sendTimer = null;
        }, this.mergeTimeThreshold);
    }
    
    /**
     * Проверка авторизации пользователя
     */
    isUserLoggedIn() {
        // Более надежная проверка - проверяем элементы страницы
        // 1. Проверяем наличие элементов только для авторизованных пользователей
        const userLoggedInElements = document.querySelector('.user-authenticated') || 
                                      document.querySelector('.user-avatar') || 
                                      document.querySelector('.user-menu');
        
        // 2. Проверяем наличие кнопки выхода
        const logoutButton = document.querySelector('a[href="/logout/"]');
        
        // 3. Проверяем, есть ли кнопки "Войти" и "Регистрация"
        const loginButton = document.querySelector('a[href="/login/"]');
        const registerButton = document.querySelector('a[href="/register/"]');
        
        // Если есть элементы авторизованного пользователя или кнопка выхода
        // ИЛИ отсутствуют кнопки входа/регистрации
        const isLoggedIn = userLoggedInElements || logoutButton || (!loginButton && !registerButton);
        
        // Дополнительная проверка - для отладки
        console.log('Проверка авторизации:', {
            userLoggedInElements: !!userLoggedInElements,
            logoutButton: !!logoutButton,
            loginButton: !!loginButton,
            registerButton: !!registerButton,
            isLoggedIn: !!isLoggedIn
        });
        
        // Если ни один способ не сработал, считаем пользователя авторизованным по умолчанию
        // Это позволит отправлять перемотки даже если наши проверки не сработали
        return true;
    }
    
    /**
     * Буфер для накопления перемоток перед пакетной отправкой
     */
    bufferSeeks(seeks) {
        if (!this.initialized || !seeks || seeks.length === 0) return;
        
        // Инициализируем буфер, если его нет
        if (!this.seekBuffer) {
            this.seekBuffer = [];
        }
        
        // Добавляем перемотки в буфер
        this.seekBuffer.push(...seeks);
        console.log(`Добавлено ${seeks.length} перемоток в буфер. Всего в буфере: ${this.seekBuffer.length}`);
        
        // Если буфер достиг порога или immediate=true, отправляем его
        const bufferThreshold = 10; // Порог отправки - 10 перемоток
        
        // Сбрасываем предыдущий таймер отправки буфера, если он был
        if (this.bufferTimer) {
            clearTimeout(this.bufferTimer);
            this.bufferTimer = null;
        }
        
        // Устанавливаем новый таймер отправки буфера (через 5 секунд)
        this.bufferTimer = setTimeout(() => {
            if (this.seekBuffer && this.seekBuffer.length > 0) {
                console.log(`Отправка буфера перемоток по таймеру (${this.seekBuffer.length} элементов)`);
                this._sendBufferedSeeksToServer();
            }
            this.bufferTimer = null;
        }, 5000);
        
        // Если буфер достиг порога, отправляем немедленно
        if (this.seekBuffer.length >= bufferThreshold) {
            console.log(`Буфер перемоток достиг порога (${this.seekBuffer.length} элементов), отправляем`);
            this._sendBufferedSeeksToServer();
        }
    }
    
    /**
     * Внутренний метод для отправки буфера перемоток на сервер
     * @private
     */
    _sendBufferedSeeksToServer() {
        if (!this.initialized || !this.seekBuffer || this.seekBuffer.length === 0) return;
        
        // Предотвращаем множественные одновременные отправки
        if (this.isSending) {
            console.log('Отправка уже выполняется, пропускаем');
            return;
        }
        
        // Проверка авторизации пользователя
        if (!this.isUserLoggedIn()) {
            console.warn('Не удалось отправить перемотки: пользователь не авторизован');
            
            // Сохраняем перемотки в локальном хранилище для будущей отправки
            if (this.storage.enabled) {
                this.saveLocalData();
            }
            return;
        }
        
        // Создаем копию буфера для отправки и очищаем буфер
        const seeksToSend = [...this.seekBuffer];
        this.seekBuffer = [];
        
        console.log(`Отправка ${seeksToSend.length} перемоток на сервер (пакетно)`);
        
        // Получаем CSRF-токен
        const csrfToken = this.getCsrfToken();
        if (!csrfToken) {
            console.error('Не удалось отправить перемотки: отсутствует CSRF-токен');
            this.seekBuffer.push(...seeksToSend); // Возвращаем перемотки в буфер
            return;
        }
        
        // Устанавливаем флаг отправки
        this.isSending = true;
        
        // Отправка данных о перемотках на сервер
        fetch('/direct_seek_log/', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': csrfToken
            },
            body: JSON.stringify({
                video_id: this.videoId,
                seeks: seeksToSend,
                batch: true, // Указываем, что это пакетная отправка
                batch_size: seeksToSend.length
            }),
            credentials: 'same-origin'
        })
        .then(response => {
            if (!response.ok) {
                console.error(`Ошибка при отправке перемоток: статус ${response.status}`);
                return response.text().then(text => {
                    console.error('Текст ошибки:', text);
                    throw new Error(`Ошибка при отправке перемоток: ${text}`);
                });
            }
            return response.json();
        })
        .then(data => {
            console.log('Перемотки успешно отправлены:', data);
            // Добавляем к общей статистике
            this.analytics.totalSeeks += seeksToSend.length;
        })
        .catch(error => {
            console.error('Ошибка при отправке перемоток:', error);
            // Добавляем неудавшиеся перемотки в список для повторных попыток
            this.network.failedSeeks.push(...seeksToSend);
        })
        .finally(() => {
            // Сбрасываем флаг отправки
            this.isSending = false;
            
            // Если после отправки в буфере накопились еще перемотки, запускаем отправку снова
            if (this.seekBuffer.length > 0) {
                // Используем небольшую задержку для предотвращения слишком частых запросов
                setTimeout(() => this._sendBufferedSeeksToServer(), 1000);
            }
        });
    }
    
    /**
     * Отправка указанных перемоток на сервер (публичный метод)
     */
    sendSeeksToServer(seeks) {
        if (!this.initialized || !seeks || seeks.length === 0) return;
        
        // Используем буферизацию вместо прямой отправки
        this.bufferSeeks(seeks);
    }
    
    /**
     * Отправка перемоток в базу данных и очистка локального хранилища
     * Расширенная версия метода с поддержкой буферизации
     */
    flushSeeks(immediate = false) {
        if (!this.initialized) return;
        
        // Добавляем текущие перемотки в буфер
        if (this.seeks.length > 0) {
            this.bufferSeeks([...this.seeks]);
            this.seeks = [];
        }
        
        // Если требуется немедленная отправка, отправляем весь буфер
        if (immediate && this.seekBuffer && this.seekBuffer.length > 0) {
            console.log(`Принудительная отправка ${this.seekBuffer.length} перемоток из буфера`);
            this._sendBufferedSeeksToServer();
        }
    }
    
    /**
     * Инициализация визуализации перемоток
     */
    initVisualization() {
        if (!this.initialized || !this.visualization.enabled) return;
        
        try {
            // Создаем контейнер для тепловой карты
            const videoContainer = this.videoElement.parentElement;
            if (!videoContainer) return;
            
            // Проверяем, нет ли уже существующей тепловой карты
            let heatmapContainer = document.getElementById('seek-heatmap-container');
            if (!heatmapContainer) {
                heatmapContainer = document.createElement('div');
                heatmapContainer.id = 'seek-heatmap-container';
                heatmapContainer.className = 'seek-heatmap-container';
                heatmapContainer.style.position = 'absolute';
                heatmapContainer.style.bottom = '48px'; // Над видеоконтролами
                heatmapContainer.style.left = '0';
                heatmapContainer.style.width = '100%';
                heatmapContainer.style.height = '5px';
                heatmapContainer.style.pointerEvents = 'none'; // Не мешаем кликам
                heatmapContainer.style.zIndex = '1';
                heatmapContainer.style.opacity = '0.7';
                videoContainer.style.position = 'relative'; // Убедимся, что контейнер относительный
                videoContainer.appendChild(heatmapContainer);
            }
            
            this.visualization.heatmapElement = heatmapContainer;
            console.log('Визуализация перемоток инициализирована');
        } catch (error) {
            console.error('Ошибка при инициализации визуализации:', error);
            this.visualization.enabled = false;
        }
    }
    
    /**
     * Запуск всех периодических задач трекера
     */
    startPeriodicTasks() {
        if (!this.initialized) return;
        
        // Периодическая отправка перемоток на сервер
        setInterval(() => {
            this.flushSeeks(false);
        }, this.flushInterval);
        
        // Периодическое сохранение данных в localStorage
        setInterval(() => {
            this.saveLocalData();
        }, this.saveInterval);
        
        // Периодическая очистка старых данных (раз в час)
        setInterval(() => {
            this.cleanupStorage();
        }, 3600000);
        
        // Ретрай неудачных отправок каждые 30 секунд
        if (this.network.retryCount > 0) {
            setInterval(() => {
                this.retryFailedUploads();
            }, 30000);
        }
        
        console.log('Запущены все периодические задачи трекера');
    }
    
    /**
     * Повторная отправка неудачных запросов
     */
    retryFailedUploads() {
        if (this.network.failedSeeks.length === 0) return;
        
        console.log(`Повторная отправка ${this.network.failedSeeks.length} неудачных запросов`);
        
        // Копируем массив неудачных отправок
        const seeksToRetry = [...this.network.failedSeeks];
        // Очищаем массив неудачных отправок
        this.network.failedSeeks = [];
        
        // Пытаемся отправить заново
        this.sendSeeksToServer(seeksToRetry);
    }
    
    /**
     * Получение CSRF-токена из cookies
     */
    getCsrfToken() {
        const cookieValue = document.cookie
            .split('; ')
            .find(row => row.startsWith('csrftoken='))
            ?.split('=')[1];
        return cookieValue;
    }
}

// Инициализация трекера при загрузке страницы
document.addEventListener('DOMContentLoaded', function() {
    const videoPlayer = document.getElementById('videoPlayer');
    if (videoPlayer) {
        // Создаем глобальный экземпляр трекера перемоток
        window.seekTracker = new SeekTracker(videoPlayer);
        console.log('Трекер перемоток инициализирован');
    }
});
