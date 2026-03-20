/* ============================================================
   ADMIN SETTINGS v2 - Tab-Based Layout (admin-settings.js)
   Tab switching, security score ring, login heatmap
   Command bar (Ctrl+K), notification preferences, API calls
   Loaded globally via index.html and called from router onLoad.
   ============================================================ */

var _asProfileData = null;
var _asSessionData = null;
var _asCmdBound = false;

/* Entry point */
function initAdminSettings() {
    _asInitTabs();
    _asInitCmdBar();
    _asInitNotifPrefs();
    bindAdminSettingsEvents();
    loadAdminProfile();
    loadAdminMfaStatus();
    loadAdminSessions();
    loadAdminActivity();
}

/* ============================================================
   TAB SWITCHING
   ============================================================ */
function _asInitTabs() {
    var btns = document.querySelectorAll('.as-tab-btn');
    btns.forEach(function (btn) {
        btn.addEventListener('click', function () {
            _asSwitchTab(btn.getAttribute('data-tab'));
        });
    });
}

function _asSwitchTab(tabName) {
    document.querySelectorAll('.as-tab-btn').forEach(function (b) {
        b.classList.toggle('active', b.getAttribute('data-tab') === tabName);
    });
    document.querySelectorAll('.as-tab-panel').forEach(function (p) {
        p.classList.toggle('active', p.getAttribute('data-panel') === tabName);
    });
}

/* ============================================================
   SECURITY SCORE RING
   ============================================================ */
function _asUpdateScore() {
    var score = 0;
    var circumference = 2 * Math.PI * 52; // r=52

    // MFA: +30
    var mfaOn = _asProfileData && _asProfileData.mfa_enabled && _asProfileData.mfa_setup_complete;
    _asScoreItem('asScoreMfa', mfaOn);
    if (mfaOn) score += 30;

    // Password changed in last 90 days: +25
    var pwdRecent = false;
    if (_asProfileData && _asProfileData.password_changed_at) {
        var diff = Date.now() - new Date(_asProfileData.password_changed_at).getTime();
        pwdRecent = diff < 90 * 24 * 60 * 60 * 1000;
    }
    _asScoreItem('asScorePwd', pwdRecent);
    if (pwdRecent) score += 25;

    // Low session count (<=3): +20
    var lowSessions = _asSessionData ? _asSessionData.length <= 3 : true;
    _asScoreItem('asScoreSessions', lowSessions);
    if (lowSessions) score += 20;

    // Account active: +25
    var isActive = _asProfileData ? _asProfileData.is_active : false;
    _asScoreItem('asScoreActive', isActive);
    if (isActive) score += 25;

    // Animate ring
    var ring = document.getElementById('asRingFill');
    var numEl = document.getElementById('asScoreNum');
    if (ring) {
        var offset = circumference - (score / 100) * circumference;
        ring.style.strokeDashoffset = offset;
        ring.classList.remove('low', 'medium', 'high');
        if (score < 40) ring.classList.add('low');
        else if (score < 75) ring.classList.add('medium');
        else ring.classList.add('high');
    }
    if (numEl) {
        _asAnimateNum(numEl, score);
    }

    // Grade letter
    var gradeEl = document.getElementById('asScoreGrade');
    if (gradeEl) {
        var grade = score >= 90 ? 'A+' : score >= 75 ? 'A' : score >= 60 ? 'B' : score >= 40 ? 'C' : score >= 20 ? 'D' : 'F';
        var gc = score >= 75 ? 'grade-a' : score >= 60 ? 'grade-b' : score >= 40 ? 'grade-c' : score >= 20 ? 'grade-d' : 'grade-f';
        gradeEl.textContent = grade;
        gradeEl.className = 'as-score-grade ' + gc;
    }
}

function _asScoreItem(id, passed) {
    var el = document.getElementById(id);
    if (!el) return;
    el.classList.remove('pass', 'fail');
    el.classList.add(passed ? 'pass' : 'fail');
}

var _asScoreInterval = null;
function _asAnimateNum(el, target) {
    if (_asScoreInterval) clearInterval(_asScoreInterval);
    var current = parseInt(el.textContent) || 0;
    if (current === target) { el.textContent = target; return; }
    var step = target > current ? 1 : -1;
    _asScoreInterval = setInterval(function () {
        current += step;
        el.textContent = current;
        if (current === target) { clearInterval(_asScoreInterval); _asScoreInterval = null; }
    }, 15);
}

/* ============================================================
   COMMAND BAR (Ctrl+K)
   ============================================================ */
function _asInitCmdBar() {
    if (_asCmdBound) return;
    _asCmdBound = true;

    document.addEventListener('keydown', function (e) {
        if ((e.ctrlKey || e.metaKey) && e.key === 'k') {
            e.preventDefault();
            _asCmdToggle();
        }
    });

    var overlay = document.getElementById('asCmdOverlay');
    if (overlay) {
        overlay.addEventListener('click', function (e) {
            if (e.target === overlay) _asCmdClose();
        });
    }

    var input = document.getElementById('asCmdInput');
    if (input) {
        input.addEventListener('input', function () {
            _asCmdFilter(input.value.toLowerCase().trim());
        });
        input.addEventListener('keydown', function (e) {
            if (e.key === 'Escape') _asCmdClose();
            if (e.key === 'Enter') {
                var focused = document.querySelector('.as-cmd-item.focused');
                if (!focused) focused = document.querySelector('.as-cmd-item:not(.hidden)');
                if (focused) focused.click();
            }
            if (e.key === 'ArrowDown' || e.key === 'ArrowUp') {
                e.preventDefault();
                _asCmdNavigate(e.key === 'ArrowDown' ? 1 : -1);
            }
        });
    }

    document.querySelectorAll('.as-cmd-item').forEach(function (item) {
        item.addEventListener('click', function () {
            var action = item.getAttribute('data-action');
            _asCmdClose();
            _asCmdExec(action);
        });
    });
}

