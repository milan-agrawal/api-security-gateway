/* ============================================================
   API SECURITY GATEWAY - USER PANEL JavaScript
   ============================================================ */

(function patchUserPanelFetch() {
    if (window.__userPanelFetchPatched) return;
    window.__userPanelFetchPatched = true;
    const originalFetch = window.fetch.bind(window);
    window.fetch = function(input, init) {
        const url = typeof input === 'string' ? input : (input && input.url) || '';
        const options = init ? Object.assign({}, init) : {};
        if (url.indexOf('http://localhost:8001') === 0) {
            options.credentials = options.credentials || 'include';
        }
        return originalFetch(input, options);
    };
})();

let __userSessionResolved = null;

async function userSessionBootstrap() {
    const response = await fetch('http://localhost:8001/auth/me?panel=user');
    if (!response.ok) throw new Error('Authentication required');
    const session = await response.json();
    localStorage.setItem('userEmail', session.email || '');
    localStorage.setItem('userRole', session.role || '');
    localStorage.setItem('fullName', session.full_name || '');
    __userSessionResolved = session;
    return session;
}

async function userSessionBootstrapWithRetry(retries = 2, delayMs = 250) {
    let lastError = null;
    for (let attempt = 0; attempt <= retries; attempt++) {
        try {
            return await userSessionBootstrap();
        } catch (error) {
            lastError = error;
            if (attempt === retries) break;
            await new Promise((resolve) => setTimeout(resolve, delayMs));
        }
    }
    throw lastError || new Error('Authentication required');
}

// ============================================================
// IMMEDIATE AUTH CHECK - runs before page renders
// ============================================================
window.__userPanelAuthReady = (async function() {
    const urlParams = new URLSearchParams(window.location.search);
    const handoffCode = urlParams.get('handoff');
    const hasLegacyAuthParams = ['token', 'email', 'role', 'fullName'].some((key) => urlParams.has(key));

    // Clean up old query-string auth remnants from the pre-cookie flow.
    if (hasLegacyAuthParams) {
        localStorage.removeItem('token');
        window.history.replaceState({}, document.title, '/index.html' + (window.location.hash || ''));
    }

    if (handoffCode) {
        try {
            const response = await fetch('http://localhost:8001/auth/panel-handoff/exchange', {
                method: 'POST',
                credentials: 'include',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ handoff_code: handoffCode })
            });
            const handoff = await response.json().catch(() => ({}));
            if (!response.ok || !handoff.role) {
                throw new Error((handoff && handoff.detail) || 'Panel handoff failed');
            }

            localStorage.removeItem('token');
            localStorage.setItem('userEmail', handoff.email || '');
            localStorage.setItem('userRole', handoff.role || '');
            localStorage.setItem('fullName', handoff.full_name || '');
            sessionStorage.removeItem('loggedOut');
            window.history.replaceState({}, document.title, '/index.html');
        } catch (_) {
            window.location.replace('http://localhost:3000/login.html');
            return;
        }
    }

    const loggedOut = sessionStorage.getItem('loggedOut');
    
    if (loggedOut === 'true') {
        window.location.replace('http://localhost:3000/login.html');
        return;
    }

    let session;
    try {
        session = await userSessionBootstrapWithRetry();
    } catch (_) {
        window.location.replace('http://localhost:3000/login.html');
        return;
    }

    if (session.role !== 'user') {
        window.location.replace('http://localhost:3000/login.html');
        return;
    }
})();

// Prevent browser back button after logout
window.history.pushState(null, null, window.location.href);
window.addEventListener('popstate', function() {
    window.history.pushState(null, null, window.location.href);
});

// ============================================================
// AUTH FUNCTIONS
// ============================================================

/**
 * Check authentication on every page load (including back button)
 */
function checkAuth() {
    localStorage.removeItem('token');
    const session = __userSessionResolved;
    const userEmail = (session && session.email) || localStorage.getItem('userEmail');
    const userRole = (session && session.role) || localStorage.getItem('userRole');
    const fullName = (session && session.full_name) || localStorage.getItem('fullName');

    if (!userRole) {
        window.location.replace('http://localhost:3000/login.html');
        return;
    }

    if (userRole !== 'user') {
        window.location.replace('http://localhost:3000/login.html');
        return;
    }

    // Update UI with user info
    updateUserDisplay(userEmail, fullName);
}

