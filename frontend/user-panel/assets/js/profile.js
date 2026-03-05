/* ============================================================
   PROFILE & MFA PAGE — JavaScript Logic
   ============================================================ */

const PROFILE_API = 'http://localhost:8001';

// Cached profile data
let _profileData = null;
let _backupCodesCache = [];

// ============================================================
// UNSAVED CHANGES TRACKING
// ============================================================
let _profileDirty = false;
let _pendingNavHash = null;
let _skipUnsavedCheck = false;

function markProfileDirty() {
    _profileDirty = true;
}

function markProfileClean() {
    _profileDirty = false;
}

function hasUnsavedChanges() {
    if (_skipUnsavedCheck) return false;
    if (!_profileData) return false;
    const nameInput = document.getElementById('editFullName');
    const emailInput = document.getElementById('editEmail');
    if (nameInput && nameInput.value.trim() !== (_profileData.full_name || '')) return true;
    if (emailInput && emailInput.value.trim() !== (_profileData.email || '')) return true;
    // Check password form — if any field has input
    const cur = document.getElementById('currentPassword');
    const newP = document.getElementById('newPassword');
    const conf = document.getElementById('confirmPassword');
    if (cur && cur.value) return true;
    if (newP && newP.value) return true;
    if (conf && conf.value) return true;
    return false;
}

function showUnsavedModal(targetHash) {
    _pendingNavHash = targetHash;
    const modal = document.getElementById('unsavedChangesModal');
    if (modal) modal.classList.add('active');
}

function dismissUnsavedModal(discard) {
    const modal = document.getElementById('unsavedChangesModal');
    if (modal) modal.classList.remove('active');
    if (discard && _pendingNavHash !== null) {
        _skipUnsavedCheck = true;
        window.location.hash = _pendingNavHash;
        // Reset flag after navigation completes
        setTimeout(() => { _skipUnsavedCheck = false; }, 100);
    }
    _pendingNavHash = null;
}

// Hook into hashchange to intercept navigation when dirty
(function() {
    let _realHashHandler = null;
    
    window.addEventListener('hashchange', function _unsavedGuard(e) {
        // Only guard when on profile page and dirty
        if (!hasUnsavedChanges()) return;
        
        const newHash = window.location.hash.slice(1);
        if (newHash === 'profile') return; // staying on profile

        // Prevent navigation — restore old hash silently
        e.stopImmediatePropagation();
        history.replaceState(null, '', '#profile');
        showUnsavedModal(newHash);
    }, true); // capture phase — runs before router
})();

// Also guard browser close / tab close
window.addEventListener('beforeunload', function(e) {
    if (hasUnsavedChanges()) {
        e.preventDefault();
        e.returnValue = '';
    }
});

/**
 * Helper — get auth header
 */
function profileAuthHeaders() {
    return {
        'Authorization': `Bearer ${localStorage.getItem('token')}`,
        'Content-Type': 'application/json'
    };
}

/**
 * Helper — handle 401 / revoked token
 */
function handleAuthError(res) {
    if (res.status === 401) {
        showToast('Session expired. Please log in again.', 'error');
        setTimeout(() => logout(), 1500);
        return true;
    }
    return false;
}

// ============================================================
// INIT — called by router via initProfilePage()
// ============================================================

async function initProfilePage() {
    await loadProfile();
    await loadMfaStatus();
}

// ============================================================
// PROFILE — fetch & render
// ============================================================

async function loadProfile() {
    try {
        const res = await fetch(`${PROFILE_API}/user/profile`, {
            headers: profileAuthHeaders()
        });
        if (handleAuthError(res)) return;
        if (!res.ok) throw new Error('Failed to load profile');

        const data = await res.json();
        _profileData = data;
        renderProfile(data);
    } catch (err) {
        console.error('loadProfile:', err);
        showToast('Failed to load profile', 'error');
    }
}