function _asCmdToggle() {
    var overlay = document.getElementById('asCmdOverlay');
    if (!overlay) return;
    if (overlay.style.display === 'none') {
        overlay.style.display = '';
        var input = document.getElementById('asCmdInput');
        if (input) { input.value = ''; input.focus(); }
        _asCmdFilter('');
    } else {
        _asCmdClose();
    }
}

function _asCmdClose() {
    var overlay = document.getElementById('asCmdOverlay');
    if (overlay) overlay.style.display = 'none';
}

function _asCmdFilter(q) {
    document.querySelectorAll('.as-cmd-item').forEach(function (item) {
        var text = item.textContent.toLowerCase();
        var match = !q || text.indexOf(q) !== -1;
        item.classList.toggle('hidden', !match);
        item.classList.remove('focused');
    });
    var first = document.querySelector('.as-cmd-item:not(.hidden)');
    if (first) first.classList.add('focused');
}

function _asCmdNavigate(dir) {
    var items = Array.from(document.querySelectorAll('.as-cmd-item:not(.hidden)'));
    if (!items.length) return;
    var idx = items.findIndex(function (i) { return i.classList.contains('focused'); });
    items.forEach(function (i) { i.classList.remove('focused'); });
    idx += dir;
    if (idx < 0) idx = items.length - 1;
    if (idx >= items.length) idx = 0;
    items[idx].classList.add('focused');
    items[idx].scrollIntoView({ block: 'nearest' });
}

function _asCmdExec(action) {
    if (!action) return;
    if (action.indexOf('tab:') === 0) {
        _asSwitchTab(action.split(':')[1]);
    } else if (action === 'revoke-all') {
        revokeAllAdminSessions();
    }
}

/* ============================================================
   NOTIFICATION PREFERENCES
   ============================================================ */
function _asInitNotifPrefs() {
    var saveBtn = document.getElementById('asSaveNotifs');
    if (saveBtn && saveBtn.dataset.bound === 'true') return;

    _asFetch('/user/notification-preferences').then(function (data) {
        var loginToggle = document.getElementById('asNotifLogin');
        var pwdToggle = document.getElementById('asNotifPwd');
        var mfaToggle = document.getElementById('asNotifMfa');
        var failedToggle = document.getElementById('asNotifFailed');
        var digestToggle = document.getElementById('asNotifDigest');
        if (loginToggle) loginToggle.checked = data.new_login_alert_enabled !== false;
        if (pwdToggle) pwdToggle.checked = data.password_change_alert_enabled !== false;
        if (mfaToggle) mfaToggle.checked = data.mfa_change_alert_enabled !== false;
        if (failedToggle) failedToggle.checked = data.failed_login_alert_enabled !== false;
        if (digestToggle) digestToggle.checked = data.weekly_security_digest_enabled === true;
    }).catch(function () { });

    if (saveBtn) {
        saveBtn.dataset.bound = 'true';
        saveBtn.addEventListener('click', function () {
            _asFetch('/user/notification-preferences', {
                method: 'PATCH',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    new_login_alert_enabled: !!((document.getElementById('asNotifLogin') || {}).checked),
                    password_change_alert_enabled: !!((document.getElementById('asNotifPwd') || {}).checked),
                    mfa_change_alert_enabled: !!((document.getElementById('asNotifMfa') || {}).checked),
                    failed_login_alert_enabled: !!((document.getElementById('asNotifFailed') || {}).checked),
                    weekly_security_digest_enabled: !!((document.getElementById('asNotifDigest') || {}).checked)
                })
            }).then(function () {
                _asToast('Notification preferences saved', 'success');
            }).catch(function (err) {
                _asToast('Failed to save notification preferences: ' + err.message, 'error');
            });
        });
    }
}

/* ============================================================
   PROFILE API
   ============================================================ */
