// API URL - use existing if already defined (SPA mode)
if (typeof API_URL === 'undefined') {
    var API_URL = 'http://localhost:8001';
}

// Close modals on ESC key or clicking outside
document.addEventListener('keydown', function(e) {
    if (e.key === 'Escape') {
        closeEditModal();
        closeConfirmModal();
        closeUserDetail();
    }
});
document.addEventListener('click', function(e) {
    if (e.target.classList.contains('modal-overlay') && e.target.classList.contains('active')) {
        e.target.classList.remove('active');
    }
});

// Check if loaded via SPA (index.js sets window.isSPAMode = true)
var isSPAMode = window.isSPAMode === true;

// Skip auth checks and auto-init in SPA mode (handled by index.js)
if (!isSPAMode) {
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

        if (urlToken && urlEmail && urlRole) {
            localStorage.setItem('token', urlToken);
            localStorage.setItem('userEmail', urlEmail);
            localStorage.setItem('userRole', urlRole);
            localStorage.setItem('fullName', urlFullName || '');
            sessionStorage.removeItem('loggedOut');
            window.history.replaceState({}, document.title, '/userManagement.html');
        }

        const token = localStorage.getItem('token');
        const userRole = localStorage.getItem('userRole');
        const loggedOut = sessionStorage.getItem('loggedOut');
        
        if (loggedOut === 'true') {
            window.location.replace('http://localhost:3000/login.html');
            return;
        }
        
        if (!token) {
            window.location.replace('http://localhost:3000/login.html');
            return;
        }

        if (userRole !== 'admin') {
            alert('Access denied. This panel is for administrators only.');
            window.location.replace('http://localhost:3000/login.html');
            return;
        }
    })();

    // Set admin email on load (standalone mode)
    window.addEventListener('DOMContentLoaded', function() {
        const userEmail = localStorage.getItem('userEmail');
        if (userEmail) {
            const emailEl = document.getElementById('loggedInAdminEmail');
            if (emailEl) emailEl.textContent = userEmail;
        }
        // Load data
        loadUsers();
        loadAdmins();
    });
}

function logout() {
    sessionStorage.setItem('loggedOut', 'true');
    localStorage.clear();
    window.location.replace('http://localhost:3000/login.html?logout=true');
}

function refreshData() {
    loadUsers();
    loadAdmins();
}