function renderProfile(p) {
    // Avatar
    const avatarEl = document.getElementById('profileAvatar');
    if (avatarEl) {
        const initials = getInitials(p.full_name || p.email);
        avatarEl.textContent = initials;
    }

    // Name & email
    const nameEl = document.getElementById('profileName');
    if (nameEl) nameEl.textContent = p.full_name;

    const emailEl = document.getElementById('profileEmail');
    if (emailEl) emailEl.textContent = p.email;

    // Badges
    const badgesEl = document.getElementById('profileBadges');
    if (badgesEl) {
        badgesEl.innerHTML = `
            <span class="profile-badge role">${p.role.toUpperCase()}</span>
            <span class="profile-badge ${p.mfa_enabled ? 'mfa-on' : 'mfa-off'}">
                ${p.mfa_enabled ? '🔒 2FA Enabled' : '🔓 2FA Off'}
            </span>
            <span class="profile-badge keys">${p.active_api_key_count} Active Key${p.active_api_key_count !== 1 ? 's' : ''}</span>
        `;
    }

    // Stats
    const statKeys = document.getElementById('statApiKeys');
    const statActive = document.getElementById('statActiveKeys');
    if (statKeys) statKeys.textContent = p.api_key_count;
    if (statActive) statActive.textContent = p.active_api_key_count;

    // Account Details grid
    setTextById('infoAccountId', `#${p.id}`);
    setTextById('infoRole', p.role.charAt(0).toUpperCase() + p.role.slice(1));
    setTextById('infoCreatedAt', formatDateNice(p.created_at));
    setTextById('infoLastLogin', p.last_login_at ? formatDateNice(p.last_login_at) : 'Never');
    setTextById('infoStatus', p.is_active ? '● Active' : '● Inactive');
    const statusEl = document.getElementById('infoStatus');
    if (statusEl) statusEl.style.color = p.is_active ? 'var(--success)' : 'var(--error)';
    setTextById('infoPasswordChanged', p.password_changed_at ? formatDateNice(p.password_changed_at) : 'Never');
    setTextById('infoUpdatedAt', formatDateNice(p.updated_at));

    // Render Security Score
    renderSecurityScore(p);

    // Pre-fill edit form
    const nameInput = document.getElementById('editFullName');
    const emailInput = document.getElementById('editEmail');
    if (nameInput) nameInput.value = p.full_name;
    if (emailInput) emailInput.value = p.email;
}

function setTextById(id, text) {
    const el = document.getElementById(id);
    if (el) el.textContent = text;
}

function formatDateNice(isoStr) {
    if (!isoStr) return '—';
    const d = new Date(isoStr);
    return d.toLocaleDateString('en-US', {
        year: 'numeric', month: 'short', day: 'numeric',
        hour: '2-digit', minute: '2-digit'
    });
}

// ============================================================
// EDIT PROFILE
// ============================================================

function resetEditForm() {
    if (!_profileData) return;
    document.getElementById('editFullName').value = _profileData.full_name;
    document.getElementById('editEmail').value = _profileData.email;
}

async function handleUpdateProfile(e) {
    e.preventDefault();
    const btn = document.getElementById('btnSaveProfile');
    const fullName = document.getElementById('editFullName').value.trim();
    const email = document.getElementById('editEmail').value.trim();

    // Quick check — anything changed?
    if (_profileData && fullName === _profileData.full_name && email === _profileData.email) {
        showToast('No changes to save', 'info');
        return;
    }

    btn.disabled = true;
    btn.innerHTML = '<span class="loading-spinner" style="width:16px;height:16px"></span> Saving...';

    try {
        const body = {};
        if (!_profileData || fullName !== _profileData.full_name) body.full_name = fullName;
        if (!_profileData || email !== _profileData.email) body.email = email;

        const res = await fetch(`${PROFILE_API}/user/profile`, {
            method: 'PATCH',
            headers: profileAuthHeaders(),
            body: JSON.stringify(body)
        });

        if (handleAuthError(res)) return;

        const result = await res.json();
        if (!res.ok) {
            showToast(result.detail || 'Update failed', 'error');
            return;
        }

        showToast('Profile updated!', 'success');
        showSuccessAnimation('Profile Updated!');
        markProfileClean();

        // Update localStorage so sidebar reflects new info
        if (body.email) localStorage.setItem('userEmail', result.email);
        if (body.full_name) localStorage.setItem('fullName', result.full_name);

        // Refresh sidebar user display
        if (typeof updateUserDisplay === 'function') {
            updateUserDisplay(
                localStorage.getItem('userEmail'),
                localStorage.getItem('fullName')
            );
        }

        // Reload profile to refresh everything
        clearPageCache('profile');
        await loadProfile();
    } catch (err) {
        console.error('handleUpdateProfile:', err);
        showToast('Network error', 'error');
    } finally {
        btn.disabled = false;
        btn.innerHTML = `<svg width="16" height="16" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M5 13l4 4L19 7"/></svg> Save Changes`;
    }
}