function loadAdminProfile() {
    _asFetch('/user/profile').then(function (data) {
        _asProfileData = data;
        var nameEl = document.getElementById('asProfileName');
        var emailEl = document.getElementById('asProfileEmail');
        var avatarEl = document.getElementById('asAvatar');
        var joinEl = document.getElementById('asJoinDate');
        var loginEl = document.getElementById('asLastLogin');
        var keyEl = document.getElementById('asKeyCount');
        var statusEl = document.getElementById('asStatusBadge');
        var pwdEl = document.getElementById('asPwdChanged');
        var fnEl = document.getElementById('asFullName');
        var emEl = document.getElementById('asEmail');
        var geoEl = document.getElementById('asAllowedCountries');

        if (nameEl) nameEl.textContent = _asEsc(data.full_name || 'Admin');
        if (emailEl) emailEl.textContent = _asEsc(data.email || '');
        if (typeof setHeaderUserInfo === 'function') setHeaderUserInfo(data);
        if (fnEl) fnEl.value = data.full_name || '';
        if (emEl) emEl.value = data.email || '';
        if (geoEl) geoEl.value = data.allowed_countries || '';
        _asUpdateGeoPolicyStatus(data.allowed_countries || '');
        if (joinEl) joinEl.textContent = _asFormatDate(data.created_at);
        if (loginEl) loginEl.textContent = data.last_login_at ? _asTimeAgo(data.last_login_at) : 'never';
        if (keyEl) keyEl.textContent = data.active_api_key_count || 0;

        // Load saved timezone into dropdown + show hint
        var tzSel = document.getElementById('asTimezone');
        var savedTz = _asGetTz();
        if (tzSel) {
            var resolvedTz = _asResolveDropdownTz(savedTz, tzSel);
            tzSel.value = resolvedTz;
            _asUpdateTzHint(resolvedTz);
        } else {
            _asUpdateTzHint(savedTz);
        }

        if (statusEl) {
            statusEl.className = 'as-status-badge ' + (data.is_active ? 'active' : '');
            statusEl.innerHTML = '<span class="as-status-dot"></span>' + (data.is_active ? 'Active' : 'Inactive');
        }

        if (pwdEl) {
            pwdEl.textContent = data.password_changed_at ? _asTimeAgo(data.password_changed_at) : 'never';
        }

        if (avatarEl) {
            if (data.avatar) {
                var img = document.createElement('img');
                img.alt = 'avatar';
                img.src = data.avatar;
                avatarEl.textContent = '';
                avatarEl.appendChild(img);
            } else {
                var initials = (data.full_name || 'A').split(' ').map(function (w) { return w[0]; }).join('').substring(0, 2).toUpperCase();
                avatarEl.textContent = initials;
            }
        }

        _asUpdateScore();
    }).catch(function (err) {
        _asToast('Failed to load profile: ' + err.message, 'error');
    });
}

function _asUpdateGeoPolicyStatus(policyText) {
    var statusEl = document.getElementById('asGeoPolicyStatus');
    if (!statusEl) return;

    var normalized = (policyText || '').trim();
    if (!normalized) {
        statusEl.textContent = 'Current policy: Global access allowed';
        return;
    }

    statusEl.textContent = 'Current policy: Only these countries can log in -> ' + normalized;
}

function saveAdminProfile() {
    var name = (document.getElementById('asFullName') || {}).value || '';
    var email = (document.getElementById('asEmail') || {}).value || '';
    if (!name.trim() || !email.trim()) return _asToast('Name and email are required', 'error');

    // Save timezone preference to localStorage
    var tzSel = document.getElementById('asTimezone');
    if (tzSel && tzSel.value) {
        localStorage.setItem('as_timezone', _asNormalizeTz(tzSel.value));
    }

    var btn = document.getElementById('asSaveProfile');
    _asBtnLoading(btn, true);

    _asFetch('/user/profile', {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ full_name: name.trim(), email: email.trim() })
    }).then(function () {
        _asBtnLoading(btn, false);
        _asToast('Profile updated - Timezone set to ' + _asGetTz(), 'success');
        loadAdminProfile();
    }).catch(function (err) {
        _asBtnLoading(btn, false);
        _asToast('Update failed: ' + err.message, 'error');
    });
}

/* ============================================================
   AVATAR
   ============================================================ */
function handleAvatarUpload(file) {
    if (!file) return;
    if (file.size > 2 * 1024 * 1024) return _asToast('Image must be under 2 MB', 'error');
    if (!/^image\/(png|jpeg|gif|webp)$/.test(file.type)) {
        return _asToast('Only PNG, JPEG, GIF, or WebP images are allowed', 'error');
    }

    var reader = new FileReader();
    reader.onload = function () {
        _asFetch('/user/avatar', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ avatar: reader.result })
        })
            .then(function () {
                _asToast('Avatar updated', 'success');
                loadAdminProfile();
            })
            .catch(function (err) { _asToast('Upload failed: ' + err.message, 'error'); });
    };
    reader.onerror = function () {
        _asToast('Upload failed: could not read the image file', 'error');
    };
    reader.readAsDataURL(file);
}

/* ============================================================
   PASSWORD
   ============================================================ */
function changeAdminPassword() {
    var cur = (document.getElementById('asCurPwd') || {}).value || '';
    var nw = (document.getElementById('asNewPwd') || {}).value || '';
    var cnf = (document.getElementById('asConfirmPwd') || {}).value || '';

    if (!cur || !nw) return _asToast('Fill in all password fields', 'error');
    if (nw !== cnf) return _asToast('Passwords do not match', 'error');
    if (nw.length < 8) return _asToast('Password must be at least 8 characters', 'error');

    var btn = document.getElementById('asChangePassword');
    _asBtnLoading(btn, true);

    _asFetch('/user/change-password', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ current_password: cur, new_password: nw })
    }).then(function () {
        _asBtnLoading(btn, false);
        _asToast('Password changed successfully', 'success');
        document.getElementById('asCurPwd').value = '';
        document.getElementById('asNewPwd').value = '';
        document.getElementById('asConfirmPwd').value = '';
        _asUpdatePwdStrength('');
        loadAdminProfile();
    }).catch(function (err) {
        _asBtnLoading(btn, false);
        _asToast('Password change failed: ' + err.message, 'error');
    });
}