/**
 * Update user display in the UI
 */
function updateUserDisplay(email, fullName) {
    // Update user email display
    const userEmailEl = document.getElementById('userEmail');
    if (userEmailEl) {
        userEmailEl.textContent = email || 'User';
    }

    // Update user name in sidebar
    const userNameEl = document.getElementById('userName');
    if (userNameEl) {
        userNameEl.textContent = fullName || email?.split('@')[0] || 'User';
    }

    // Update sidebar email
    const sidebarEmailEl = document.getElementById('sidebarEmail');
    if (sidebarEmailEl) {
        sidebarEmailEl.textContent = email || '';
    }

    // Update user avatar initials
    const avatarEl = document.getElementById('userAvatar');
    if (avatarEl) {
        const initials = getInitials(fullName || email || 'U');
        avatarEl.textContent = initials;
        avatarEl.classList.remove('has-image');
    }

    // Fetch avatar from API (fire-and-forget)
    loadSidebarAvatar();
}

/**
 * Fetch user profile to get avatar for sidebar
 */
async function loadSidebarAvatar() {
    try {
        const res = await fetch('http://localhost:8001/user/profile', {
            headers: { 'Content-Type': 'application/json' }
        });
        if (!res.ok) return;
        const data = await res.json();
        const avatarEl = document.getElementById('userAvatar');
        if (avatarEl && data.avatar) {
            avatarEl.innerHTML = `<img src="${data.avatar}" alt="Avatar">`;
            avatarEl.classList.add('has-image');
        }
    } catch (e) {
        // Silent fail — sidebar just shows initials
    }
}

/**
 * Get initials from a name or email
 */
function getInitials(name) {
    if (!name) return 'U';
    
    // If it's an email, use first letter
    if (name.includes('@')) {
        return name[0].toUpperCase();
    }
    
    // Get initials from name
    const parts = name.trim().split(/\s+/);
    if (parts.length >= 2) {
        return (parts[0][0] + parts[parts.length - 1][0]).toUpperCase();
    }
    return parts[0][0].toUpperCase();
}

/**
 * Logout function
 */
function logout() {
    // Set logout flag in sessionStorage (survives page refresh, cleared when browser closes)
    sessionStorage.setItem('loggedOut', 'true');
    
    // Clear authentication data
    localStorage.clear();

    fetch('http://localhost:8001/auth/logout?panel=user', {
        method: 'POST',
        credentials: 'include'
    }).finally(function () {
        // Use replace with logout parameter to trigger port 3000 cleanup
        window.location.replace('http://localhost:3000/login.html?logout=true');
    });
}

// ============================================================
// SIDEBAR FUNCTIONS
// ============================================================

/**
 * Toggle sidebar - no-op on desktop (sidebar always visible)
 * On mobile, acts as hamburger toggle
 */
function toggleSidebar() {
    if (window.innerWidth <= 768) {
        toggleMobileSidebar();
    }
}

/**
 * Toggle mobile sidebar
 */
function toggleMobileSidebar() {
    const sidebar = document.querySelector('.sidebar');
    const overlay = document.getElementById('sidebarOverlay');
    
    if (sidebar) {
        sidebar.classList.toggle('mobile-open');
        if (overlay) {
            overlay.classList.toggle('active');
        }
        document.body.classList.toggle('sidebar-open');
    }
}

/**
 * Close mobile sidebar
 */
function closeMobileSidebar() {
    const sidebar = document.querySelector('.sidebar');
    const overlay = document.getElementById('sidebarOverlay');
    
    if (sidebar) {
        sidebar.classList.remove('mobile-open');
        if (overlay) {
            overlay.classList.remove('active');
        }
        document.body.classList.remove('sidebar-open');
    }
}

/**
 * Initialize sidebar
 */
function initSidebar() {
    const sidebar = document.querySelector('.sidebar');
    
    // Clear any stale collapsed state
    localStorage.removeItem('sidebarCollapsed');
    if (sidebar) {
        sidebar.classList.remove('collapsed');
    }
    
    // Close mobile sidebar on nav item click
    const navItems = document.querySelectorAll('.nav-item');
    navItems.forEach(item => {
        item.addEventListener('click', () => {
            if (window.innerWidth <= 768) {
                closeMobileSidebar();
            }
        });
    });
    
    // Handle window resize - close mobile sidebar when going to desktop
    window.addEventListener('resize', () => {
        if (window.innerWidth > 768) {
            closeMobileSidebar();
        }
    });
}