// ============================================================
// CHANGE PASSWORD
// ============================================================

function togglePasswordVisibility(inputId, btn) {
    const input = document.getElementById(inputId);
    if (!input) return;
    const isHidden = input.type === 'password';
    input.type = isHidden ? 'text' : 'password';
    btn.querySelector('.eye-open').style.display = isHidden ? 'none' : '';
    btn.querySelector('.eye-closed').style.display = isHidden ? '' : 'none';
    btn.title = isHidden ? 'Hide password' : 'Show password';
}

function resetPasswordForm() {
    document.getElementById('changePasswordForm').reset();
    const fill = document.getElementById('strengthBarFill');
    const text = document.getElementById('strengthText');
    if (fill) { fill.className = 'strength-bar-fill'; }
    if (text) { text.className = 'strength-text'; text.textContent = ''; }
    const hint = document.getElementById('passwordMatchHint');
    if (hint) hint.textContent = '';
    // Reset requirement checklist
    ['reqLength', 'reqUpper', 'reqLower', 'reqDigit'].forEach(id => {
        const li = document.getElementById(id);
        if (li) {
            li.className = '';
            const icon = li.querySelector('.req-icon');
            if (icon) icon.textContent = '\u25cb';
        }
    });
    // Reset eye toggles back to hidden state
    document.querySelectorAll('#changePasswordForm .pw-eye-toggle').forEach(btn => {
        const input = btn.closest('.input-password-wrap')?.querySelector('input');
        if (input) input.type = 'password';
        const open = btn.querySelector('.eye-open');
        const closed = btn.querySelector('.eye-closed');
        if (open) open.style.display = '';
        if (closed) closed.style.display = 'none';
        btn.title = 'Show password';
    });
}

function updatePasswordStrength() {
    const pw = document.getElementById('newPassword').value;
    const fill = document.getElementById('strengthBarFill');
    const text = document.getElementById('strengthText');
    if (!fill || !text) return;

    // Check individual requirements
    const checks = {
        reqLength: pw.length >= 8,
        reqUpper: /[A-Z]/.test(pw),
        reqLower: /[a-z]/.test(pw),
        reqDigit: /\d/.test(pw),
    };

    // Update requirement checklist icons
    for (const [id, met] of Object.entries(checks)) {
        const li = document.getElementById(id);
        if (!li) continue;
        const icon = li.querySelector('.req-icon');
        if (pw.length === 0) {
            li.className = '';
            if (icon) icon.textContent = '○';
        } else if (met) {
            li.className = 'met';
            if (icon) icon.textContent = '✓';
        } else {
            li.className = 'fail';
            if (icon) icon.textContent = '✗';
        }
    }

    let score = 0;
    if (checks.reqLength) score++;
    if (checks.reqUpper) score++;
    if (checks.reqLower) score++;
    if (checks.reqDigit) score++;
    if (/[^A-Za-z0-9]/.test(pw)) score++;

    const levels = ['', 'weak', 'fair', 'good', 'strong', 'strong'];
    const labels = ['', 'Weak', 'Fair', 'Good', 'Strong', 'Strong'];
    const level = levels[score] || '';

    fill.className = `strength-bar-fill ${level}`;
    text.className = `strength-text ${level}`;
    text.textContent = pw.length > 0 ? labels[score] : '';

    // Also check match hint
    checkPasswordMatch();
}

function checkPasswordMatch() {
    const pw = document.getElementById('newPassword').value;
    const confirm = document.getElementById('confirmPassword').value;
    const hint = document.getElementById('passwordMatchHint');
    if (!hint || !confirm) return;

    if (confirm.length === 0) {
        hint.textContent = '';
        hint.style.color = '';
    } else if (pw === confirm) {
        hint.textContent = '✓ Passwords match';
        hint.style.color = 'var(--success)';
    } else {
        hint.textContent = '✗ Passwords do not match';
        hint.style.color = 'var(--error)';
    }
}

