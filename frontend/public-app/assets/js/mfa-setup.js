// ============================================================
// MFA Setup Page – JavaScript
// ============================================================

const API_URL = 'http://localhost:8001';

// URL params
const urlParams = new URLSearchParams(window.location.search);
const urlTempToken = urlParams.get('token');
const urlUserEmail = urlParams.get('email');
if (urlTempToken) {
    sessionStorage.setItem('mfaTempToken', urlTempToken);
}
if (urlUserEmail) {
    sessionStorage.setItem('mfaEmail', urlUserEmail);
}
if (urlTempToken || urlUserEmail) {
    window.history.replaceState({}, document.title, 'mfa-setup.html');
}
const tempToken = sessionStorage.getItem('mfaTempToken');
const userEmail = sessionStorage.getItem('mfaEmail');

// DOM refs
const qrCodeContainer = document.getElementById('qrCode');
const secretCodeEl     = document.getElementById('secretCode');
const verifyCodeHidden = document.getElementById('verifyCode');
const completeBtn      = document.getElementById('completeSetup');
const backupSection    = document.getElementById('backupCodesSection');
const backupGrid       = document.getElementById('backupCodesGrid');
const continueBtn      = document.getElementById('continueBtn');
const alertBox         = document.getElementById('alert');
const otpDigits        = document.querySelectorAll('.otp-digit');
const successBadge     = document.getElementById('successBadge');
const qrPanel          = document.getElementById('qrPanel');
const verifyPanel      = document.getElementById('verifyPanel');

// Step cards
const stepCard1 = document.getElementById('stepCard1');
const stepCard2 = document.getElementById('stepCard2');
const stepCard3 = document.getElementById('stepCard3');

// State
let mfaSecret    = null;
let backupCodes  = [];
let setupDone    = false;
let finalAuthData = null;
let verifySetupInProgress = false;

// ── Guard ───────────────────────────────────────────────────
if (!tempToken || !userEmail) {
    showAlert('Invalid setup link. Please login again.', 'error');
    setTimeout(() => { window.location.href = 'login.html'; }, 2000);
}

// ── Alert ───────────────────────────────────────────────────
function showAlert(message, type = 'error') {
    alertBox.textContent = message;
    alertBox.className = `alert ${type} show`;
    setTimeout(() => { alertBox.classList.remove('show'); }, 5000);
}

// ── OTP individual-digit inputs ─────────────────────────────
otpDigits.forEach((input, idx) => {
    input.addEventListener('input', (e) => {
        const val = e.target.value.replace(/\D/g, '');
        e.target.value = val.slice(0, 1);
        if (val && idx < otpDigits.length - 1) {
            otpDigits[idx + 1].focus();
        }
        if (val) e.target.classList.add('filled');
        else e.target.classList.remove('filled');
        syncHiddenOTP();
    });

    input.addEventListener('keydown', (e) => {
        if (e.key === 'Backspace' && !input.value && idx > 0) {
            otpDigits[idx - 1].focus();
            otpDigits[idx - 1].value = '';
            otpDigits[idx - 1].classList.remove('filled');
            syncHiddenOTP();
        }
        if (e.key === 'Enter') {
            const code = getOTPValue();
            if (code.length === 6) verifyAndComplete();
        }
    });

    // Handle paste anywhere in the digit row
    input.addEventListener('paste', (e) => {
        e.preventDefault();
        const paste = (e.clipboardData || window.clipboardData).getData('text').replace(/\D/g, '').slice(0, 6);
        paste.split('').forEach((ch, i) => {
            if (otpDigits[i]) {
                otpDigits[i].value = ch;
                otpDigits[i].classList.add('filled');
            }
        });
        if (paste.length > 0) otpDigits[Math.min(paste.length, 5)].focus();
        syncHiddenOTP();
    });
});

function syncHiddenOTP() {
    const code = getOTPValue();
    verifyCodeHidden.value = code;
    completeBtn.disabled = code.length !== 6;
}

function getOTPValue() {
    return Array.from(otpDigits).map(d => d.value).join('');
}

// ── Step highlighting ───────────────────────────────────────
function activateStep(n) {
    [stepCard1, stepCard2, stepCard3].forEach(s => s.classList.remove('active'));
    if (n >= 1) stepCard1.classList.add('active');
    if (n >= 2) stepCard2.classList.add('active');
    if (n >= 3) stepCard3.classList.add('active');
}

// ── Init MFA setup (fetch QR) ───────────────────────────────
async function initMFASetup() {
    try {
        const res = await fetch(`${API_URL}/auth/mfa/setup`, {
            method: 'POST',
            credentials: 'include',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ temp_token: tempToken })
        });

        const data = await res.json();
        if (res.ok) {
            // QR code — backend now returns full data URI
            qrCodeContainer.classList.remove('loading');
            qrCodeContainer.innerHTML = `<img src="${data.qr_code}" alt="QR Code">`;

            // Secret
            mfaSecret = data.secret;
            secretCodeEl.textContent = formatSecret(data.secret);

            // Enable input
            otpDigits.forEach(d => d.disabled = false);
            otpDigits[0].focus();

            activateStep(2);
        } else {
            showAlert(data.detail || 'Failed to initialise MFA setup');
            qrCodeContainer.classList.remove('loading');
            qrCodeContainer.innerHTML = '<p style="color:#F87171;font-size:13px;">Failed to load QR code</p>';
        }
    } catch (err) {
        console.error('MFA setup error:', err);
        showAlert('Unable to connect to server. Please try again.');
        qrCodeContainer.classList.remove('loading');
        qrCodeContainer.innerHTML = '<p style="color:#F87171;font-size:13px;">Connection error</p>';
    }
}

