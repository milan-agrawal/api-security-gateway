/* ============================================================
   API SECURITY GATEWAY - USER PANEL ROUTER
   SPA Router with HTML partial loading
   ============================================================ */

// Page configuration
const routes = {
    'dashboard': {
        title: 'Dashboard',
        file: 'pages/dashboard.html',
        breadcrumb: 'Dashboard'
    },
    'features': {
        title: 'Features & Specifications',
        file: 'pages/features.html',
        breadcrumb: 'Features'
    },
    'system-status': {
        title: 'System Status',
        file: 'pages/system-status.html',
        breadcrumb: 'System Status'
    },
    'api-keys': {
        title: 'API Keys',
        file: 'pages/api-keys.html',
        breadcrumb: 'API Keys'
    },
    'key-permissions': {
        title: 'Key Permissions',
        file: 'pages/key-permissions.html',
        breadcrumb: 'Key Permissions'
    },
    'usage-plans': {
        title: 'Usage Plans',
        file: 'pages/usage-plans.html',
        breadcrumb: 'Usage Plans'
    },
    'webhooks': {
        title: 'Webhooks & Alerts',
        file: 'pages/webhooks.html',
        breadcrumb: 'Webhooks & Alerts'
    },
    'documentation': {
        title: 'Documentation',
        file: 'pages/documentation.html',
        breadcrumb: 'Documentation'
    },
    'api-reference': {
        title: 'API Reference',
        file: 'pages/api-reference.html',
        breadcrumb: 'API Reference'
    },
    'api-sandbox': {
        title: 'API Sandbox',
        file: 'pages/api-sandbox.html',
        breadcrumb: 'API Sandbox'
    },
    'sdk-downloads': {
        title: 'SDK Downloads',
        file: 'pages/sdk-downloads.html',
        breadcrumb: 'SDK Downloads'
    },
    'error-codes': {
        title: 'Error Codes',
        file: 'pages/error-codes.html',
        breadcrumb: 'Error Codes'
    },
    'security-logs': {
        title: 'Security Logs',
        file: 'pages/security-logs.html',
        breadcrumb: 'Security Logs'
    },
    'security-wiki': {
        title: 'Security Wiki',
        file: 'pages/security-wiki.html',
        breadcrumb: 'Security Wiki'
    },
    'appeal': {
        title: 'Appeal Portal',
        file: 'pages/appeal.html',
        breadcrumb: 'Appeal Portal'
    },
    'profile': {
        title: 'Profile & MFA',
        file: 'pages/profile.html',
        breadcrumb: 'Profile & MFA'
    },
    'sessions': {
        title: 'Active Sessions',
        file: 'pages/sessions.html',
        breadcrumb: 'Active Sessions'
    },
    'data-export': {
        title: 'Data Export',
        file: 'pages/data-export.html',
        breadcrumb: 'Data Export'
    },
    'support': {
        title: 'Support',
        file: 'pages/support.html',
        breadcrumb: 'Support'
    },
    'troubleshooting': {
        title: 'Troubleshooting',
        file: 'pages/troubleshooting.html',
        breadcrumb: 'Troubleshooting'
    },
    'privacy': {
        title: 'Privacy & Terms',
        file: 'pages/privacy.html',
        breadcrumb: 'Privacy & Terms'
    }
};

// Default route
const DEFAULT_ROUTE = 'dashboard';

// Page container element
let pageContainer = null;

// Page cache for performance
const pageCache = {};

/**
 * Initialize the router
 */
function initRouter() {
    pageContainer = document.getElementById('page-container');
    
    if (!pageContainer) {
        console.error('Page container not found');
        return;
    }

    // Listen for hash changes
    window.addEventListener('hashchange', handleRouteChange);

    // Handle initial route
    handleRouteChange();
}

/**
 * Handle route changes
 */
async function handleRouteChange() {
    const hash = window.location.hash.slice(1) || DEFAULT_ROUTE;
    const route = routes[hash];

    if (!route) {
        // Route not found, redirect to default
        navigateTo(DEFAULT_ROUTE);
        return;
    }

    // Update active nav item
    updateActiveNavItem(hash);

    // Update breadcrumb
    updateBreadcrumb(route.breadcrumb);

    // Update page title
    document.title = `${route.title} - API Security Gateway`;

    // Load and render the page
    await loadPage(route, hash);
}

/**
 * Load a page partial
 */
async function loadPage(route, routeName) {
    // Show loading state
    pageContainer.innerHTML = `
        <div class="page-loading">
            <div class="loading-spinner"></div>
            <p>Loading...</p>
        </div>
    `;

    try {
        let html;
        
        // Check cache first
        if (pageCache[routeName]) {
            html = pageCache[routeName];
        } else {
            // Fetch the page
            const response = await fetch(route.file);
            
            if (!response.ok) {
                throw new Error(`Failed to load page: ${response.status}`);
            }
            
            html = await response.text();
            
            // Cache the page
            pageCache[routeName] = html;
        }

        // Inject the HTML
        pageContainer.innerHTML = html;

        // Initialize page-specific scripts
        initPageScripts(routeName);

    } catch (error) {
        console.error('Error loading page:', error);
        pageContainer.innerHTML = `
            <div class="page-error">
                <div class="error-icon">⚠️</div>
                <h2>Page Not Found</h2>
                <p>The requested page could not be loaded.</p>
                <button class="btn btn-primary" onclick="navigateTo('dashboard')">
                    Go to Dashboard
                </button>
            </div>
        `;
    }
}

/**
 * Update the active navigation item
 */
function updateActiveNavItem(routeName) {
    // Remove active from all nav items
    document.querySelectorAll('.nav-item').forEach(item => {
        item.classList.remove('active');
    });

    // Add active to current nav item
    const activeItem = document.querySelector(`.nav-item[data-route="${routeName}"]`);
    if (activeItem) {
        activeItem.classList.add('active');
    }
}

/**
 * Update the breadcrumb
 */
function updateBreadcrumb(pageName) {
    const breadcrumbCurrent = document.querySelector('.breadcrumb-current');
    if (breadcrumbCurrent) {
        breadcrumbCurrent.textContent = pageName;
    }
}

/**
 * Navigate to a route
 */
function navigateTo(routeName) {
    window.location.hash = routeName;
}

/**
 * Initialize page-specific scripts after load
 */
function initPageScripts(routeName) {
    // Call page-specific init function if it exists
    const initFn = window[`init${capitalizeFirst(routeName.replace('-', ''))}Page`];
    if (typeof initFn === 'function') {
        initFn();
    }

    // Generic page initialization (e.g., tooltips, dropdowns)
    initPageComponents();
}

/**
 * Initialize common page components
 */
function initPageComponents() {
    // Initialize any charts, tables, or interactive components
    // This is called after every page load
}

/**
 * Capitalize first letter
 */
function capitalizeFirst(str) {
    return str.charAt(0).toUpperCase() + str.slice(1);
}

/**
 * Clear page cache (useful for refreshing data)
 */
function clearPageCache(routeName = null) {
    if (routeName) {
        delete pageCache[routeName];
    } else {
        Object.keys(pageCache).forEach(key => delete pageCache[key]);
    }
}

/**
 * Reload current page
 */
function reloadCurrentPage() {
    const hash = window.location.hash.slice(1) || DEFAULT_ROUTE;
    clearPageCache(hash);
    handleRouteChange();
}

// Export for use in other modules
window.initRouter = initRouter;
window.navigateTo = navigateTo;
window.clearPageCache = clearPageCache;
window.reloadCurrentPage = reloadCurrentPage;