/**
 * Validate new password client-side before calling API.
 * Returns an error string or null if valid.
 */
function validateNewPassword(pw) {
    if (pw.length < 8) return 'Password must be at least 8 characters';
    if (!/[A-Z]/.test(pw)) return 'Password must contain at least one uppercase letter';
    if (!/[a-z]/.test(pw)) return 'Password must contain at least one lowercase letter';
    if (!/\d/.test(pw)) return 'Password must contain at least one digit';
    return null;
}

async function handleChangePassword(e) {
    e.preventDefault();
    const btn = document.getElementById('btnChangePassword');
    const current = document.getElementById('currentPassword').value;
    const newPw = document.getElementById('newPassword').value;
    const confirm = document.getElementById('confirmPassword').value;

    // Client-side validation — highlight failing requirements
    const validationError = validateNewPassword(newPw);
    if (validationError) {
        // Trigger the strength meter to highlight failures
        updatePasswordStrength();
        // Scroll the password field into view
        document.getElementById('newPassword').focus();
        showToast(validationError, 'error');
        return;
    }

    if (newPw !== confirm) {
        document.getElementById('confirmPassword').focus();
        showToast('Passwords do not match', 'error');
        return;
    }

    btn.disabled = true;
    btn.innerHTML = '<span class="loading-spinner" style="width:16px;height:16px"></span> Updating...';

    try {
        const res = await fetch(`${PROFILE_API}/user/change-password`, {
            method: 'POST',
            headers: profileAuthHeaders(),
            body: JSON.stringify({
                current_password: current,
                new_password: newPw
            })
        });

        if (handleAuthError(res)) return;

        const result = await res.json();
        if (!res.ok) {
            // Focus the current password field on auth error
            if (result.detail && result.detail.toLowerCase().includes('current password')) {
                document.getElementById('currentPassword').focus();
            }
            showToast(result.detail || 'Failed to change password', 'error');
            return;
        }

        showToast('Password changed successfully!', 'success');
        showSuccessAnimation('Password Changed!');
        markProfileClean();
        resetPasswordForm();

        // Token version was bumped — current token is now invalid.
        // Show a warning toast, then logout.
        setTimeout(() => {
            showToast('Logging you out. Please log in with your new password.', 'info');
            setTimeout(() => logout(), 2500);
        }, 2000);
    } catch (err) {
        console.error('handleChangePassword:', err);
        showToast('Network error', 'error');
    } finally {
        btn.disabled = false;
        btn.innerHTML = `<svg width="16" height="16" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 15v2m-6 4h12a2 2 0 002-2v-6a2 2 0 00-2-2H6a2 2 0 00-2 2v6a2 2 0 002 2zm10-10V7a4 4 0 00-8 0v4h8z"/></svg> Update Password`;
    }
}

// Hook up confirm field on input
document.addEventListener('input', (e) => {
    if (e.target.id === 'confirmPassword') checkPasswordMatch();
});

// ============================================================
// MFA — Status, Enable, Disable, Backup Codes
// ============================================================

async function loadMfaStatus() {
    try {
        const res = await fetch(`${PROFILE_API}/auth/mfa/status`, {
            headers: profileAuthHeaders()
        });
        if (handleAuthError(res)) return;
        if (!res.ok) throw new Error('MFA status check failed');

        const data = await res.json();
        renderMfaStatus(data);
    } catch (err) {
        console.error('loadMfaStatus:', err);
    }
}