// HTML escaping to prevent XSS attacks
function escapeHtml(unsafe) {
    if (typeof unsafe !== 'string') return unsafe;
    return unsafe
        .replace(/&/g, "&amp;")
        .replace(/</g, "&lt;")
        .replace(/>/g, "&gt;")
        .replace(/\"/g, "&quot;")
        .replace(/'/g, "&#039;");
}

// Get auth headers
function getAuthHeaders() {
    const token = localStorage.getItem('token');
    return {
        'Content-Type': 'application/json',
        'Authorization': `Bearer ${token}`
    };
}

// Show message
function showMessage(elementId, message, type) {
    const el = document.getElementById(elementId);
    el.textContent = message;
    el.className = `message ${type}`;
    el.style.display = 'block';
    setTimeout(() => {
        el.style.display = 'none';
    }, 5000);
}

// Create User
async function createUser(event) {
    event.preventDefault();
    const email = document.getElementById('userEmail').value;
    const fullName = document.getElementById('userFullName').value;
    const enable2FA = document.getElementById('userEnable2FA')?.checked || false;
    const submitBtn = event.target.querySelector('.btn-submit');

    submitBtn.disabled = true;
    submitBtn.textContent = 'Creating...';

    try {
        const requestBody = {
            email: email,
            full_name: fullName,
            role: 'user',
            enable_2fa: enable2FA
        };
        // debug logs removed for security

        const response = await fetch(`${API_URL}/admin/users/create`, {
            method: 'POST',
            headers: getAuthHeaders(),
            body: JSON.stringify(requestBody)
        });

        const data = await response.json();
        // response logging removed to avoid leaking sensitive info

        if (response.ok) {
            showMessage('userMessage', data.message, 'success');
            document.getElementById('addUserForm').reset();
            setTimeout(() => loadUsers(), 1000);
        } else {
            // Handle different error formats
            console.error('Create User Error:', data);
            let errorMsg = 'Error creating user';
            if (typeof data.detail === 'string') {
                errorMsg = data.detail;
            } else if (Array.isArray(data.detail)) {
                // Handle FastAPI validation errors
                errorMsg = data.detail.map(err => `${err.loc.join('.')}: ${err.msg}`).join('; ');
            } else if (typeof data.detail === 'object') {
                errorMsg = JSON.stringify(data.detail);
            }
            showMessage('userMessage', errorMsg, 'error');
        }
    } catch (error) {
        showMessage('userMessage', 'Network error: ' + error.message, 'error');
    } finally {
        submitBtn.disabled = false;
        submitBtn.textContent = 'Create User Account';
    }
}

// Create Admin
async function createAdmin(event) {
    event.preventDefault();
    const email = document.getElementById('adminEmail').value;
    const fullName = document.getElementById('adminFullName').value;
    const submitBtn = event.target.querySelector('.btn-submit');

    submitBtn.disabled = true;
    submitBtn.textContent = 'Creating...';

    try {
        const requestBody = {
            email: email,
            full_name: fullName,
            role: 'admin'
        };
        // debug logs removed for security

        const response = await fetch(`${API_URL}/admin/users/create`, {
            method: 'POST',
            headers: getAuthHeaders(),
            body: JSON.stringify(requestBody)
        });

        const data = await response.json();
        // response logging removed to avoid leaking sensitive info

        if (response.ok) {
            showMessage('adminMessage', data.message, 'success');
            document.getElementById('addAdminForm').reset();
            setTimeout(() => loadAdmins(), 1000);
        } else {
            // Handle different error formats
            console.error('Create Admin Error:', data);
            let errorMsg = 'Error creating admin';
            if (typeof data.detail === 'string') {
                errorMsg = data.detail;
            } else if (Array.isArray(data.detail)) {
                // Handle FastAPI validation errors
                errorMsg = data.detail.map(err => `${err.loc.join('.')}: ${err.msg}`).join('; ');
            } else if (typeof data.detail === 'object') {
                errorMsg = JSON.stringify(data.detail);
            }
            showMessage('adminMessage', errorMsg, 'error');
        }
    } catch (error) {
        showMessage('adminMessage', 'Network error: ' + error.message, 'error');
    } finally {
        submitBtn.disabled = false;
        submitBtn.textContent = 'Create Admin Account';
    }
}

// ==========================================
//  DATA STORES & PAGINATION STATE
// ==========================================
var allUsers = [];
var allAdmins = [];
var userPage = 1;
var adminPage = 1;
var PAGE_SIZE = 10;

// Load Users
async function loadUsers() {
    const tbody = document.getElementById('usersTableBody');
    if (!tbody) return;
    tbody.innerHTML = '<tr><td colspan="6" class="loading">Loading users...</td></tr>';

    try {
        const response = await fetch(`${API_URL}/admin/users/list?role=user`, {
            headers: getAuthHeaders()
        });

        const data = await response.json();

        if (response.ok) {
            allUsers = data.users || [];
            document.getElementById('userCount').textContent = `${data.total} User${data.total !== 1 ? 's' : ''}`;
            userPage = 1;
            filterUsers();
        } else {
            document.getElementById('userCount').textContent = '0 Users';
            allUsers = [];
            tbody.innerHTML = '<tr><td colspan="6" class="empty-state"><div class="empty-state-icon">👤</div><div>No users found</div></td></tr>';
        }
    } catch (error) {
        console.error('Error loading users:', error);
        allUsers = [];
        tbody.innerHTML = `<tr><td colspan="6" class="empty-state" style="color: #FCA5A5;">Error loading users: ${error.message}</td></tr>`;
    }
}

// Load Admins
async function loadAdmins() {
    const tbody = document.getElementById('adminsTableBody');
    tbody.innerHTML = '<tr><td colspan="6" class="loading">Loading admins</td></tr>';

    try {
        const response = await fetch(`${API_URL}/admin/users/list?role=admin`, {
            headers: getAuthHeaders()
        });

        const data = await response.json();

        if (response.ok) {
            allAdmins = data.users || [];
            document.getElementById('adminCount').textContent = `${data.total} Admin${data.total !== 1 ? 's' : ''}`;
            adminPage = 1;
            filterAdmins();
        } else {
            document.getElementById('adminCount').textContent = '0 Admins';
            allAdmins = [];
            tbody.innerHTML = '<tr><td colspan="6" class="empty-state"><div class="empty-state-icon">👑</div><div>No admins found</div></td></tr>';
        }
    } catch (error) {
        console.error('Error loading admins:', error);
        allAdmins = [];
        tbody.innerHTML = `<tr><td colspan="6" class="empty-state" style="color: #FCA5A5;">Error loading admins: ${error.message}</td></tr>`;
    }
}

// ==========================================
//  CLIENT-SIDE FILTER, SORT & PAGINATION
// ==========================================

function applyFilters(items, searchId, statusId, sortId) {
    const search = (document.getElementById(searchId)?.value || '').toLowerCase().trim();
    const statusVal = document.getElementById(statusId)?.value || 'all';
    const sortVal = document.getElementById(sortId)?.value || 'newest';

    let filtered = items.slice();

    // Search by name or email
    if (search) {
        filtered = filtered.filter(u =>
            u.email.toLowerCase().includes(search) ||
            u.full_name.toLowerCase().includes(search)
        );
    }

    // Status filter
    if (statusVal === 'active') {
        filtered = filtered.filter(u => u.is_active);
    } else if (statusVal === 'inactive') {
        filtered = filtered.filter(u => !u.is_active);
    }

    // Sort
    switch (sortVal) {
        case 'oldest':
            filtered.sort((a, b) => new Date(a.created_at) - new Date(b.created_at));
            break;
        case 'newest':
            filtered.sort((a, b) => new Date(b.created_at) - new Date(a.created_at));
            break;
        case 'name-asc':
            filtered.sort((a, b) => a.full_name.localeCompare(b.full_name));
            break;
        case 'name-desc':
            filtered.sort((a, b) => b.full_name.localeCompare(a.full_name));
            break;
    }

    return filtered;
}

function renderTableRows(filtered, page, tbodyId, pageInfoId, prevBtnId, nextBtnId, emptyIcon) {
    const tbody = document.getElementById(tbodyId);
    if (!tbody) return;

    const totalPages = Math.max(1, Math.ceil(filtered.length / PAGE_SIZE));
    if (page > totalPages) page = totalPages;
    const start = (page - 1) * PAGE_SIZE;
    const pageItems = filtered.slice(start, start + PAGE_SIZE);

    if (filtered.length === 0) {
        tbody.innerHTML = `<tr><td colspan="7" class="empty-state"><div class="empty-state-icon">${emptyIcon}</div><div>No results found</div></td></tr>`;
    } else {
        tbody.innerHTML = pageItems.map(user => {
            let mfaBadge;
            if (user.mfa_enabled && user.mfa_setup_complete) {
                mfaBadge = '<span class="mfa-badge mfa-active">🔒 Active</span>';
            } else if (user.mfa_enabled && !user.mfa_setup_complete) {
                mfaBadge = '<span class="mfa-badge mfa-pending">⏳ Pending</span>';
            } else {
                mfaBadge = '<span class="mfa-badge mfa-disabled">🔓 Off</span>';
            }
            return `
            <tr>
                <td>${user.id}</td>
                <td>${escapeHtml(user.email)}</td>
                <td>${escapeHtml(user.full_name)}</td>
                <td>
                    <span class="status-badge ${user.is_active ? 'active' : 'inactive'}">
                        ${user.is_active ? 'Active' : 'Inactive'}
                    </span>
                </td>
                <td>${mfaBadge}</td>
                <td>${new Date(user.created_at).toLocaleString()}</td>
                <td>
                    <div class="action-buttons">
                        <button class="btn-action btn-view" onclick="openUserDetail(${user.id})" title="View Details">
                            <svg width="14" height="14" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M15 12a3 3 0 11-6 0 3 3 0 016 0z"/><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M2.458 12C3.732 7.943 7.523 5 12 5c4.478 0 8.268 2.943 9.542 7-1.274 4.057-5.064 7-9.542 7-4.477 0-8.268-2.943-9.542-7z"/></svg>
                            <span>View</span>
                        </button>
                        <button class="btn-action btn-edit" onclick="openEditModal(${user.id}, '${escapeHtml(user.email)}', '${escapeHtml(user.full_name)}')" title="Edit User">
                            <svg width="14" height="14" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M11 5H6a2 2 0 00-2 2v11a2 2 0 002 2h11a2 2 0 002-2v-5m-1.414-9.414a2 2 0 112.828 2.828L11.828 15H9v-2.828l8.586-8.586z"/></svg>
                            <span>Edit</span>
                        </button>
                        <button class="btn-action btn-toggle" onclick="toggleStatus(${user.id}, '${escapeHtml(user.email)}')">
                            ${user.is_active ? 'Deactivate' : 'Activate'}
                        </button>
                    </div>
                </td>
            </tr>
        `;
        }).join('');
    }

    // Update pagination
    const pageInfoEl = document.getElementById(pageInfoId);
    const prevBtn = document.getElementById(prevBtnId);
    const nextBtn = document.getElementById(nextBtnId);
    if (pageInfoEl) pageInfoEl.textContent = `Page ${page} of ${totalPages}` + (filtered.length > 0 ? ` (${filtered.length} results)` : '');
    if (prevBtn) prevBtn.disabled = page <= 1;
    if (nextBtn) nextBtn.disabled = page >= totalPages;
}

function filterUsers() {
    const filtered = applyFilters(allUsers, 'userSearchInput', 'userStatusFilter', 'userSortFilter');
    userPage = 1;
    renderTableRows(filtered, userPage, 'usersTableBody', 'userPageInfo', 'userPrevBtn', 'userNextBtn', '👤');
}

function filterAdmins() {
    const filtered = applyFilters(allAdmins, 'adminSearchInput', 'adminStatusFilter', 'adminSortFilter');
    adminPage = 1;
    renderTableRows(filtered, adminPage, 'adminsTableBody', 'adminPageInfo', 'adminPrevBtn', 'adminNextBtn', '👑');
}

function changeUserPage(delta) {
    const filtered = applyFilters(allUsers, 'userSearchInput', 'userStatusFilter', 'userSortFilter');
    const totalPages = Math.max(1, Math.ceil(filtered.length / PAGE_SIZE));
    userPage = Math.max(1, Math.min(totalPages, userPage + delta));
    renderTableRows(filtered, userPage, 'usersTableBody', 'userPageInfo', 'userPrevBtn', 'userNextBtn', '👤');
}

function changeAdminPage(delta) {
    const filtered = applyFilters(allAdmins, 'adminSearchInput', 'adminStatusFilter', 'adminSortFilter');
    const totalPages = Math.max(1, Math.ceil(filtered.length / PAGE_SIZE));
    adminPage = Math.max(1, Math.min(totalPages, adminPage + delta));
    renderTableRows(filtered, adminPage, 'adminsTableBody', 'adminPageInfo', 'adminPrevBtn', 'adminNextBtn', '👑');
}

// ==========================================
//  USER DETAILS SLIDE PANEL
// ==========================================

function openUserDetail(userId) {
    const overlay = document.getElementById('userDetailOverlay');
    const panel = document.getElementById('userDetailPanel');
    const body = document.getElementById('userDetailBody');
    if (!panel || !body) return;

    body.innerHTML = '<div class="detail-loading">Loading user details...</div>';
    overlay.classList.add('active');
    panel.classList.add('active');

    // Fetch full user details from backend
    fetch(`${API_URL}/admin/users/${userId}`, {
        headers: getAuthHeaders()
    })
    .then(res => res.json())
    .then(data => {
        if (data.id) {
            const createdDate = data.created_at ? new Date(data.created_at) : null;
            const updatedDate = data.updated_at ? new Date(data.updated_at) : null;
            const lastLogin = data.last_login_at ? new Date(data.last_login_at) : null;
            const accountAge = createdDate ? getAccountAge(createdDate) : 'Unknown';

            body.innerHTML = `
                <div class="detail-profile">
                    <div class="detail-avatar">${escapeHtml(data.full_name.charAt(0).toUpperCase())}</div>
                    <div class="detail-name">${escapeHtml(data.full_name)}</div>
                    <div class="detail-email">${escapeHtml(data.email)}</div>
                    <div class="detail-badges">
                        <span class="detail-role-badge role-${data.role}">${data.role === 'admin' ? '👑 Admin' : '👤 User'}</span>
                        <span class="status-badge ${data.is_active ? 'active' : 'inactive'}">${data.is_active ? 'Active' : 'Inactive'}</span>
                    </div>
                </div>

                <div class="detail-section">
                    <h4 class="detail-section-title">Account Info</h4>
                    <div class="detail-grid">
                        <div class="detail-item">
                            <span class="detail-label">User ID</span>
                            <span class="detail-value">#${data.id}</span>
                        </div>
                        <div class="detail-item">
                            <span class="detail-label">Account Age</span>
                            <span class="detail-value">${accountAge}</span>
                        </div>
                        <div class="detail-item">
                            <span class="detail-label">Created</span>
                            <span class="detail-value">${createdDate ? createdDate.toLocaleDateString('en-US', { year: 'numeric', month: 'short', day: 'numeric' }) : 'N/A'}</span>
                        </div>
                        <div class="detail-item">
                            <span class="detail-label">Last Updated</span>
                            <span class="detail-value">${updatedDate ? updatedDate.toLocaleDateString('en-US', { year: 'numeric', month: 'short', day: 'numeric' }) : 'N/A'}</span>
                        </div>
                    </div>
                </div>

                <div class="detail-section">
                    <h4 class="detail-section-title">Security</h4>
                    <div class="detail-grid">
                        <div class="detail-item">
                            <span class="detail-label">MFA Enabled</span>
                            <span class="detail-value detail-mfa ${data.mfa_enabled ? 'mfa-on' : 'mfa-off'}">
                                ${data.mfa_enabled ? '🔒 Enabled' : '🔓 Disabled'}
                            </span>
                        </div>
                        <div class="detail-item">
                            <span class="detail-label">MFA Setup</span>
                            <span class="detail-value">${data.mfa_setup_complete ? '✅ Complete' : '⏳ Pending'}</span>
                        </div>
                        <div class="detail-item">
                            <span class="detail-label">Last Login</span>
                            <span class="detail-value">${lastLogin ? lastLogin.toLocaleString() : 'Never'}</span>
                        </div>
                    </div>
                </div>

                <div class="detail-section">
                    <h4 class="detail-section-title">API Keys</h4>
                    <div class="detail-grid">
                        <div class="detail-item">
                            <span class="detail-label">Total Keys</span>
                            <span class="detail-value detail-keys">${data.api_keys_count}</span>
                        </div>
                        <div class="detail-item">
                            <span class="detail-label">Active Keys</span>
                            <span class="detail-value detail-keys">${data.active_api_keys}</span>
                        </div>
                    </div>
                </div>

                <div class="detail-danger-zone">
                    <h4 class="detail-section-title danger-title">Danger Zone</h4>
                    <div class="detail-actions-row">
                        <button class="btn-action btn-reset" onclick="closeUserDetail(); resetPassword(${data.id}, '${escapeHtml(data.email)}')">
                            <svg width="14" height="14" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M15 7a2 2 0 012 2m4 0a6 6 0 01-7.743 5.743L11 17H9v2H7v2H4a1 1 0 01-1-1v-2.586a1 1 0 01.293-.707l5.964-5.964A6 6 0 1121 9z"/></svg>
                            <span>Reset Password</span>
                        </button>
                        <button class="btn-action btn-revoke" onclick="closeUserDetail(); revokeSessions(${data.id}, '${escapeHtml(data.email)}')">
                            <svg width="14" height="14" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M17 16l4-4m0 0l-4-4m4 4H7m6 4v1a3 3 0 01-3 3H6a3 3 0 01-3-3V7a3 3 0 013-3h4a3 3 0 013 3v1"/></svg>
                            <span>Revoke Sessions</span>
                        </button>
                    </div>
                    <button class="btn-action btn-delete detail-delete-btn" onclick="closeUserDetail(); deleteUser(${data.id}, '${escapeHtml(data.email)}')">
                        <svg width="14" height="14" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16"/></svg>
                        <span>Delete User Permanently</span>
                    </button>
                </div>
            `;
        } else {
            body.innerHTML = '<div class="detail-loading" style="color: #FCA5A5;">User not found</div>';
        }
    })
    .catch(err => {
        body.innerHTML = `<div class="detail-loading" style="color: #FCA5A5;">Error: ${err.message}</div>`;
    });
}

function closeUserDetail() {
    const overlay = document.getElementById('userDetailOverlay');
    const panel = document.getElementById('userDetailPanel');
    if (overlay) overlay.classList.remove('active');
    if (panel) panel.classList.remove('active');
}

function getAccountAge(createdDate) {
    const now = new Date();
    const diff = now - createdDate;
    const days = Math.floor(diff / (1000 * 60 * 60 * 24));
    if (days < 1) return 'Today';
    if (days === 1) return '1 day';
    if (days < 30) return `${days} days`;
    const months = Math.floor(days / 30);
    if (months < 12) return `${months} month${months > 1 ? 's' : ''}`;
    const years = Math.floor(months / 12);
    const rem = months % 12;
    return rem > 0 ? `${years}y ${rem}m` : `${years} year${years > 1 ? 's' : ''}`;
}

// ==========================================
//  EDIT USER MODAL
// ==========================================

function openEditModal(userId, email, fullName) {
    document.getElementById('editUserId').value = userId;
    document.getElementById('editEmail').value = email;
    document.getElementById('editFullName').value = fullName;
    document.getElementById('editMessage').style.display = 'none';
    document.getElementById('editSubmitBtn').disabled = false;
    document.getElementById('editSubmitBtn').textContent = 'Save Changes';
    document.getElementById('editUserModal').classList.add('active');
}

function closeEditModal() {
    document.getElementById('editUserModal').classList.remove('active');
}

async function submitEditUser(event) {
    event.preventDefault();
    const userId = document.getElementById('editUserId').value;
    const email = document.getElementById('editEmail').value;
    const fullName = document.getElementById('editFullName').value;
    const submitBtn = document.getElementById('editSubmitBtn');

    submitBtn.disabled = true;
    submitBtn.textContent = 'Saving...';

    try {
        const response = await fetch(`${API_URL}/admin/users/${userId}`, {
            method: 'PATCH',
            headers: getAuthHeaders(),
            body: JSON.stringify({ email, full_name: fullName })
        });

        const data = await response.json();

        if (response.ok) {
            showMessage('editMessage', data.message, 'success');
            setTimeout(() => {
                closeEditModal();
                refreshData();
            }, 1200);
        } else {
            let errorMsg = 'Error updating user';
            if (typeof data.detail === 'string') {
                errorMsg = data.detail;
            } else if (Array.isArray(data.detail)) {
                errorMsg = data.detail.map(err => `${err.loc.join('.')}: ${err.msg}`).join('; ');
            }
            showMessage('editMessage', errorMsg, 'error');
            submitBtn.disabled = false;
            submitBtn.textContent = 'Save Changes';
        }
    } catch (error) {
        showMessage('editMessage', 'Network error: ' + error.message, 'error');
        submitBtn.disabled = false;
        submitBtn.textContent = 'Save Changes';
    }
}

// ==========================================
//  CONFIRM MODAL (replaces alert/confirm)
// ==========================================

let confirmCallback = null;

function showConfirmModal(title, message, extraInfo, btnText, btnClass, callback) {
    document.getElementById('confirmTitle').textContent = title;
    document.getElementById('confirmMessage').textContent = message;
    const extraEl = document.getElementById('confirmExtraInfo');
    extraEl.innerHTML = extraInfo || '';
    extraEl.style.display = extraInfo ? 'block' : 'none';
    const actionBtn = document.getElementById('confirmActionBtn');
    actionBtn.textContent = btnText;
    actionBtn.className = 'btn-submit btn-confirm-action ' + (btnClass || '');
    confirmCallback = callback;
    actionBtn.onclick = async () => {
        actionBtn.disabled = true;
        actionBtn.textContent = 'Processing...';
        await callback();
        actionBtn.disabled = false;
    };
    document.getElementById('confirmModal').classList.add('active');
}

function closeConfirmModal() {
    document.getElementById('confirmModal').classList.remove('active');
    confirmCallback = null;
}

// ==========================================
//  RESET PASSWORD
// ==========================================

function resetPassword(userId, email) {
    showConfirmModal(
        '🔑 Reset Password',
        `Reset password for ${email}?`,
        '<div class="confirm-warning">⚠️ A new password will be generated and emailed. All existing sessions will be invalidated.</div>',
        'Reset Password',
        'btn-reset-confirm',
        async () => {
            try {
                const response = await fetch(`${API_URL}/admin/users/${userId}/reset-password`, {
                    method: 'POST',
                    headers: getAuthHeaders()
                });
                const data = await response.json();
                if (response.ok) {
                    closeConfirmModal();
                    showToast(data.message, 'success');
                } else {
                    closeConfirmModal();
                    showToast(data.detail || 'Error resetting password', 'error');
                }
            } catch (error) {
                closeConfirmModal();
                showToast('Network error: ' + error.message, 'error');
            }
        }
    );
}

// ==========================================
//  TOGGLE STATUS (with confirm modal)
// ==========================================

function toggleStatus(userId, email) {
    showConfirmModal(
        '🔄 Toggle Status',
        `Toggle active status for ${email}?`,
        '',
        'Toggle Status',
        '',
        async () => {
            try {
                const response = await fetch(`${API_URL}/admin/users/${userId}/toggle-status`, {
                    method: 'PATCH',
                    headers: getAuthHeaders()
                });
                const data = await response.json();
                if (response.ok) {
                    closeConfirmModal();
                    showToast(data.message, 'success');
                    refreshData();
                } else {
                    closeConfirmModal();
                    showToast(data.detail || 'Error toggling status', 'error');
                }
            } catch (error) {
                closeConfirmModal();
                showToast('Network error: ' + error.message, 'error');
            }
        }
    );
}

// ==========================================
//  REVOKE SESSIONS / FORCE LOGOUT
// ==========================================

function revokeSessions(userId, email) {
    showConfirmModal(
        '🚪 Force Logout',
        `Revoke all sessions for ${email}?`,
        '<div class="confirm-warning">⚠️ The user will be logged out everywhere immediately and must log in again.</div>',
        'Revoke Sessions',
        'btn-revoke-confirm',
        async () => {
            try {
                const response = await fetch(`${API_URL}/admin/users/${userId}/revoke-sessions`, {
                    method: 'POST',
                    headers: getAuthHeaders()
                });
                const data = await response.json();
                if (response.ok) {
                    closeConfirmModal();
                    showToast(data.message, 'success');
                } else {
                    closeConfirmModal();
                    showToast(data.detail || 'Error revoking sessions', 'error');
                }
            } catch (error) {
                closeConfirmModal();
                showToast('Network error: ' + error.message, 'error');
            }
        }
    );
}

// ==========================================
//  DELETE USER (with confirm modal)
// ==========================================

function deleteUser(userId, email) {
    showConfirmModal(
        '🗑️ Delete User',
        `Permanently delete ${email}?`,
        '<div class="confirm-warning confirm-danger">⚠️ This action cannot be undone. All user data, API keys, and sessions will be destroyed.</div>',
        'Delete User',
        'btn-delete-confirm',
        async () => {
            try {
                const response = await fetch(`${API_URL}/admin/users/${userId}`, {
                    method: 'DELETE',
                    headers: getAuthHeaders()
                });
                const data = await response.json();
                if (response.ok) {
                    closeConfirmModal();
                    showToast(data.message, 'success');
                    refreshData();
                } else {
                    closeConfirmModal();
                    showToast(data.detail || 'Error deleting user', 'error');
                }
            } catch (error) {
                closeConfirmModal();
                showToast('Network error: ' + error.message, 'error');
            }
        }
    );
}

// ==========================================
//  TOAST NOTIFICATION (replaces alert())
// ==========================================

function showToast(message, type = 'info') {
    // Remove existing toast if any
    const existing = document.querySelector('.toast-notification');
    if (existing) existing.remove();

    const toast = document.createElement('div');
    toast.className = `toast-notification toast-${type}`;
    const icon = type === 'success' ? '✅' : type === 'error' ? '❌' : 'ℹ️';
    toast.innerHTML = `<span class="toast-icon">${icon}</span><span class="toast-msg">${escapeHtml(message)}</span>`;
    document.body.appendChild(toast);

    // Trigger animation
    requestAnimationFrame(() => toast.classList.add('show'));

    // Auto remove after 4s
    setTimeout(() => {
        toast.classList.remove('show');
        setTimeout(() => toast.remove(), 300);
    }, 4000);
}
