// API URL - use existing if already defined (SPA mode)
if (typeof API_URL === 'undefined') {
    var API_URL = 'http://localhost:8001';
}

// Close modals on ESC key or clicking outside
document.addEventListener('keydown', function(e) {
    if (e.key === 'Escape') {
        closeEditModal();
        closeConfirmModal();
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

        if (response.ok && data.users.length > 0) {
            document.getElementById('userCount').textContent = `${data.total} User${data.total !== 1 ? 's' : ''}`;
            tbody.innerHTML = data.users.map(user => `
                <tr>
                    <td>${user.id}</td>
                    <td>${escapeHtml(user.email)}</td>
                    <td>${escapeHtml(user.full_name)}</td>
                    <td>
                        <span class="status-badge ${user.is_active ? 'active' : 'inactive'}">
                            ${user.is_active ? 'Active' : 'Inactive'}
                        </span>
                    </td>
                    <td>${new Date(user.created_at).toLocaleString()}</td>
                    <td>
                        <div class="action-buttons">
                            <button class="btn-action btn-edit" onclick="openEditModal(${user.id}, '${escapeHtml(user.email)}', '${escapeHtml(user.full_name)}')" title="Edit User">
                                <svg width="14" height="14" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M11 5H6a2 2 0 00-2 2v11a2 2 0 002 2h11a2 2 0 002-2v-5m-1.414-9.414a2 2 0 112.828 2.828L11.828 15H9v-2.828l8.586-8.586z"/></svg>
                                <span>Edit</span>
                            </button>
                            <button class="btn-action btn-reset" onclick="resetPassword(${user.id}, '${escapeHtml(user.email)}')" title="Reset Password">
                                <svg width="14" height="14" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M15 7a2 2 0 012 2m4 0a6 6 0 01-7.743 5.743L11 17H9v2H7v2H4a1 1 0 01-1-1v-2.586a1 1 0 01.293-.707l5.964-5.964A6 6 0 1121 9z"/></svg>
                                <span>Reset</span>
                            </button>
                            <button class="btn-action btn-toggle" onclick="toggleStatus(${user.id}, '${escapeHtml(user.email)}')">
                                ${user.is_active ? 'Deactivate' : 'Activate'}
                            </button>
                            <button class="btn-action btn-delete" onclick="deleteUser(${user.id}, '${escapeHtml(user.email)}')">
                                Delete
                            </button>
                        </div>
                    </td>
                </tr>
            `).join('');
        } else {
            document.getElementById('userCount').textContent = '0 Users';
            tbody.innerHTML = '<tr><td colspan="6" class="empty-state"><div class="empty-state-icon">👤</div><div>No users found</div></td></tr>';
        }
    } catch (error) {
        console.error('Error loading users:', error);
        tbody.innerHTML = `<tr><td colspan="6" class="empty-state" style="color: #FCA5A5;">Error loading users: ${error.message}</td></tr>`;
    }
}

// Load Admins
async function loadAdmins() {
    const tbody = document.getElementById('adminsTableBody');
    tbody.innerHTML = '<tr><td colspan="6" class="loading">Loading admins</td></tr>';

    try {
        // removed debug log
        const response = await fetch(`${API_URL}/admin/users/list?role=admin`, {
            headers: getAuthHeaders()
        });

        const data = await response.json();
        // removed debug logs

        if (response.ok && data.users.length > 0) {
            document.getElementById('adminCount').textContent = `${data.total} Admin${data.total !== 1 ? 's' : ''}`;
            tbody.innerHTML = data.users.map(user => `
                <tr>
                    <td>${user.id}</td>
                    <td>${escapeHtml(user.email)}</td>
                    <td>${escapeHtml(user.full_name)}</td>
                    <td>
                        <span class="status-badge ${user.is_active ? 'active' : 'inactive'}">
                            ${user.is_active ? 'Active' : 'Inactive'}
                        </span>
                    </td>
                    <td>${new Date(user.created_at).toLocaleString()}</td>
                    <td>
                        <div class="action-buttons">
                            <button class="btn-action btn-edit" onclick="openEditModal(${user.id}, '${escapeHtml(user.email)}', '${escapeHtml(user.full_name)}')" title="Edit Admin">
                                <svg width="14" height="14" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M11 5H6a2 2 0 00-2 2v11a2 2 0 002 2h11a2 2 0 002-2v-5m-1.414-9.414a2 2 0 112.828 2.828L11.828 15H9v-2.828l8.586-8.586z"/></svg>
                                <span>Edit</span>
                            </button>
                            <button class="btn-action btn-reset" onclick="resetPassword(${user.id}, '${escapeHtml(user.email)}')" title="Reset Password">
                                <svg width="14" height="14" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M15 7a2 2 0 012 2m4 0a6 6 0 01-7.743 5.743L11 17H9v2H7v2H4a1 1 0 01-1-1v-2.586a1 1 0 01.293-.707l5.964-5.964A6 6 0 1121 9z"/></svg>
                                <span>Reset</span>
                            </button>
                            <button class="btn-action btn-toggle" onclick="toggleStatus(${user.id}, '${escapeHtml(user.email)}')">
                                ${user.is_active ? 'Deactivate' : 'Activate'}
                            </button>
                            <button class="btn-action btn-delete" onclick="deleteUser(${user.id}, '${escapeHtml(user.email)}')">
                                Delete
                            </button>
                        </div>
                    </td>
                </tr>
            `).join('');
        } else {
            document.getElementById('adminCount').textContent = '0 Admins';
            tbody.innerHTML = '<tr><td colspan="6" class="empty-state"><div class="empty-state-icon">👑</div><div>No admins found</div></td></tr>';
        }
    } catch (error) {
        console.error('Error loading admins:', error);
        tbody.innerHTML = `<tr><td colspan="6" class="empty-state" style="color: #FCA5A5;">Error loading admins: ${error.message}</td></tr>`;
    }
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