function renderMfaStatus(mfa) {
    const icon = document.getElementById('mfaStatusIcon');
    const title = document.getElementById('mfaStatusTitle');
    const desc = document.getElementById('mfaStatusDesc');
    const actions = document.getElementById('mfaActionButtons');

    if (mfa.mfa_enabled) {
        icon.className = 'mfa-status-icon enabled';
        icon.innerHTML = `<svg width="24" height="24" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 12l2 2 4-4m5.618-4.016A11.955 11.955 0 0112 2.944a11.955 11.955 0 01-8.618 3.04A12.02 12.02 0 003 9c0 5.591 3.824 10.29 9 11.622 5.176-1.332 9-6.03 9-11.622 0-1.042-.133-2.052-.382-3.016z"/></svg>`;
        title.textContent = '2FA is Enabled';
        desc.textContent = 'Your account is protected with two-factor authentication.';
        actions.innerHTML = `
            <button class="p-btn p-btn-secondary p-btn-sm" onclick="handleViewBackupCodes()">View Backup Codes</button>
            <button class="p-btn p-btn-secondary p-btn-sm" onclick="handleRegenerateBackupCodes()">Regenerate Codes</button>
            <button class="p-btn p-btn-danger p-btn-sm" onclick="handleDisableMfa()">Disable 2FA</button>
        `;
    } else {
        icon.className = 'mfa-status-icon disabled';
        icon.innerHTML = `<svg width="24" height="24" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 15v2m-6 4h12a2 2 0 002-2v-6a2 2 0 00-2-2H6a2 2 0 00-2 2v6a2 2 0 002 2zm10-10V7a4 4 0 00-8 0v4h8z"/></svg>`;
        title.textContent = '2FA is Disabled';
        desc.textContent = 'Add an extra layer of security to your account.';
        actions.innerHTML = `
            <button class="p-btn p-btn-success p-btn-sm" onclick="handleEnableMfa()">Enable 2FA</button>
        `;
    }

    // Hide setup area when status refreshes
    document.getElementById('mfaSetupArea').classList.remove('active');
    document.getElementById('mfaBackupArea').classList.remove('active');
}

// --- Enable MFA (step 1: get QR) ---
async function handleEnableMfa() {
    try {
        const res = await fetch(`${PROFILE_API}/user/mfa/setup`, {
            method: 'POST',
            headers: profileAuthHeaders()
        });
        if (handleAuthError(res)) return;
        const data = await res.json();
        if (!res.ok) {
            showToast(data.detail || 'Failed to start MFA setup', 'error');
            return;
        }

        // Show setup area with QR
        document.getElementById('mfaQrImage').src = data.qr_code;
        document.getElementById('mfaSecretKey').textContent = data.secret;
        document.getElementById('mfaVerifyCode').value = '';
        document.getElementById('mfaSetupArea').classList.add('active');
        document.getElementById('mfaBackupArea').classList.remove('active');
    } catch (err) {
        console.error('handleEnableMfa:', err);
        showToast('Network error', 'error');
    }
}

// --- Enable MFA (step 2: verify TOTP code) ---
async function handleVerifyMfaSetup() {
    const code = document.getElementById('mfaVerifyCode').value.trim();
    if (code.length !== 6) {
        showToast('Enter the 6-digit code from your authenticator', 'error');
        return;
    }

    try {
        const res = await fetch(`${PROFILE_API}/user/mfa/verify-setup`, {
            method: 'POST',
            headers: profileAuthHeaders(),
            body: JSON.stringify({ code })
        });
        if (handleAuthError(res)) return;
        const data = await res.json();
        if (!res.ok) {
            showToast(data.detail || 'Verification failed', 'error');
            return;
        }

        showToast('2FA enabled successfully!', 'success');

        // Show backup codes if returned
        if (data.backup_codes && data.backup_codes.length) {
            _backupCodesCache = data.backup_codes;
            renderBackupCodes(data.backup_codes);
            document.getElementById('mfaSetupArea').classList.remove('active');
            document.getElementById('mfaBackupArea').classList.add('active');
        } else {
            document.getElementById('mfaSetupArea').classList.remove('active');
        }

        // Refresh MFA status & profile badge
        await loadMfaStatus();
        await loadProfile();
    } catch (err) {
        console.error('handleVerifyMfaSetup:', err);
        showToast('Network error', 'error');
    }
}

