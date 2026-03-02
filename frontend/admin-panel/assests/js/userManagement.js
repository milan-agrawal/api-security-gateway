const API_URL = 'http://localhost:8001';

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
        window.history.replaceState({}, document.title, '/index.html');
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

// Prevent browser back button after logout
window.history.pushState(null, null, window.location.href);
window.addEventListener('popstate', function() {
    window.history.pushState(null, null, window.location.href);
});

// Set admin email on load
window.addEventListener('DOMContentLoaded', function() {
    const userEmail = localStorage.getItem('userEmail');
    if (userEmail) {
        document.getElementById('loggedInAdminEmail').textContent = userEmail;
    }
    // Load data
    loadUsers();
    loadAdmins();
});

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
    const submitBtn = event.target.querySelector('.btn-submit');

    submitBtn.disabled = true;
    submitBtn.textContent = 'Creating...';

    try {
        const requestBody = {
            email: email,
            full_name: fullName,
            role: 'user'
        };
        console.log('Create User Request:', requestBody);
        console.log('Request Headers:', getAuthHeaders());

        const response = await fetch(`${API_URL}/admin/users/create`, {
            method: 'POST',
            headers: getAuthHeaders(),
            body: JSON.stringify(requestBody)
        });

        const data = await response.json();
        console.log('Create User Response:', { status: response.status, ok: response.ok, data });

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
        console.log('Create Admin Request:', requestBody);
        console.log('Request Headers:', getAuthHeaders());

        const response = await fetch(`${API_URL}/admin/users/create`, {
            method: 'POST',
            headers: getAuthHeaders(),
            body: JSON.stringify(requestBody)
        });

        const data = await response.json();
        console.log('Create Admin Response:', { status: response.status, ok: response.ok, data });

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
    tbody.innerHTML = '<tr><td colspan="6" class="loading">Loading users</td></tr>';

    try {
        console.log('Loading users from:', `${API_URL}/admin/users/list?role=user`);
        const response = await fetch(`${API_URL}/admin/users/list?role=user`, {
            headers: getAuthHeaders()
        });

        console.log('Users response status:', response.status);
        const data = await response.json();
        console.log('Users data:', data);

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
        console.log('Loading admins from:', `${API_URL}/admin/users/list?role=admin`);
        const response = await fetch(`${API_URL}/admin/users/list?role=admin`, {
            headers: getAuthHeaders()
        });

        console.log('Admins response status:', response.status);
        const data = await response.json();
        console.log('Admins data:', data);

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

// Toggle User Status
async function toggleStatus(userId, email) {
    if (!confirm(`Are you sure you want to toggle status for ${email}?`)) {
        return;
    }

    try {
        const response = await fetch(`${API_URL}/admin/users/${userId}/toggle-status`, {
            method: 'PATCH',
            headers: getAuthHeaders()
        });

        const data = await response.json();

        if (response.ok) {
            alert(data.message);
            refreshData();
        } else {
            alert(data.detail || 'Error toggling status');
        }
    } catch (error) {
        alert('Network error: ' + error.message);
    }
}

// Delete User
async function deleteUser(userId, email) {
    if (!confirm(`Are you sure you want to DELETE ${email}? This action cannot be undone!`)) {
        return;
    }

    try {
        const response = await fetch(`${API_URL}/admin/users/${userId}`, {
            method: 'DELETE',
            headers: getAuthHeaders()
        });

        const data = await response.json();

        if (response.ok) {
            alert(data.message);
            refreshData();
        } else {
            alert(data.detail || 'Error deleting user');
        }
    } catch (error) {
        alert('Network error: ' + error.message);
    }
}
