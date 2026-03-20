var API_URL = 'http://localhost:8001';

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
    loadUserInfo();
    initializeSidebar();
    initializeRouter();
    initSystemStatus();
});

function setHeaderUserInfo(profile) {
    const fullName = (profile && profile.full_name) || localStorage.getItem('fullName') || 'Admin';
    const userAvatarImage = document.getElementById('userAvatarImage');
    const userAvatarInitials = document.getElementById('userAvatarInitials');
    const userName = document.getElementById('userName');
    const initials = fullName.split(' ').map(n => n[0]).join('').toUpperCase().substring(0, 2) || 'AD';

    if (userAvatarInitials) {
        userAvatarInitials.textContent = initials;
        userAvatarInitials.style.display = '';
    }
    if (userAvatarImage) {
        userAvatarImage.style.display = 'none';
        userAvatarImage.removeAttribute('src');
    }
    if (userName) {
        userName.textContent = fullName;
    }

    if (profile && profile.avatar && userAvatarImage && userAvatarInitials) {
        userAvatarImage.src = profile.avatar;
        userAvatarImage.style.display = 'block';
        userAvatarInitials.style.display = 'none';
    }
}

// Load user information
async function loadUserInfo() {
    const token = localStorage.getItem('token');
    setHeaderUserInfo(null);

    if (!token) return;

    try {
        const resp = await fetch(`${API_URL}/user/profile`, {
            headers: { 'Authorization': `Bearer ${token}` }
        });
        if (!resp.ok) return;

        const data = await resp.json();
        setHeaderUserInfo(data);
    } catch {
        // Keep the initials fallback if profile fetch fails.
    }
}

// Sidebar toggle functionality
function initializeSidebar() {
    const sidebar = document.getElementById('sidebar');
    const sidebarToggle = document.getElementById('sidebarToggle');
    const mobileMenuBtn = document.getElementById('mobileMenuBtn');
    const sidebarOverlay = document.getElementById('sidebarOverlay');
    
    // Desktop sidebar toggle
    if (sidebarToggle && sidebar) {
        sidebarToggle.addEventListener('click', () => {
            sidebar.classList.toggle('collapsed');
            localStorage.setItem('sidebarCollapsed', sidebar.classList.contains('collapsed'));
        });
        
        // Restore sidebar state (only on desktop)
        if (window.innerWidth > 991) {
            const isCollapsed = localStorage.getItem('sidebarCollapsed') === 'true';
            if (isCollapsed) {
                sidebar.classList.add('collapsed');
            }
        }
    }
    
    // Mobile menu toggle
    if (mobileMenuBtn && sidebar) {
        mobileMenuBtn.addEventListener('click', () => {
            sidebar.classList.add('open');
            if (sidebarOverlay) {
                sidebarOverlay.classList.add('active');
            }
            document.body.style.overflow = 'hidden';
        });
    }
    
    // Close sidebar when clicking overlay
    if (sidebarOverlay && sidebar) {
        sidebarOverlay.addEventListener('click', () => {
            closeMobileSidebar();
        });
    }
    
    // Close sidebar when clicking nav items (on mobile)
    const navItems = sidebar?.querySelectorAll('.nav-item');
    navItems?.forEach(item => {
        item.addEventListener('click', () => {
            if (window.innerWidth <= 991) {
                closeMobileSidebar();
            }
        });
    });
    
    // Handle resize
    window.addEventListener('resize', () => {
        if (window.innerWidth > 991) {
            closeMobileSidebar();
        }
    });
    
    // Handle escape key
    document.addEventListener('keydown', (e) => {
        if (e.key === 'Escape' && sidebar?.classList.contains('open')) {
            closeMobileSidebar();
        }
    });
}

