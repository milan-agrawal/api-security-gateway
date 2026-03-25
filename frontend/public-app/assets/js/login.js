// Handle back/forward navigation (bfcache)
window.addEventListener('pageshow', function(event) {
    // Only check on bfcache navigations (back/forward button)
    if (!event.persisted) return;
    
    const loggedOut = sessionStorage.getItem('loggedOut');
    const userRole = localStorage.getItem('userRole');
    
    // If logged out or no remembered role, stay on login page
    if (loggedOut === 'true' || !userRole) {
        return;
    }
    
    // If still logged in, redirect back to appropriate dashboard
    if (userRole === 'admin') {
        window.location.replace('http://localhost:3002/index.html');
    } else {
        window.location.replace('http://localhost:3001/index.html');
    }
});

// Clear localStorage if returning after logout (via URL parameter)
const urlParams = new URLSearchParams(window.location.search);
if (urlParams.get('logout') === 'true') {
    localStorage.clear();
    // Clean URL by removing the logout parameter
    window.history.replaceState({}, document.title, '/login.html');
}

// Prevent a stale stored token from bypassing MFA when visiting the login page.
// If the caller explicitly wants to keep an existing token, they can pass
// `?keepToken=true` in the URL.
if (!urlParams.get('keepToken')) {
    localStorage.removeItem('token');
}

const loginForm = document.getElementById('loginForm');
const otpForm = document.getElementById('otpForm');
const emailInput = document.getElementById('email');
const passwordInput = document.getElementById('password');
const otpInput = document.getElementById('otpCode');
const alertBox = document.getElementById('alert');
const submitButton = loginForm.querySelector('button[type="submit"]');
const togglePasswordBtn = document.getElementById('togglePassword');
const eyeIcon = document.getElementById('eyeIcon');
const eyeOffIcon = document.getElementById('eyeOffIcon');
const skeletonLoader = document.getElementById('skeletonLoader');
const loginCard = document.querySelector('.login-card');
const capsLockWarning = document.getElementById('capsLockWarning');

// MFA state
let mfaTempToken = null;
let mfaEmail = null;

// Password visibility toggle
togglePasswordBtn.addEventListener('click', () => {
    const type = passwordInput.getAttribute('type') === 'password' ? 'text' : 'password';
    passwordInput.setAttribute('type', type);
    
    // Toggle eye icons
    if (type === 'text') {
        eyeIcon.style.display = 'none';
        eyeOffIcon.style.display = 'block';
    } else {
        eyeIcon.style.display = 'block';
        eyeOffIcon.style.display = 'none';
    }
});

// Caps Lock Detection
passwordInput.addEventListener('keyup', (e) => {
    if (e.getModifierState && e.getModifierState('CapsLock')) {
        capsLockWarning.classList.add('show');
        passwordInput.classList.add('has-caps-warning');
    } else {
        capsLockWarning.classList.remove('show');
        passwordInput.classList.remove('has-caps-warning');
    }
});

// Clear error states on input
[emailInput, passwordInput].forEach(input => {
    input.addEventListener('input', () => {
        input.parentElement.parentElement.classList.remove('error');
    });
});

// Show alert message
function showAlert(message, type = 'error') {
    alertBox.textContent = message;
    alertBox.className = `alert ${type} show`;
    const duration = (type === 'warning' || message.includes('locked')) ? 10000 : 5000;
    setTimeout(() => {
        alertBox.classList.remove('show');
    }, duration);
}

async function clearExistingServerSession() {
    try {
        await fetch('http://localhost:8001/auth/logout?panel=public', {
            method: 'POST',
            credentials: 'include'
        });
    } catch (_) {
        // Ignore cleanup failures here. Fresh login should still proceed.
    }
}

// Shake animation trigger
function triggerShake() {
    loginCard.classList.add('shake');
    setTimeout(() => {
        loginCard.classList.remove('shake');
    }, 500);
}

// Validate email
function isValidEmail(email) {
    const re = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
    return re.test(email);
}

