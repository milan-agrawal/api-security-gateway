/* ============================================================
   API SECURITY GATEWAY - ADMIN PANEL ROUTER
   Route configuration + page partial loading
   ============================================================ */

// Admin route configuration
const adminRoutes = {
    'dashboard': {
        title: 'Security Dashboard',
        subtitle: 'Real-time monitoring and threat detection',
        file: 'pages/dashboard.html'
    },
    'traffic-inspector': {
        title: 'Traffic Inspector',
        subtitle: 'Real-time request monitoring and analysis',
        file: 'pages/traffic-inspector.html'
    },
    'ip-geolocation': {
        title: 'IP Geolocation',
        subtitle: 'Geographic traffic analysis and mapping',
        file: 'pages/ip-geolocation.html'
    },
    'firewall-rules': {
        title: 'Firewall Rules',
        subtitle: 'Manage firewall policies and IP blocking',
        file: 'pages/firewall-rules.html'
    },
    'rate-limiting': {
        title: 'Rate Limiting',
        subtitle: 'Configure rate limit policies and thresholds',
        file: 'pages/rate-limiting.html'
    },
    'behavior-engine': {
        title: 'Behavior Engine',
        subtitle: 'Behavioral analysis and pattern detection',
        file: 'pages/behavior-engine.html'
    },
    'anomaly-detection': {
        title: 'Anomaly Detection',
        subtitle: 'ML-powered anomaly detection settings',
        file: 'pages/anomaly-detection.html'
    },
    'bot-mitigation': {
        title: 'Bot Mitigation',
        subtitle: 'Bot detection, CAPTCHA and blocking rules',
        file: 'pages/bot-mitigation.html'
    },
    'api-key-audit': {
        title: 'API Key Audit',
        subtitle: 'Monitor and audit API key usage',
        file: 'pages/api-key-audit.html'
    },
    'support-desk': {
        title: 'Support Desk',
        subtitle: 'Manage user support tickets and response workflow',
        file: 'pages/support-desk.html',
        onLoad: function() {
            if (typeof initSupportDesk === 'function') initSupportDesk();
        }
    },
    'role-management': {
        title: 'Role Management',
        subtitle: 'Admin roles and permission policies',
        file: 'pages/role-management.html'
    },
    'incident-logs': {
        title: 'Security Incidents',
        subtitle: 'Incident tracking and response logs',
        file: 'pages/incident-logs.html'
    },
    'ml-training': {
        title: 'ML Model Training',
        subtitle: 'Train and manage ML detection models',
        file: 'pages/ml-training.html'
    },
    'backend-health': {
        title: 'Backend Health',
        subtitle: 'System health and uptime monitoring',
        file: 'pages/backend-health.html'
    },
    'audit-logs': {
        title: 'System Audit Logs',
        subtitle: 'Comprehensive admin audit trail',
        file: 'pages/audit-logs.html'
    },
    'alerts': {
        title: 'Alerts & Notifications',
        subtitle: 'Manage alert rules and notifications',
        file: 'pages/alerts.html'
    },
    'admin-settings': {
        title: 'Account & MFA',
        subtitle: 'Admin account and security settings',
        file: 'pages/admin-settings.html',
        onLoad: function() {
            if (typeof initAdminSettings === 'function') initAdminSettings();
        }
    },
    'system-config': {
        title: 'System Config',
        subtitle: 'Gateway configuration and tuning',
        file: 'pages/system-config.html'
    },
    'security-reports': {
        title: 'Security Reports',
        subtitle: 'Generate and view security reports',
        file: 'pages/security-reports.html'
    },
    'threat-feeds': {
        title: 'Threat Feeds',
        subtitle: 'External threat intelligence feeds',
        file: 'pages/threat-feeds.html'
    },
    'data-policy': {
        title: 'Data & Privacy Policy',
        subtitle: 'Data governance and compliance settings',
        file: 'pages/data-policy.html'
    },
    'users': {
        title: 'User Management',
        subtitle: 'Manage users and administrators',
        file: 'pages/user-management.html',
        onLoad: function() {
            if (typeof loadUsers === 'function') loadUsers();
            if (typeof loadAdmins === 'function') loadAdmins();
        }
    }
};

// Page cache for performance
const pageCache = {};

/**
 * Load a page partial from the pages/ folder
 * Called from index.js loadRoute() for non-special routes
 */
async function loadPagePartial(route, contentArea) {
    const routeConfig = adminRoutes[route];

    if (!routeConfig) {
        contentArea.innerHTML = `
            <div class="content-loading" style="flex-direction: column; gap: 16px;">
                <span style="color: var(--error);">Page not found</span>
                <button class="btn btn-primary" onclick="navigateTo('dashboard')">Go to Dashboard</button>
            </div>
        `;
        return;
    }

    // Update header
    if (typeof updatePageHeader === 'function') {
        updatePageHeader(routeConfig.title, routeConfig.subtitle);
    }

    // Show loading state
    contentArea.innerHTML = '<div class="content-loading">Loading ' + routeConfig.title + '</div>';

    try {
        let html;

        // Check cache first
        if (pageCache[route]) {
            html = pageCache[route];
        } else {
            const response = await fetch(routeConfig.file + '?v=' + Date.now());
            if (!response.ok) throw new Error('Failed to load page');
            html = await response.text();
            pageCache[route] = html;
        }

        contentArea.innerHTML = html;

        // Run post-load callback if defined
        if (routeConfig.onLoad && typeof routeConfig.onLoad === 'function') {
            routeConfig.onLoad();
        }

    } catch (error) {
        console.error('Error loading page:', error);
        contentArea.innerHTML = `
            <div class="content-loading" style="flex-direction: column; gap: 16px;">
                <span style="color: var(--error);">Failed to load ${routeConfig.title}</span>
                <button class="btn btn-primary" onclick="loadRoute('${route}')">Retry</button>
            </div>
        `;
    }
}

/**
 * Clear page cache
 */
function clearAdminPageCache(route = null) {
    if (route) {
        delete pageCache[route];
    } else {
        Object.keys(pageCache).forEach(key => delete pageCache[key]);
    }
}

/**
 * Check if a route exists in adminRoutes
 */
function isValidAdminRoute(route) {
    return route in adminRoutes;
}