function _asUpdatePwdStrength(val) {
    var bar = document.getElementById('asPwdBarFill');
    var label = document.getElementById('asPwdLabel');
    if (!bar || !label) return;

    var s = 0;
    if (val.length >= 8) s++;
    if (/[A-Z]/.test(val)) s++;
    if (/[a-z]/.test(val)) s++;
    if (/[0-9]/.test(val)) s++;
    if (/[^A-Za-z0-9]/.test(val)) s++;

    var pct = (s / 5) * 100;
    var colors = ['', '#EF4444', '#F59E0B', '#F59E0B', '#3B82F6', '#10B981'];
    var labels = ['', 'Very Weak', 'Weak', 'Fair', 'Strong', 'Very Strong'];
    bar.style.width = pct + '%';
    bar.style.background = colors[s] || '';
    label.textContent = val ? labels[s] : '';
    label.style.color = colors[s] || '';

    // Live requirement checks
    var reqs = { length: val.length >= 8, upper: /[A-Z]/.test(val), lower: /[a-z]/.test(val), number: /[0-9]/.test(val), special: /[^A-Za-z0-9]/.test(val) };
    document.querySelectorAll('.as-pwd-reqs li').forEach(function (li) {
        var key = li.getAttribute('data-req');
        li.classList.toggle('met', !!reqs[key]);
    });
}

/* ============================================================
   MFA
   ============================================================ */
function loadAdminMfaStatus() {
    _asFetch('/auth/mfa/status').then(function (data) {
        var badge = document.getElementById('asMfaBadge');
        var dEl = document.getElementById('asMfaDisabled');
        var sEl = document.getElementById('asMfaSetup');
        var eEl = document.getElementById('asMfaEnabled');

        var enabled = data.mfa_enabled && data.mfa_setup_complete;
        if (badge) {
            badge.textContent = enabled ? 'Enabled' : 'Disabled';
            badge.className = 'as-mfa-badge ' + (enabled ? 'enabled' : 'disabled');
        }
        if (dEl) dEl.style.display = enabled ? 'none' : '';
        if (sEl) sEl.style.display = 'none';
        if (eEl) eEl.style.display = enabled ? '' : 'none';
    }).catch(function () { });
}

function setupAdminMfa() {
    var dEl = document.getElementById('asMfaDisabled');
    var sEl = document.getElementById('asMfaSetup');
    if (dEl) dEl.style.display = 'none';
    if (sEl) sEl.style.display = '';

    _asFetch('/user/mfa/setup', { method: 'POST' }).then(function (data) {
        var qrBox = document.getElementById('asMfaQrBox');
        var secretEl = document.getElementById('asMfaSecret');
        if (qrBox && data.qr_code) {
            qrBox.innerHTML = '<img src="' + data.qr_code + '" alt="QR Code">';
        }
        if (secretEl && data.secret) {
            secretEl.textContent = data.secret;
        }
    }).catch(function (err) {
        _asToast('MFA setup failed: ' + err.message, 'error');
        if (dEl) dEl.style.display = '';
        if (sEl) sEl.style.display = 'none';
    });
}

function verifyAdminMfa() {
    var code = (document.getElementById('asMfaCode') || {}).value || '';
    if (code.length !== 6) return _asToast('Enter a 6-digit code', 'error');

    _asFetch('/user/mfa/verify-setup', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ code: code })
    }).then(function (data) {
        _asToast('MFA enabled successfully!', 'success');
        loadAdminMfaStatus();
        if (data.backup_codes) _asShowBackupCodes(data.backup_codes);
        loadAdminProfile();
    }).catch(function (err) {
        _asToast('Verification failed: ' + err.message, 'error');
    });
}

function disableAdminMfa() {
    _asShowModal('Disable MFA', '<p>Are you sure? This will remove two-factor authentication from your admin account.</p>', function () {
        _asFetch('/auth/mfa/disable', { method: 'POST' }).then(function () {
            _asToast('MFA disabled', 'success');
            _asCloseModal();
            loadAdminMfaStatus();
            loadAdminProfile();
        }).catch(function (err) {
            _asToast('Failed: ' + err.message, 'error');
        });
    });
}

function regenerateAdminBackupCodes() {
    _asFetch('/auth/mfa/regenerate-backup-codes', { method: 'POST' }).then(function (data) {
        if (data.backup_codes) _asShowBackupCodes(data.backup_codes);
        _asToast('Backup codes regenerated', 'success');
    }).catch(function (err) {
        _asToast('Failed: ' + err.message, 'error');
    });
}

function _asShowBackupCodes(codes) {
    var wrap = document.getElementById('asBackupCodes');
    var grid = document.getElementById('asBackupGrid');
    if (!wrap || !grid) return;
    wrap.style.display = '';
    grid.innerHTML = codes.map(function (c) { return '<code>' + _asEsc(c) + '</code>'; }).join('');
}

/* ============================================================
   SESSIONS
   ============================================================ */
