const API_URL = 'http://localhost:8001';

// Handle back/forward navigation (bfcache)
window.addEventListener('pageshow', function(event) {
    if (event.persisted) {
        // Page was loaded from cache via back/forward button
        const token = localStorage.getItem('token');
        const loggedOut = sessionStorage.getItem('loggedOut');
        if (!token || loggedOut === 'true') {
            window.location.replace('http://localhost:3000/login.html');
        }
    }
});

// IMMEDIATE AUTH CHECK - runs before page renders
(function() {
    const urlParams = new URLSearchParams(window.location.search);
    const urlToken = urlParams.get('token');
    const urlEmail = urlParams.get('email');
    const urlRole = urlParams.get('role');  
    const urlFullName = urlParams.get('fullName');

    // If URL has auth params, store them and clean URL
    if (urlToken && urlEmail && urlRole) {
        localStorage.setItem('token', urlToken);
        localStorage.setItem('userEmail', urlEmail);
        localStorage.setItem('userRole', urlRole);
        localStorage.setItem('fullName', urlFullName || '');
        sessionStorage.removeItem('loggedOut');
        window.history.replaceState({}, document.title, '/index.html');
    }

    const token = localStorage.getItem('token');
    const userRole = localStorage.getItem('userRole');
    const loggedOut = sessionStorage.getItem('loggedOut');
    
    // Redirect if logged out
    if (loggedOut === 'true') {
        window.location.replace('http://localhost:3000/login.html');
        return;
    }
    
    // Redirect if no token
    if (!token) {
        window.location.replace('http://localhost:3000/login.html');
        return;
    }
    
    // Redirect if not admin
    if (userRole !== 'admin') {
        window.location.replace('http://localhost:3001/index.html');
        return;
    }
})();

// DOM Ready
document.addEventListener('DOMContentLoaded', function() {
    initializeUI();
    loadUserInfo();
    initializeSidebar();
    startLiveUpdates();
});

// Initialize UI
function initializeUI() {
    // Set current date in logs
    updateLogTimestamps();
}

// Load user information
function loadUserInfo() {
    const email = localStorage.getItem('userEmail') || 'admin@example.com';
    const fullName = localStorage.getItem('fullName') || 'Admin';
    
    // Update user avatar with initials
    const userAvatar = document.getElementById('userAvatar');
    if (userAvatar) {
        const initials = fullName.split(' ').map(n => n[0]).join('').toUpperCase().substring(0, 2);
        userAvatar.textContent = initials || 'AD';
    }
    
    // Update user name
    const userName = document.getElementById('userName');
    if (userName) {
        userName.textContent = fullName;
    }
}

// Sidebar toggle functionality
function initializeSidebar() {
    const sidebar = document.getElementById('sidebar');
    const sidebarToggle = document.getElementById('sidebarToggle');
    
    if (sidebarToggle && sidebar) {
        sidebarToggle.addEventListener('click', () => {
            sidebar.classList.toggle('collapsed');
            localStorage.setItem('sidebarCollapsed', sidebar.classList.contains('collapsed'));
        });
        
        // Restore sidebar state
        const isCollapsed = localStorage.getItem('sidebarCollapsed') === 'true';
        if (isCollapsed) {
            sidebar.classList.add('collapsed');
        }
    }
}

// Logout function
function logout() {
    // Clear this origin's storage (3002)
    localStorage.removeItem('token');
    localStorage.removeItem('userEmail');
    localStorage.removeItem('userRole');
    localStorage.removeItem('fullName');
    sessionStorage.setItem('loggedOut', 'true');
    // Redirect to login with ?logout=true to clear port 3000's localStorage
    window.location.replace('http://localhost:3000/login.html?logout=true');
}

// Refresh data
function refreshData() {
    // Show refresh animation
    const refreshBtn = document.querySelector('.btn-icon[title="Refresh Data"]');
    if (refreshBtn) {
        refreshBtn.style.animation = 'spin 1s ease-in-out';
        setTimeout(() => {
            refreshBtn.style.animation = '';
        }, 1000);
    }
    
    // Update metrics with random values for demo
    updateMetrics();
    
    // Add new log entry
    addNewLogEntry();
}

