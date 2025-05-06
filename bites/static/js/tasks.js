document.addEventListener('DOMContentLoaded', function() {
    const taskList = document.getElementById('task-list');
    const socket = new WebSocket(`ws://${window.location.host}/ws/tasks/`);
    
    socket.onmessage = function(e) {
        const data = JSON.parse(e.data);
        if (data.type === 'task_update') {
            updateTaskProgress(data);
        }
    };
    
    socket.onclose = function(e) {
        console.error('WebSocket closed unexpectedly');
    };
    
    function updateTaskProgress(data) {
        const taskElement = document.querySelector(`[data-video-id="${data.video_id}"]`);
        if (!taskElement) return;
        
        // Update status
        const statusElement = taskElement.querySelector('.status');
        if (statusElement) {
            statusElement.textContent = data.status;
            statusElement.className = `status ${data.status.toLowerCase()}`;
        }
        
        // Update progress
        const progressElement = taskElement.querySelector('.progress');
        if (progressElement && data.progress) {
            progressElement.textContent = `${data.progress}%`;
            progressElement.style.width = `${data.progress}%`;
        }
        
        // Update speed
        const speedElement = taskElement.querySelector('.speed');
        if (speedElement && data.speed) {
            speedElement.textContent = data.speed;
        }
        
        // Update ETA
        const etaElement = taskElement.querySelector('.eta');
        if (etaElement && data.eta) {
            etaElement.textContent = data.eta;
        }
        
        // Update error message if any
        if (data.error) {
            const errorElement = taskElement.querySelector('.error');
            if (errorElement) {
                errorElement.textContent = data.error;
                errorElement.style.display = 'block';
            }
        }
    }
    
    // Initial load of tasks
    fetch('/tasks/')
        .then(response => response.json())
        .then(data => {
            if (data.tasks) {
                data.tasks.forEach(task => {
                    const taskElement = createTaskElement(task);
                    taskList.appendChild(taskElement);
                });
            }
        })
        .catch(error => console.error('Error loading tasks:', error));
});

function createTaskElement(task) {
    const div = document.createElement('div');
    div.className = 'task-item';
    div.setAttribute('data-video-id', task.id);
    
    div.innerHTML = `
        <div class="task-header">
            <h3>${task.title}</h3>
            <span class="status ${task.status.toLowerCase()}">${task.status}</span>
        </div>
        <div class="task-progress">
            <div class="progress-bar">
                <div class="progress" style="width: ${task.progress || 0}%">${task.progress || 0}%</div>
            </div>
        </div>
        <div class="task-info">
            <span class="speed">${task.speed || ''}</span>
            <span class="eta">${task.eta || ''}</span>
        </div>
        <div class="error" style="display: none;"></div>
    `;
    
    return div;
} 