function loadAdminSessions() {
    _asFetch('/user/sessions').then(function (data) {
        _asSessionData = data;
        var tbody = document.getElementById('asSessionsBody');
        var countEl = document.getElementById('asSessionCount');
        if (countEl) countEl.textContent = data.length + ' session' + (data.length !== 1 ? 's' : '');

        if (!tbody) return;
        if (!data.length) {
            tbody.innerHTML = '<tr><td colspan="6" class="as-loading-row">No active sessions</td></tr>';
            _asUpdateScore();
            return;
        }

        tbody.innerHTML = '';
        data.forEach(function (s) {
            var isCurrent = s.is_current;
            var tr = document.createElement('tr');

            var tdDevice = document.createElement('td');
            tdDevice.textContent = s.device_label || s.device || 'Unknown';
            if (isCurrent) { var badge = document.createElement('span'); badge.className = 'as-current-badge'; badge.textContent = 'current'; tdDevice.appendChild(badge); }
            tr.appendChild(tdDevice);

            var tdIp = document.createElement('td');
            var ipCode = document.createElement('code');
            ipCode.style.fontSize = '12px';
            ipCode.textContent = s.ip_address || '-';
            tdIp.appendChild(ipCode);
            tr.appendChild(tdIp);

            var tdLoc = document.createElement('td');
            var locText = document.createElement('span');
            if (s.country && s.country !== 'Local Network') {
                locText.textContent = (s.city ? s.city + ', ' : '') + s.country;
            } else if (s.country === 'Local Network') {
                locText.textContent = 'Local Network';
            } else {
                locText.textContent = '-';
            }
            tdLoc.appendChild(locText);
            
            if (s.is_new_location) {
                var newBadge = document.createElement('span');
                newBadge.className = 'as-current-badge';
                newBadge.style.cssText = 'background:rgba(239,68,68,0.1);color:#ef4444;border-color:rgba(239,68,68,0.2);margin-left:8px;';
                newBadge.innerHTML = '&#9888; New Location';
                tdLoc.appendChild(newBadge);
            }
            tr.appendChild(tdLoc);

            var tdActive = document.createElement('td');
            tdActive.textContent = _asTimeAgo(s.last_active_at || s.updated_at);
            tr.appendChild(tdActive);

            var tdCreated = document.createElement('td');
            tdCreated.textContent = _asFormatDate(s.created_at);
            tr.appendChild(tdCreated);

            var tdAction = document.createElement('td');
            if (!isCurrent) {
                var btn = document.createElement('button');
                btn.className = 'as-btn-icon';
                btn.title = 'Revoke';
                btn.innerHTML = '<svg width="14" height="14" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12"/></svg>';
                btn.addEventListener('click', (function (sid) { return function () { revokeSession(sid); }; })(s.id));
                tdAction.appendChild(btn);
            }
            tr.appendChild(tdAction);

            tbody.appendChild(tr);
        });

        _asUpdateScore();
    }).catch(function (err) {
        _asToast('Failed to load sessions: ' + err.message, 'error');
    });
}

function revokeSession(id) {
    _asFetch('/user/sessions/' + id, { method: 'DELETE' }).then(function () {
        _asToast('Session revoked', 'success');
        loadAdminSessions();
    }).catch(function (err) {
        _asToast('Revoke failed: ' + err.message, 'error');
    });
}

function revokeAllAdminSessions() {
    _asShowModal('Revoke All Sessions', '<p>This will log you out of all other devices. Continue?</p>', function () {
        _asFetch('/user/sessions', { method: 'DELETE' }).then(function () {
            _asToast('All other sessions revoked', 'success');
            _asCloseModal();
            loadAdminSessions();
        }).catch(function (err) {
            _asToast('Failed: ' + err.message, 'error');
        });
    });
}

/* ============================================================
   ACTIVITY + HEATMAP
   ============================================================ */
function loadAdminActivity() {
    _asFetch('/user/audit-log?limit=50').then(function (events) {
        _asRenderActivity(events);
        _asRenderHeatmap(events);
    }).catch(function () {
        var list = document.getElementById('asActivityList');
        if (list) list.innerHTML = '<div class="as-activity-empty">No activity data available</div>';
        _asRenderHeatmap([]);
    });
}

function _asRenderActivity(events) {
    var list = document.getElementById('asActivityList');
    if (!list) return;

    if (!events || !events.length) {
        list.innerHTML = '<div class="as-activity-empty">No recent activity</div>';
        return;
    }

    var iconMap = {
        login: { cls: 'login', icon: '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M15 3h4a2 2 0 0 1 2 2v14a2 2 0 0 1-2 2h-4"/><path d="M10 17l5-5-5-5"/><path d="M15 12H3"/></svg>' },
        login_failed: { cls: 'danger', icon: '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M10.3 3.9 1.8 18a2 2 0 0 0 1.7 3h17a2 2 0 0 0 1.7-3L13.7 3.9a2 2 0 0 0-3.4 0Z"/><path d="M12 9v4"/><path d="M12 17h.01"/></svg>' },
        password_changed: { cls: 'password', icon: '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="3" y="11" width="18" height="10" rx="2"/><path d="M7 11V7a5 5 0 0 1 10 0v4"/></svg>' },
        profile_updated: { cls: 'login', icon: '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M12 20h9"/><path d="m16.5 3.5 4 4L7 21H3v-4Z"/></svg>' },
        mfa_enabled: { cls: 'mfa', icon: '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M20 13c0 5-3.5 7.5-8 9-4.5-1.5-8-4-8-9V6l8-4 8 4z"/><path d="m9 12 2 2 4-4"/></svg>' },
        mfa_disabled: { cls: 'danger', icon: '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M20 13c0 5-3.5 7.5-8 9-4.5-1.5-8-4-8-9V6l8-4 8 4z"/><path d="m9 9 6 6"/><path d="m15 9-6 6"/></svg>' },
        session_revoked: { cls: 'session', icon: '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M18 6 6 18"/><path d="m6 6 12 12"/></svg>' },
        sessions_revoked_all: { cls: 'session', icon: '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M3 12a9 9 0 1 0 3-6.7"/><path d="M3 3v6h6"/></svg>' }
    };

    var html = events.slice(0, 25).map(function (ev) {
        var type = (ev.event_type || '').toLowerCase();
        var info = iconMap[type] || { cls: 'default', icon: '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M8 2h8"/><path d="M9 2v3"/><path d="M15 2v3"/><rect x="4" y="5" width="16" height="17" rx="2"/><path d="M8 10h8"/><path d="M8 14h8"/><path d="M8 18h5"/></svg>' };
        var label = type.replace(/_/g, ' ').replace(/\b\w/g, function (c) { return c.toUpperCase(); });
        return '<div class="as-activity-item">' +
            '<div class="as-activity-icon ' + info.cls + '">' + info.icon + '</div>' +
            '<div class="as-activity-info"><strong>' + _asEsc(label) + '</strong><span>' + _asEsc(ev.detail || '') + (ev.ip_address ? ' - ' + _asEsc(ev.ip_address) : '') + '</span></div>' +
            '<span class="as-activity-time">' + _asTimeAgo(ev.created_at) + '</span>' +
            '</div>';
    }).join('');

    list.innerHTML = html;
}