// ── Helpers ─────────────────────────────────────────────────
function formatSecret(s) {
    return s.match(/.{1,4}/g)?.join(' ') || s;
}

async function copySecret() {
    if (!mfaSecret) return;
    try {
        await navigator.clipboard.writeText(mfaSecret);
        secretCodeEl.classList.add('copied');
        secretCodeEl.textContent = 'Copied!';
        setTimeout(() => {
            secretCodeEl.classList.remove('copied');
            secretCodeEl.textContent = formatSecret(mfaSecret);
        }, 2000);
    } catch (_) {}
}

// ── Verify & Complete ───────────────────────────────────────
async function verifyAndComplete() {
    if (verifySetupInProgress) return;
    const otpCode = getOTPValue();
    if (otpCode.length !== 6 || !/^\d{6}$/.test(otpCode)) {
        showAlert('Please enter a valid 6-digit code');
        return;
    }

    verifySetupInProgress = true;
    completeBtn.disabled = true;
    completeBtn.classList.add('loading');
    otpDigits.forEach(d => { d.disabled = true; });

    try {
        const res = await fetch(`${API_URL}/auth/mfa/verify-setup`, {
            method: 'POST',
            credentials: 'include',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ temp_token: tempToken, otp_code: otpCode })
        });

        const data = await res.json();
        if (res.ok) {
            setupDone = true;
            finalAuthData = data;
            sessionStorage.removeItem('mfaTempToken');
            sessionStorage.removeItem('mfaEmail');

            // Persist auth
            localStorage.clear();
            sessionStorage.removeItem('loggedOut');
            localStorage.setItem('userEmail', data.email);
            localStorage.setItem('userRole', data.role);
            localStorage.setItem('fullName', data.full_name);

            activateStep(3);

            // Hide QR & verify panels, show success
            qrPanel.style.display = 'none';
            verifyPanel.style.display = 'none';
            successBadge.classList.add('show');

            // Show backup codes
            if (data.backup_codes && data.backup_codes.length) {
                backupCodes = data.backup_codes;
                displayBackupCodes(data.backup_codes);
            }

            // Show continue
            continueBtn.classList.add('show');

            showAlert('Two-factor authentication enabled!', 'success');
        } else {
            showAlert(data.detail || 'Invalid code. Please try again.');
            resetVerifyBtn();
            clearOTP();
        }
    } catch (err) {
        console.error('Verify error:', err);
        showAlert('Unable to verify code. Please try again.');
        resetVerifyBtn();
    }
}

function resetVerifyBtn() {
    verifySetupInProgress = false;
    completeBtn.disabled = false;
    completeBtn.classList.remove('loading');
    otpDigits.forEach(d => { d.disabled = false; });
}

function clearOTP() {
    otpDigits.forEach(d => { d.value = ''; d.classList.remove('filled'); });
    verifyCodeHidden.value = '';
    otpDigits[0].focus();
}

// ── Backup codes ────────────────────────────────────────────
function displayBackupCodes(codes) {
    backupSection.classList.add('show');
    backupGrid.innerHTML = codes.map(c => `<div class="backup-code">${c}</div>`).join('');
}

function downloadBackupCodes() {
    if (!backupCodes.length) return;
    const txt = `API Security Gateway - Backup Codes\n${'='.repeat(40)}\nEmail: ${userEmail}\nGenerated: ${new Date().toISOString()}\n\nKeep these codes safe. Each code can only be used once.\n\n${backupCodes.map((c, i) => `${i + 1}. ${c}`).join('\n')}\n\n${'='.repeat(40)}\nStore these codes securely offline.\n`;
    const blob = new Blob([txt], { type: 'text/plain' });
    const a = document.createElement('a');
    a.href = URL.createObjectURL(blob);
    a.download = 'api-security-gateway-backup-codes.txt';
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    showAlert('Backup codes downloaded!', 'success');
}

async function copyBackupCodes() {
    if (!backupCodes.length) return;
    try {
        await navigator.clipboard.writeText(backupCodes.join('\n'));
        showAlert('Backup codes copied!', 'success');
    } catch (_) {
        showAlert('Failed to copy codes');
    }
}

// ── Continue ────────────────────────────────────────────────
async function continueToDashboard() {
    if (!finalAuthData) return;
    const response = await fetch('http://localhost:8001/auth/panel-handoff', {
        method: 'POST',
        credentials: 'include',
        headers: {
            'Content-Type': 'application/json'
        },
        body: JSON.stringify({
            target_panel: finalAuthData.role === 'admin' ? 'admin' : 'user'
        })
    });
    const handoff = await response.json().catch(() => ({}));
    if (!response.ok || !handoff.handoff_code) {
        showAlert((handoff && handoff.detail) || 'Failed to open dashboard securely.');
        return;
    }

    if (finalAuthData.role === 'admin') {
        window.location.href = `http://localhost:3002/index.html?handoff=${encodeURIComponent(handoff.handoff_code)}`;
    } else {
        window.location.href = `http://localhost:3001/index.html?handoff=${encodeURIComponent(handoff.handoff_code)}`;
    }
}

// ── Event listeners ─────────────────────────────────────────
completeBtn.addEventListener('click', verifyAndComplete);
continueBtn.addEventListener('click', continueToDashboard);

// Global for inline onclick
window.copySecret          = copySecret;
window.downloadBackupCodes = downloadBackupCodes;
window.copyBackupCodes     = copyBackupCodes;

// ── Boot ────────────────────────────────────────────────────
document.addEventListener('DOMContentLoaded', () => {
    if (tempToken && userEmail) initMFASetup();
});