// Handle form submission
loginForm.addEventListener('submit', async (e) => {
    e.preventDefault();

    // Clear previous errors
    document.querySelectorAll('.form-group').forEach(group => {
        group.classList.remove('error');
    });

    const email = emailInput.value.trim();
    const password = passwordInput.value;

    // Client-side validation
    let hasError = false;

    if (!email || !isValidEmail(email)) {
        emailInput.parentElement.parentElement.classList.add('error');
        hasError = true;
    }

    if (!password) {
        passwordInput.parentElement.parentElement.classList.add('error');
        hasError = true;
    }

    if (hasError) {
        showAlert('Please fix the errors above');
        triggerShake();
        return;
    }

    // Show loading state with skeleton
    submitButton.disabled = true;
    loginCard.classList.add('loading');
    skeletonLoader.classList.add('active');

    try {
        // Clear any stale authenticated cookie before starting a fresh login.
        // This prevents cross-account MFA handoff from reusing an old admin session.
        await clearExistingServerSession();

        // Call Auth API login endpoint
        const response = await fetch('http://localhost:8001/auth/login', {
            method: 'POST',
            credentials: 'include',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify({
                email: email,
                password: password
            })
        });

        let data;
        try {
            data = await response.json();
        } catch (parseErr) {
            throw new Error('Server returned an invalid response');
        }
        
        if (response.ok) {
            // Check if MFA is required
            if (data.mfa_required) {
                // Store temp token and email for MFA verification
                mfaTempToken = data.temp_token;
                mfaEmail = email;
                
                // Hide loading
                loginCard.classList.remove('loading');
                skeletonLoader.classList.remove('active');
                submitButton.disabled = false;
                
                // Check if MFA setup is needed
                if (data.mfa_setup_required) {
                    // Redirect to MFA setup page
                    showAlert('MFA setup required. Redirecting...', 'success');
                    sessionStorage.setItem('mfaTempToken', mfaTempToken || '');
                    sessionStorage.setItem('mfaEmail', mfaEmail || '');
                    setTimeout(() => {
                        window.location.href = 'mfa-setup.html';
                    }, 1000);
                } else {
                    // Show OTP form
                    showOTPForm();
                }
                return;
            }
            
            // No MFA required - proceed with login
            // Clear any old login data first
            localStorage.clear();
            
            // Clear logout flag when logging in
            sessionStorage.removeItem('loggedOut');
            
            // Store authentication data
            localStorage.setItem('userEmail', data.email);
            localStorage.setItem('userRole', data.role);
            localStorage.setItem('fullName', data.full_name);

            // Show success message
            showAlert('Login successful! Redirecting...', 'success');

            // Redirect based on user role using one-time handoff code
            setTimeout(() => {
                redirectToPanel(data).catch((error) => {
                    console.error('Panel redirect error:', error);
                    showAlert(error.message || 'Unable to open dashboard securely.');
                    loginCard.classList.remove('loading');
                    skeletonLoader.classList.remove('active');
                    submitButton.disabled = false;
                });
            }, 1000);
        } else {
            // Show error message from server
            loginCard.classList.remove('loading');
            skeletonLoader.classList.remove('active');
            const msg = data.detail || 'Invalid credentials';
            if (response.status === 429) {
                showAlert(msg, 'error');
                // Disable form for visual feedback during lockout
                submitButton.disabled = true;
                submitButton.textContent = 'Account Locked';
                setTimeout(() => {
                    submitButton.disabled = false;
                    submitButton.textContent = 'Sign In';
                }, 30000);
            } else {
                if (msg.includes('Warning:')) {
                    showAlert(msg, 'warning');
                } else {
                    showAlert(msg);
                }
                submitButton.disabled = false;
            }
            triggerShake();
        }
    } catch (error) {
        console.error('Login error:', error);
        loginCard.classList.remove('loading');
        skeletonLoader.classList.remove('active');
        showAlert('Unable to connect to server. Please try again.');
        triggerShake();
        submitButton.disabled = false;
    }
});