function _asRenderHeatmap(events) {
    var grid = document.getElementById('asHeatmapGrid');
    if (!grid) return;

    var matrix = [];
    var dayLabels = [];
    var now = new Date();
    for (var d = 6; d >= 0; d--) {
        var day = new Date(now);
        day.setDate(day.getDate() - d);
        dayLabels.push(day.toLocaleDateString('en-US', { weekday: 'short' }));
        var row = [0, 0, 0, 0, 0, 0, 0, 0];
        matrix.push(row);
    }

    if (events && events.length) {
        events.forEach(function (ev) {
            var ts = new Date(ev.created_at);
            var diffDays = Math.floor((now - ts) / (24 * 60 * 60 * 1000));
            if (diffDays < 0 || diffDays > 6) return;
            var dayIdx = 6 - diffDays;
            var hour = ts.getHours();
            var block = Math.floor(hour / 3);
            matrix[dayIdx][block]++;
        });
    }

    var maxVal = 1;
    matrix.forEach(function (row) { row.forEach(function (v) { if (v > maxVal) maxVal = v; }); });

    var html = '';
    for (var i = 0; i < 7; i++) {
        html += '<div class="as-heat-day-label">' + dayLabels[i] + '</div>';
        for (var j = 0; j < 8; j++) {
            var val = matrix[i][j];
            var level = 0;
            if (val > 0) level = 1;
            if (val >= maxVal * 0.4) level = 2;
            if (val >= maxVal * 0.75) level = 3;
            html += '<div class="as-heat-cell" data-level="' + level + '" title="' + val + ' event' + (val !== 1 ? 's' : '') + '"></div>';
        }
    }
    grid.innerHTML = html;
}

/* ============================================================
   DELETE ACCOUNT
   ============================================================ */
function deleteAdminAccount() {
    var overlay = document.getElementById('asModalOverlay');
    var title = document.getElementById('asModalTitle');
    var body = document.getElementById('asModalBody');
    var btn = document.getElementById('asModalConfirm');
    if (!overlay || !body || !btn) return;

    if (title) title.textContent = 'Delete Admin Account';
    body.innerHTML = '<p style="color:var(--error); font-weight:500;">This action is permanent and cannot be undone.</p>' +
        '<p>Enter your password and type <strong>DELETE MY ACCOUNT</strong> to confirm.</p>' +
        '<input type="password" id="asDeletePwd" placeholder="Current password" autocomplete="current-password">' +
        '<input type="text" id="asDeleteConfirm" placeholder="Type DELETE MY ACCOUNT" autocomplete="off" style="margin-top:8px">';
    btn.textContent = 'Delete Permanently';
    overlay.style.display = '';

    btn.onclick = function () {
        var pwd = (document.getElementById('asDeletePwd') || {}).value || '';
        var conf = (document.getElementById('asDeleteConfirm') || {}).value || '';
        if (!pwd) return _asToast('Password is required', 'error');
        if (conf !== 'DELETE MY ACCOUNT') return _asToast('Confirmation text does not match', 'error');

        _asFetch('/user/delete-account', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ password: pwd, confirmation: conf })
        }).then(function () {
            _asToast('Account deleted', 'info');
            _asCloseModal();
            localStorage.removeItem('token');
            setTimeout(function () { window.location.href = '/'; }, 1500);
        }).catch(function (err) {
            _asToast('Deletion failed: ' + err.message, 'error');
        });
    };
}

/* ============================================================
   EVENT BINDINGS
   ============================================================ */