// --- Disable MFA ---
async function handleDisableMfa() {
    if (!confirm('Are you sure you want to disable 2FA? This will make your account less secure.')) return;

    try {
        const res = await fetch(`${PROFILE_API}/auth/mfa/disable`, {
            method: 'POST',
            headers: profileAuthHeaders()
        });
        if (handleAuthError(res)) return;
        const data = await res.json();
        if (!res.ok) {
            showToast(data.detail || 'Failed to disable MFA', 'error');
            return;
        }

        showToast('2FA has been disabled', 'success');
        await loadMfaStatus();
        await loadProfile();
    } catch (err) {
        console.error('handleDisableMfa:', err);
        showToast('Network error', 'error');
    }
}

// --- View / Regenerate Backup Codes ---
async function handleViewBackupCodes() {
    // The status endpoint tells us remaining count; show a message
    showToast('Backup codes were shown only when 2FA was first enabled or regenerated. Click "Regenerate Codes" to get new ones.', 'info');
}

async function handleRegenerateBackupCodes() {
    if (!confirm('Regenerating backup codes will invalidate all previous codes. Continue?')) return;

    try {
        const res = await fetch(`${PROFILE_API}/auth/mfa/regenerate-backup-codes`, {
            method: 'POST',
            headers: profileAuthHeaders()
        });
        if (handleAuthError(res)) return;
        const data = await res.json();
        if (!res.ok) {
            showToast(data.detail || 'Failed to regenerate codes', 'error');
            return;
        }

        _backupCodesCache = data.backup_codes || [];
        renderBackupCodes(_backupCodesCache);
        document.getElementById('mfaBackupArea').classList.add('active');
        showToast('New backup codes generated — save them now!', 'success');
    } catch (err) {
        console.error('handleRegenerateBackupCodes:', err);
        showToast('Network error', 'error');
    }
}

function renderBackupCodes(codes) {
    const grid = document.getElementById('backupCodesGrid');
    if (!grid) return;
    grid.innerHTML = codes.map(c => `<div class="backup-code">${c}</div>`).join('');
}

function copyBackupCodes() {
    if (_backupCodesCache.length === 0) {
        showToast('No backup codes to copy', 'error');
        return;
    }
    const text = _backupCodesCache.join('\n');
    copyToClipboard(text);
}

function hideBackupCodes() {
    document.getElementById('mfaBackupArea').classList.remove('active');
}

// ============================================================
// DELETE ACCOUNT
// ============================================================

function openDeleteAccountModal() {
    document.getElementById('deleteAccountModal').classList.add('active');
    document.getElementById('deletePassword').value = '';
    document.getElementById('deleteConfirmation').value = '';
}

function closeDeleteAccountModal() {
    document.getElementById('deleteAccountModal').classList.remove('active');
}

async function handleDeleteAccount(e) {
    e.preventDefault();
    const password = document.getElementById('deletePassword').value;
    const confirmation = document.getElementById('deleteConfirmation').value;

    if (!password) {
        showToast('Please enter your password', 'error');
        return;
    }
    if (confirmation !== 'DELETE MY ACCOUNT') {
        showToast('Please type "DELETE MY ACCOUNT" exactly', 'error');
        return;
    }

    const btn = document.getElementById('btnConfirmDelete');
    btn.disabled = true;
    btn.innerHTML = '<span class="loading-spinner" style="width:16px;height:16px"></span> Deleting...';

    try {
        const res = await fetch(`${PROFILE_API}/user/delete-account`, {
            method: 'POST',
            headers: profileAuthHeaders(),
            body: JSON.stringify({ password, confirmation })
        });

        if (handleAuthError(res)) return;

        const data = await res.json();
        if (!res.ok) {
            showToast(data.detail || 'Failed to delete account', 'error');
            return;
        }

        showToast('Account deleted. Redirecting...', 'success');
        setTimeout(() => {
            localStorage.clear();
            window.location.replace('http://localhost:3000/login.html');
        }, 2000);
    } catch (err) {
        console.error('handleDeleteAccount:', err);
        showToast('Network error', 'error');
    } finally {
        btn.disabled = false;
        btn.innerHTML = `<svg width="16" height="16" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16"/></svg> Delete My Account`;
    }
}

// Close modal on overlay click
document.addEventListener('click', (e) => {
    if (e.target.id === 'deleteAccountModal') {
        closeDeleteAccountModal();
    }
});