// Show OTP form
function showOTPForm() {
    loginForm.style.display = 'none';
    otpForm.style.display = 'block';
    // Hide divider and signup
    document.querySelector('.divider').style.display = 'none';
    document.querySelector('.signup-link').style.display = 'none';
    // Focus on OTP input
    setTimeout(() => otpInput.focus(), 100);
}

// Hide OTP form
function hideOTPForm() {
    otpForm.style.display = 'none';
    loginForm.style.display = 'block';
    document.querySelector('.divider').style.display = 'block';
    document.querySelector('.signup-link').style.display = 'block';
    mfaTempToken = null;
    mfaEmail = null;
    otpInput.value = '';
}

// Redirect to appropriate panel
async function redirectToPanel(data) {
    const response = await fetch('http://localhost:8001/auth/panel-handoff', {
        method: 'POST',
        credentials: 'include',
        headers: {
            'Content-Type': 'application/json'
        },
        body: JSON.stringify({
            target_panel: data.role === 'admin' ? 'admin' : 'user'
        })
    });

    const handoff = await response.json().catch(() => ({}));
    if (!response.ok || !handoff.handoff_code) {
        throw new Error((handoff && handoff.detail) || 'Failed to open panel securely.');
    }

    const targetUrl = data.role === 'admin'
        ? `http://localhost:3002/index.html?handoff=${encodeURIComponent(handoff.handoff_code)}`
        : `http://localhost:3001/index.html?handoff=${encodeURIComponent(handoff.handoff_code)}`;
    window.location.href = targetUrl;
}

// OTP Form submission
otpForm.addEventListener('submit', async (e) => {
    e.preventDefault();
    
    const otpCode = otpInput.value.trim();
    
    if (!otpCode || otpCode.length !== 6 || !/^\d{6}$/.test(otpCode)) {
        showAlert('Please enter a valid 6-digit code');
        triggerShake();
        return;
    }
    
    const otpSubmitBtn = otpForm.querySelector('button[type="submit"]');
    otpSubmitBtn.disabled = true;
    otpSubmitBtn.textContent = 'Verifying...';
    
    try {
        const response = await fetch('http://localhost:8001/auth/mfa/verify', {
            method: 'POST',
            credentials: 'include',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify({
                temp_token: mfaTempToken,
                otp_code: otpCode
            })
        });
        
        const data = await response.json();
        
        if (response.ok) {
            // Clear any old login data first
            localStorage.clear();
            sessionStorage.removeItem('loggedOut');
            
            // Store authentication data
            localStorage.setItem('userEmail', data.email);
            localStorage.setItem('userRole', data.role);
            localStorage.setItem('fullName', data.full_name);
            
            showAlert('Verification successful! Redirecting...', 'success');
            
            setTimeout(() => {
                redirectToPanel(data).catch((error) => {
                    console.error('Panel redirect error:', error);
                    showAlert(error.message || 'Unable to open dashboard securely.');
                });
            }, 1000);
        } else {
            showAlert(data.detail || 'Invalid code. Please try again.');
            triggerShake();
            otpSubmitBtn.disabled = false;
            otpSubmitBtn.textContent = 'Verify Code';
            otpInput.value = '';
            otpInput.focus();
        }
    } catch (error) {
        console.error('MFA verify error:', error);
        showAlert('Unable to verify code. Please try again.');
        triggerShake();
        otpSubmitBtn.disabled = false;
        otpSubmitBtn.textContent = 'Verify Code';
    }
});

// Back to login button
document.getElementById('backToLogin')?.addEventListener('click', () => {
    hideOTPForm();
});

// Use backup code button (placeholder for now)
document.getElementById('useBackupCode')?.addEventListener('click', () => {
    showAlert('Backup code feature coming soon', 'info');
});

// Auto-format OTP input (numbers only, auto-submit when 6 digits)
otpInput?.addEventListener('input', (e) => {
    // Remove non-numeric characters
    e.target.value = e.target.value.replace(/\D/g, '').slice(0, 6);
});