function bindAdminSettingsEvents() {
    _asClick('asSaveProfile', saveAdminProfile);

    // Live timezone preview on dropdown change
    var tzSel = document.getElementById('asTimezone');
    if (tzSel) {
        tzSel.addEventListener('change', function () {
            _asUpdateTzHint(tzSel.value);
        });
    }

    _asClick('asAvatarUpload', function () {
        var inp = document.getElementById('asAvatarInput');
        if (inp) inp.click();
    });
    var avatarInput = document.getElementById('asAvatarInput');
    if (avatarInput) avatarInput.addEventListener('change', function () {
        if (this.files && this.files[0]) handleAvatarUpload(this.files[0]);
    });

    _asClick('asChangePassword', changeAdminPassword);
    var newPwd = document.getElementById('asNewPwd');
    if (newPwd) newPwd.addEventListener('input', function () { _asUpdatePwdStrength(this.value); });

    document.querySelectorAll('.as-pwd-toggle').forEach(function (btn) {
        btn.addEventListener('click', function () {
            var target = document.getElementById(btn.getAttribute('data-target'));
            if (!target) return;
            target.type = target.type === 'password' ? 'text' : 'password';
        });
    });

    _asClick('asMfaSetupBtn', setupAdminMfa);
    _asClick('asMfaVerifyBtn', verifyAdminMfa);
    _asClick('asMfaCancelBtn', function () { loadAdminMfaStatus(); });
    _asClick('asDisableMfa', disableAdminMfa);
    _asClick('asRegenBackup', regenerateAdminBackupCodes);
    _asClick('asCopySecret', function () {
        var el = document.getElementById('asMfaSecret');
        if (el) { navigator.clipboard.writeText(el.textContent); _asToast('Secret copied', 'info'); }
    });
    _asClick('asCopyBackup', function () {
        var codes = Array.from(document.querySelectorAll('#asBackupGrid code')).map(function (c) { return c.textContent; });
        navigator.clipboard.writeText(codes.join('\n'));
        _asToast('Backup codes copied', 'info');
    });

    _asClick('asSaveGeoBlocking', function () {
        var btn = document.getElementById('asSaveGeoBlocking');
        var geoInput = document.getElementById('asAllowedCountries');
        if (!geoInput) return;
        _asBtnLoading(btn, true);
        _asFetch('/user/profile', {
            method: 'PATCH',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ allowed_countries: geoInput.value })
        }).then(function (data) {
            _asBtnLoading(btn, false);
            if (geoInput) geoInput.value = data.allowed_countries || '';
            _asUpdateGeoPolicyStatus(data.allowed_countries || '');
            _asToast('ZTNA Geo-Blocking policy saved', 'success');
            loadAdminProfile();
        }).catch(function (err) {
            _asBtnLoading(btn, false);
            _asToast('Failed to save policy: ' + err.message, 'error');
        });
    });

    _asClick('asDownloadBackup', function () {
        var codes = Array.from(document.querySelectorAll('#asBackupGrid code')).map(function (c) { return c.textContent; });
        var blob = new Blob([codes.join('\n')], { type: 'text/plain' });
        var a = document.createElement('a');
        a.href = URL.createObjectURL(blob);
        a.download = 'backup-codes.txt';
        a.click();
    });

    _asClick('asRevokeAll', revokeAllAdminSessions);
    _asClick('asDeleteAccount', deleteAdminAccount);

    _asClick('asExportAuditLog', function () {
        var btn = document.getElementById('asExportAuditLog');
        if (btn) {
            btn.disabled = true;
            btn.innerHTML = 'Exporting...';
        }
        var token = localStorage.getItem('token') || '';
        fetch(API_URL + '/user/audit-log/export', {
            headers: { 'Authorization': 'Bearer ' + token }
        }).then(function(res) {
            if (!res.ok) throw new Error('Export failed. Check console.');
            
            // Try extracting filename from headers, fallback to generic
            var cd = res.headers.get('content-disposition');
            var filename = 'audit_logs.csv';
            if (cd) {
                var m = cd.match(/filename="?([^";]+)"?/);
                if (m) filename = m[1];
            }
            
            return res.blob().then(function(blob) {
                var a = document.createElement('a');
                a.href = URL.createObjectURL(blob);
                a.download = filename;
                document.body.appendChild(a);
                a.click();
                document.body.removeChild(a);
                URL.revokeObjectURL(a.href);
            });
        }).then(function() {
            if (btn) {
                btn.disabled = false;
                btn.innerHTML = '<svg width="14" height="14" fill="none" stroke="currentColor" viewBox="0 0 24 24" style="margin-right:4px;"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-4 4m0 0l-4-4m4 4V4" /></svg> Export to CSV';
            }
            _asToast('Export successful', 'success');
        }).catch(function(err) {
            if (btn) {
                btn.disabled = false;
                btn.innerHTML = '<svg width="14" height="14" fill="none" stroke="currentColor" viewBox="0 0 24 24" style="margin-right:4px;"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-4 4m0 0l-4-4m4 4V4" /></svg> Export to CSV';
            }
            _asToast('Error exporting logs: ' + err.message, 'error');
        });
    });

    _asClick('asModalClose', _asCloseModal);
    _asClick('asModalCancel', _asCloseModal);
}

/* ============================================================
   HELPERS
   ============================================================ */
function _asClick(id, fn) {
    var el = document.getElementById(id);
    if (el) el.addEventListener('click', fn);
}

function _asFetch(url, opts) {
    opts = opts || {};
    var token = localStorage.getItem('token') || '';
    var headers = opts.headers || {};
    headers['Authorization'] = 'Bearer ' + token;
    if (opts.rawBody) {
        delete opts.rawBody;
    }
    opts.headers = headers;
    return fetch(API_URL + url, opts).then(function (r) {
        if (r.status === 401) {
            localStorage.removeItem('token');
            localStorage.removeItem('user');
            window.location.replace('http://localhost:3000/login.html');
            return Promise.reject(new Error('Session expired'));
        }
        if (!r.ok) {
            return r.json().then(function (d) {
                var msg = d.detail;
                if (typeof msg === 'object') msg = Array.isArray(msg) ? msg.map(function (e) { return e.msg || JSON.stringify(e); }).join(', ') : JSON.stringify(msg);
                throw new Error(msg || r.statusText);
            }).catch(function (e) {
                if (e instanceof Error) throw e;
                throw new Error(r.statusText);
            });
        }
        if (r.status === 204) return {};
        return r.json();
    });
}

var _asToastIcons = {
    success: '&#10003;',
    error: '&#10007;',
    info: '&#8505;',
    warning: '&#9888;'
};
var _asToastTitles = {
    success: 'Success',
    error: 'Error',
    info: 'Info',
    warning: 'Warning'
};