// Close mobile sidebar helper
function closeMobileSidebar() {
    const sidebar = document.getElementById('sidebar');
    const sidebarOverlay = document.getElementById('sidebarOverlay');
    
    sidebar?.classList.remove('open');
    sidebarOverlay?.classList.remove('active');
    document.body.style.overflow = '';
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

// Add CSS for SPA loading state
const style = document.createElement('style');
style.textContent = `
    @keyframes spin {
        from { transform: rotate(0deg); }
        to { transform: rotate(360deg); }
    }
    .content-loading {
        display: flex;
        align-items: center;
        justify-content: center;
        min-height: 400px;
        color: var(--text-muted);
        font-size: 16px;
    }
    .content-loading::after {
        content: '';
        width: 24px;
        height: 24px;
        border: 3px solid var(--border-default);
        border-top-color: var(--accent-primary);
        border-radius: 50%;
        margin-left: 12px;
        animation: spin 1s linear infinite;
    }
`;
document.head.appendChild(style);

// ============================================
// SPA ROUTER
// ============================================

let currentRoute = 'dashboard';


// Global SPA flag for userManagement.js to detect
window.isSPAMode = true;

// Initialize Router
function initializeRouter() {
    // Setup nav click handlers
    const navItems = document.querySelectorAll('.nav-item[data-route]');
    navItems.forEach(item => {
        item.addEventListener('click', (e) => {
            e.preventDefault();
            const route = item.getAttribute('data-route');
            navigateTo(route);
        });
    });
    
    // Handle browser back/forward
    window.addEventListener('hashchange', () => {
        const hash = window.location.hash.slice(1) || 'dashboard';
        if (hash !== currentRoute) {
            loadRoute(hash, true);
        }
    });
    
    // Handle initial route from URL hash
    const initialHash = window.location.hash.slice(1) || 'dashboard';
    loadRoute(initialHash, true);
}

// Update active nav item
function updateActiveNav(route) {
    document.querySelectorAll('.nav-item[data-route]').forEach(item => {
        item.classList.remove('active');
        if (item.getAttribute('data-route') === route) {
            item.classList.add('active');
        }
    });
}

// Navigate to route (updates URL and loads content)
function navigateTo(route) {
    if (route === currentRoute) return;
    window.location.hash = route;
    loadRoute(route, true);
}

// Load route content
async function loadRoute(route, updateNav = true) {
    const contentArea = document.getElementById('contentArea');
    if (!contentArea) return;
    
    // Update current route first
    currentRoute = route;
    
    // Update active nav item
    if (updateNav) {
        updateActiveNav(route);
    }
    
    // Use router.js for all pages
    if (typeof loadPagePartial === 'function') {
        await loadPagePartial(route, contentArea);
    }
}



// Update page header
function updatePageHeader(title, subtitle) {
    const titleEl = document.querySelector('.page-title h1');
    const subtitleEl = document.querySelector('.page-subtitle');
    
    if (titleEl) titleEl.textContent = title;
    if (subtitleEl) subtitleEl.textContent = subtitle;
}
// ============================================
// SYSTEM STATUS - Live health polling
// ============================================

let _systemStatusTimer = null;

function initSystemStatus() {
    checkSystemStatus();
    _systemStatusTimer = setInterval(checkSystemStatus, 30000);
}

async function checkSystemStatus() {
    const indicator = document.querySelector('.status-indicator');
    const text = document.querySelector('.status-text');
    if (!indicator || !text) return;

    const token = localStorage.getItem('token');
    if (!token) return;

    try {
        const resp = await fetch(`${API_URL}/admin/system-status`, {
            headers: { 'Authorization': `Bearer ${token}` }
        });

        if (!resp.ok) throw new Error('Request failed');

        const data = await resp.json();

        indicator.classList.remove('online', 'degraded', 'offline');

        if (data.overall === 'operational') {
            indicator.classList.add('online');
            text.textContent = 'All Systems Operational';
        } else if (data.overall === 'degraded') {
            indicator.classList.add('degraded');
            const downServices = Object.entries(data.services)
                .filter(([, s]) => s === 'offline')
                .map(([name]) => name);
            text.textContent = `Degraded: ${downServices.join(', ')}`;
        } else {
            indicator.classList.add('offline');
            text.textContent = 'Systems Offline';
        }
    } catch {
        indicator.classList.remove('online', 'degraded', 'offline');
        indicator.classList.add('offline');
        text.textContent = 'Status Unavailable';
    }
}