/**
 * Set active navigation item based on current route
 */
function setActiveNavItem() {
    const hash = window.location.hash || '#dashboard';
    const navItems = document.querySelectorAll('.nav-item[data-route]');
    
    navItems.forEach(item => {
        const route = item.getAttribute('data-route');
        if (`#${route}` === hash) {
            item.classList.add('active');
        } else {
            item.classList.remove('active');
        }
    });
}

// ============================================================
// DROPDOWN FUNCTIONS
// ============================================================

/**
 * Toggle dropdown menu
 */
function toggleDropdown(dropdownId) {
    const dropdown = document.getElementById(dropdownId);
    if (dropdown) {
        dropdown.classList.toggle('open');
    }
}

/**
 * Close all dropdowns when clicking outside
 */
function initDropdowns() {
    document.addEventListener('click', function(e) {
        if (!e.target.closest('.dropdown')) {
            document.querySelectorAll('.dropdown.open').forEach(dropdown => {
                dropdown.classList.remove('open');
            });
        }
    });
}

// ============================================================
// MODAL FUNCTIONS
// ============================================================

/**
 * Open a modal
 */
function openModal(modalId) {
    const modal = document.getElementById(modalId);
    if (modal) {
        modal.classList.add('active');
        document.body.style.overflow = 'hidden';
    }
}

/**
 * Close a modal
 */
function closeModal(modalId) {
    const modal = document.getElementById(modalId);
    if (modal) {
        modal.classList.remove('active');
        document.body.style.overflow = '';
    }
}

/**
 * Initialize modal close on overlay click
 */
function initModals() {
    document.querySelectorAll('.modal-overlay').forEach(overlay => {
        overlay.addEventListener('click', function(e) {
            if (e.target === overlay) {
                overlay.classList.remove('active');
                document.body.style.overflow = '';
            }
        });
    });
}

// ============================================================
// UTILITY FUNCTIONS
// ============================================================

/**
 * Show a toast notification
 */
function showToast(message, type = 'info') {
    // Create toast element
    const toast = document.createElement('div');
    toast.className = `toast toast-${type}`;
    toast.innerHTML = `
        <span class="toast-message">${message}</span>
        <button class="toast-close" onclick="this.parentElement.remove()">&times;</button>
    `;
    
    // Add to container or body
    let container = document.querySelector('.toast-container');
    if (!container) {
        container = document.createElement('div');
        container.className = 'toast-container';
        document.body.appendChild(container);
    }
    
    container.appendChild(toast);
    
    // Auto remove after 5 seconds
    setTimeout(() => {
        toast.remove();
    }, 5000);
}

/**
 * Format date to readable string
 */
function formatDate(dateStr) {
    const date = new Date(dateStr);
    return date.toLocaleDateString('en-US', {
        year: 'numeric',
        month: 'short',
        day: 'numeric',
        hour: '2-digit',
        minute: '2-digit'
    });
}

/**
 * Copy text to clipboard
 */
async function copyToClipboard(text) {
    try {
        await navigator.clipboard.writeText(text);
        showToast('Copied to clipboard!', 'success');
    } catch (err) {
        showToast('Failed to copy', 'error');
    }
}

// ============================================================
// NAVIGATION / ROUTING  
// ============================================================

// Note: navigateTo() function is provided by router.js
// It handles hash-based navigation and page loading

// ============================================================
// EVENT LISTENERS
// ============================================================

// Run auth check on page load
window.addEventListener('DOMContentLoaded', async function() {
    try {
        await window.__userPanelAuthReady;
    } catch (_) {
        return;
    }
    checkAuth();
    initSidebar();
    initDropdowns();
    initModals();
    setActiveNavItem();
    
    // Initialize router for SPA page loading
    if (typeof initRouter === 'function') {
        initRouter();
    }
});

// Re-check auth when page becomes visible (back button)
window.addEventListener('pageshow', function(event) {
    if (event.persisted) {
        checkAuth();
    }
});

// Handle hash changes for navigation
window.addEventListener('hashchange', function() {
    setActiveNavItem();
});