// ============================================================
// SUCCESS CHECKMARK ANIMATION
// ============================================================

function showSuccessAnimation(label = 'Saved!') {
    const overlay = document.getElementById('successOverlay');
    const labelEl = document.getElementById('successLabel');
    if (!overlay) return;
    if (labelEl) labelEl.textContent = label;
    
    // Reset animation by removing and re-adding
    overlay.classList.remove('active');
    void overlay.offsetWidth; // force reflow
    overlay.classList.add('active');

    setTimeout(() => {
        overlay.classList.remove('active');
    }, 1600);
}

// ============================================================
// COLLAPSE / EXPAND SECTIONS
// ============================================================

function toggleSection(headerEl) {
    const section = headerEl.closest('[data-collapsible]');
    if (!section) return;
    section.classList.toggle('collapsed');
}

// ============================================================
// SECURITY SCORE WIDGET
// ============================================================

function renderSecurityScore(p) {
    const now = Date.now();
    const NINETY_DAYS = 90 * 24 * 60 * 60 * 1000;
    const THIRTY_DAYS = 30 * 24 * 60 * 60 * 1000;

    // Evaluate each criterion
    const criteria = {
        checkMfa: {
            passed: !!(p.mfa_enabled && p.mfa_setup_complete),
            points: 25
        },
        checkPassword: {
            passed: p.password_changed_at
                ? (now - new Date(p.password_changed_at).getTime()) < NINETY_DAYS
                : false,
            points: 25
        },
        checkLogin: {
            passed: p.last_login_at
                ? (now - new Date(p.last_login_at).getTime()) < THIRTY_DAYS
                : false,
            points: 25
        },
        checkActive: {
            passed: !!p.is_active,
            points: 25
        }
    };

    let score = 0;
    for (const [id, c] of Object.entries(criteria)) {
        if (c.passed) score += c.points;
        const li = document.getElementById(id);
        if (!li) continue;
        const icon = li.querySelector('.check-icon');
        if (c.passed) {
            li.className = 'passed';
            if (icon) icon.textContent = '✓';
        } else {
            li.className = 'failed';
            if (icon) icon.textContent = '✗';
        }
    }

    // Determine color tier
    let tier = 'score-low';
    if (score >= 100) tier = 'score-great';
    else if (score >= 75) tier = 'score-good';
    else if (score >= 50) tier = 'score-medium';

    // Animate the ring
    const ring = document.getElementById('scoreRingFill');
    const numEl = document.getElementById('scoreNumber');
    const subtitleEl = document.getElementById('scoreSubtitle');
    const circumference = 2 * Math.PI * 52; // ≈ 326.73

    if (ring) {
        ring.className.baseVal = 'score-ring-fill ' + tier;
        const offset = circumference - (score / 100) * circumference;
        // Small delay to ensure CSS transition fires
        requestAnimationFrame(() => {
            ring.style.strokeDashoffset = offset;
        });
    }

    // Animate the number count-up
    if (numEl) {
        numEl.className = 'score-number ' + tier;
        animateCountUp(numEl, 0, score, 800);
    }

    // Subtitle
    if (subtitleEl) {
        const labels = {
            'score-great': 'Excellent! Your account is fully secured.',
            'score-good': 'Good — just a few improvements left.',
            'score-medium': 'Fair — consider enabling more protections.',
            'score-low': 'At risk — action needed to secure your account.'
        };
        subtitleEl.textContent = labels[tier];
        subtitleEl.style.color = tier === 'score-great' ? 'var(--success)'
            : tier === 'score-good' ? 'var(--accent-primary)'
            : tier === 'score-medium' ? '#d29922'
            : 'var(--error)';
    }
}

function animateCountUp(el, from, to, duration) {
    const start = performance.now();
    function step(now) {
        const elapsed = now - start;
        const progress = Math.min(elapsed / duration, 1);
        // ease-out quad
        const eased = 1 - (1 - progress) * (1 - progress);
        el.textContent = Math.round(from + (to - from) * eased);
        if (progress < 1) requestAnimationFrame(step);
    }
    requestAnimationFrame(step);
}

// ============================================================
// Expose init function for router
// ============================================================
window.initProfilePage = initProfilePage;