function _asToast(msg, type, duration) {
    type = type || 'info';
    duration = duration || 3500;
    var container = document.getElementById('asToastContainer');
    if (!container) return;

    var t = document.createElement('div');
    t.className = 'as-toast ' + type;
    t.style.setProperty('--toast-duration', (duration / 1000) + 's');

    t.innerHTML =
        '<span class="as-toast-icon">' + (_asToastIcons[type] || '') + '</span>' +
        '<div class="as-toast-content">' +
        '<div class="as-toast-title">' + (_asToastTitles[type] || 'Notice') + '</div>' +
        '<div class="as-toast-msg">' + _asEsc(msg) + '</div>' +
        '</div>' +
        '<button class="as-toast-close" aria-label="Close">&times;</button>' +
        '<div class="as-toast-progress"></div>';

    container.appendChild(t);

    /* Close on click */
    t.querySelector('.as-toast-close').onclick = function () { _asDismissToast(t); };

    /* Auto dismiss */
    var timer = setTimeout(function () { _asDismissToast(t); }, duration);

    /* Pause on hover */
    t.addEventListener('mouseenter', function () {
        clearTimeout(timer);
        var bar = t.querySelector('.as-toast-progress');
        if (bar) bar.style.animationPlayState = 'paused';
    });
    t.addEventListener('mouseleave', function () {
        var bar = t.querySelector('.as-toast-progress');
        if (bar) bar.style.animationPlayState = 'running';
        timer = setTimeout(function () { _asDismissToast(t); }, 1500);
    });
}

function _asDismissToast(el) {
    if (!el || !el.parentNode) return;
    el.classList.add('as-toast-exit');
    setTimeout(function () { el.remove(); }, 250);
}

function _asEsc(s) {
    var d = document.createElement('div');
    d.textContent = s;
    return d.innerHTML;
}

/* Button loading state */
function _asBtnLoading(btn, loading) {
    if (!btn) return;
    if (loading) {
        btn._origHTML = btn.innerHTML;
        btn.classList.add('as-btn-saving');
        btn.innerHTML = '<span class="as-btn-spinner"></span> Saving...';
    } else {
        btn.classList.remove('as-btn-saving');
        if (btn._origHTML) btn.innerHTML = btn._origHTML;
    }
}

function _asShowModal(title, bodyHtml, onConfirm) {
    var overlay = document.getElementById('asModalOverlay');
    var titleEl = document.getElementById('asModalTitle');
    var bodyEl = document.getElementById('asModalBody');
    var confirmBtn = document.getElementById('asModalConfirm');
    if (!overlay) return;
    if (titleEl) titleEl.textContent = title;
    if (bodyEl) bodyEl.innerHTML = bodyHtml;
    if (confirmBtn) confirmBtn.onclick = onConfirm;
    overlay.style.display = '';
}

function _asCloseModal() {
    var overlay = document.getElementById('asModalOverlay');
    if (overlay) overlay.style.display = 'none';
}

/* ============================================================
   TIMEZONE HELPERS
   ============================================================ */

/** Get currently selected timezone (localStorage -> browser default) */
var _asTimezoneAliases = {
    'Asia/Calcutta': 'Asia/Kolkata'
};

function _asNormalizeTz(tz) {
    var raw = (tz || '').trim();
    if (!raw) return 'UTC';
    return _asTimezoneAliases[raw] || raw;
}

function _asResolveDropdownTz(tz, selectEl) {
    var normalized = _asNormalizeTz(tz);
    if (!selectEl) return normalized;

    var hasOption = Array.from(selectEl.options).some(function (o) {
        return o.value === normalized;
    });
    if (hasOption) return normalized;

    var browserTz = _asNormalizeTz(Intl.DateTimeFormat().resolvedOptions().timeZone || 'UTC');
    var hasBrowserOption = Array.from(selectEl.options).some(function (o) {
        return o.value === browserTz;
    });
    if (hasBrowserOption) return browserTz;

    return 'UTC';
}

function _asGetTz() {
    return _asNormalizeTz(localStorage.getItem('as_timezone') || Intl.DateTimeFormat().resolvedOptions().timeZone || 'UTC');
}

/** Format date in selected timezone: "Mar 19, 2026, 5:30 PM" */
function _asFormatDate(iso) {
    if (!iso) return '-';
    try {
        return new Intl.DateTimeFormat('en-US', {
            timeZone: _asGetTz(),
            month: 'short', day: 'numeric', year: 'numeric',
            hour: 'numeric', minute: '2-digit', hour12: true
        }).format(new Date(iso));
    } catch (e) {
        return new Date(iso).toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' });
    }
}

/** Time-ago string + exact time in parens using timezone */
function _asTimeAgo(iso) {
    if (!iso) return '-';
    var diff = Date.now() - new Date(iso).getTime();
    var s = Math.floor(diff / 1000);
    var rel;
    if (s < 60) rel = 'just now';
    else {
        var m = Math.floor(s / 60);
        if (m < 60) rel = m + 'm ago';
        else {
            var h = Math.floor(m / 60);
            if (h < 24) rel = h + 'h ago';
            else {
                var d = Math.floor(h / 24);
                rel = d < 30 ? d + 'd ago' : null;
            }
        }
    }
    var exact = _asFormatDate(iso);
    return rel ? rel + ' (' + exact + ')' : exact;
}

/** Update the timezone hint text below the dropdown */
function _asUpdateTzHint(tz) {
    var hint = document.getElementById('asTzHint');
    if (!hint) return;
    var safeTz = _asNormalizeTz(tz);
    try {
        var now = new Intl.DateTimeFormat('en-US', {
            timeZone: safeTz,
            month: 'short', day: 'numeric', year: 'numeric',
            hour: 'numeric', minute: '2-digit', hour12: true,
            timeZoneName: 'short'
        }).format(new Date());
        hint.textContent = 'Current time in this timezone: ' + now;
    } catch (e) {
        hint.textContent = 'Invalid timezone';
    }
}


