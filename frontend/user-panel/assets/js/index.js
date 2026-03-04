/* ============================================================
   API SECURITY GATEWAY - USER PANEL JavaScript
   ============================================================ */

// ============================================================
// IMMEDIATE AUTH CHECK - runs before page renders
// ============================================================
(function() {
    // First, check URL parameters for auth data from redirect
    const urlParams = new URLSearchParams(window.location.search);
    const urlToken = urlParams.get('token');
    const urlEmail = urlParams.get('email');
    const urlRole = urlParams.get('role');
    const urlFullName = urlParams.get('fullName');

    // If URL has auth data, store it in localStorage immediately
    if (urlToken && urlEmail && urlRole) {
        localStorage.setItem('token', urlToken);
        localStorage.setItem('userEmail', urlEmail);
        localStorage.setItem('userRole', urlRole);
        localStorage.setItem('fullName', urlFullName || '');
        
        // Clear logout flag when logging in
        sessionStorage.removeItem('loggedOut');
        
        // Clean URL by removing parameters
        window.history.replaceState({}, document.title, '/index.html');
    }

    // Now check localStorage
    const token = localStorage.getItem('token');
    const userRole = localStorage.getItem('userRole');
    const loggedOut = sessionStorage.getItem('loggedOut');
    
    // If user logged out in this session, block access
    if (loggedOut === 'true') {
        window.location.replace('http://localhost:3000/login.html');
        return;
    }
    
    // If no token, redirect immediately
    if (!token) {
        window.location.replace('http://localhost:3000/login.html');
        return;
    }

    // Check if user has correct role
    if (userRole !== 'user') {
        alert('Access denied. This panel is for users only.');
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
    // Check URL parameters first (from redirect)
    const urlParams = new URLSearchParams(window.location.search);
    const urlToken = urlParams.get('token');
    const urlEmail = urlParams.get('email');
    const urlRole = urlParams.get('role');
    const urlFullName = urlParams.get('fullName');

    // If URL has auth data, store it in localStorage and clean URL
    if (urlToken && urlEmail && urlRole) {
        localStorage.setItem('token', urlToken);
        localStorage.setItem('userEmail', urlEmail);
        localStorage.setItem('userRole', urlRole);
        localStorage.setItem('fullName', urlFullName || '');
        
        // Clean URL by removing parameters
        window.history.replaceState({}, document.title, '/index.html');
    }

    // Now check localStorage
    const token = localStorage.getItem('token');
    const userEmail = localStorage.getItem('userEmail');
    const userRole = localStorage.getItem('userRole');
    const fullName = localStorage.getItem('fullName');

    if (!token) {
        window.location.replace('http://localhost:3000/login.html');
        return;
    }

    // Check if user has correct role
    if (userRole !== 'user') {
        alert('Access denied. This panel is for users only.');
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
    
    // Use replace with logout parameter to trigger port 3000 cleanup
    window.location.replace('http://localhost:3000/login.html?logout=true');
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
window.addEventListener('DOMContentLoaded', function() {
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