// Update metrics with simulated data
function updateMetrics() {
    const totalRequests = document.getElementById('totalRequests');
    const threatsBlocked = document.getElementById('threatsBlocked');
    const activeUsers = document.getElementById('activeUsers');
    const avgResponse = document.getElementById('avgResponse');
    
    if (totalRequests) {
        const current = parseInt(totalRequests.textContent.replace(/,/g, ''));
        totalRequests.textContent = (current + Math.floor(Math.random() * 100)).toLocaleString();
    }
    
    if (threatsBlocked) {
        const current = parseInt(threatsBlocked.textContent);
        threatsBlocked.textContent = current + Math.floor(Math.random() * 5);
    }
    
    if (activeUsers) {
        const current = parseInt(activeUsers.textContent);
        activeUsers.textContent = current + Math.floor(Math.random() * 10) - 5;
    }
    
    if (avgResponse) {
        avgResponse.innerHTML = (35 + Math.floor(Math.random() * 20)) + '<span class="metric-unit">ms</span>';
    }
}

// Add new log entry
function addNewLogEntry() {
    const logViewer = document.getElementById('logViewer');
    if (!logViewer) return;
    
    const methods = ['get', 'post', 'put', 'delete'];
    const paths = ['/api/v1/users', '/api/v1/products', '/api/v1/orders', '/api/v1/analytics'];
    const statuses = [
        { code: '200', class: 'success' },
        { code: '201', class: 'success' },
        { code: '401', class: 'danger' },
        { code: '429', class: 'warning' }
    ];
    
    const method = methods[Math.floor(Math.random() * methods.length)];
    const path = paths[Math.floor(Math.random() * paths.length)];
    const status = statuses[Math.floor(Math.random() * statuses.length)];
    const latency = Math.floor(Math.random() * 200) + 10;
    const ip = `${Math.floor(Math.random() * 255)}.${Math.floor(Math.random() * 255)}.${Math.floor(Math.random() * 255)}.${Math.floor(Math.random() * 255)}`;
    
    const now = new Date();
    const time = now.toTimeString().split(' ')[0] + '.' + now.getMilliseconds().toString().padStart(3, '0');
    
    const isCritical = status.class === 'danger';
    const isWarning = status.class === 'warning';
    
    const entry = document.createElement('div');
    entry.className = `log-entry ${isCritical ? 'critical' : isWarning ? 'warning' : ''}`;
    entry.innerHTML = `
        <span class="log-time">${time}</span>
        <span class="log-badge ${status.class}">${status.code}</span>
        <span class="log-method ${method}">${method.toUpperCase()}</span>
        <span class="log-path">${path}</span>
        <span class="log-ip">${ip}</span>
        <span class="log-latency">${latency}ms</span>
        ${isCritical ? '<span class="log-threat">⚠️ Blocked</span>' : ''}
        ${isWarning ? '<span class="log-threat">⚡ Rate Limited</span>' : ''}
    `;
    
    // Add at the top
    logViewer.insertBefore(entry, logViewer.firstChild);
    
    // Remove old entries if too many
    while (logViewer.children.length > 20) {
        logViewer.removeChild(logViewer.lastChild);
    }
    
    // Highlight animation
    entry.style.animation = 'slideIn 300ms ease-out';
}

// Update log timestamps
function updateLogTimestamps() {
    const logEntries = document.querySelectorAll('.log-time');
    const now = new Date();
    
    logEntries.forEach((entry, index) => {
        const time = new Date(now - (index * 1234)); // Stagger times
        entry.textContent = time.toTimeString().split(' ')[0] + '.' + time.getMilliseconds().toString().padStart(3, '0');
    });
}

// Start live updates
function startLiveUpdates() {
    // Update metrics every 5 seconds
    setInterval(() => {
        const totalRequests = document.getElementById('totalRequests');
        if (totalRequests) {
            const current = parseInt(totalRequests.textContent.replace(/,/g, ''));
            totalRequests.textContent = (current + Math.floor(Math.random() * 50) + 10).toLocaleString();
        }
    }, 5000);
    
    // Add random log entries every 10 seconds
    setInterval(() => {
        if (Math.random() > 0.5) {
            addNewLogEntry();
        }
    }, 10000);
}

// Add CSS animation for spin
const style = document.createElement('style');
style.textContent = `
    @keyframes spin {
        from { transform: rotate(0deg); }
        to { transform: rotate(360deg); }
    }
    @keyframes slideIn {
        from { 
            opacity: 0;
            transform: translateY(-10px);
        }
        to {
            opacity: 1;
            transform: translateY(0);
        }
    }
`;
document.head.appendChild(style);
