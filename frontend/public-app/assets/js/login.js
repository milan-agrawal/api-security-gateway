// Handle back/forward navigation (bfcache)
window.addEventListener('pageshow', function(event) {
    // Only check on bfcache navigations (back/forward button)
    if (!event.persisted) return;
    
    const token = localStorage.getItem('token');
    const loggedOut = sessionStorage.getItem('loggedOut');
    
    // If logged out or no token, stay on login page
    if (loggedOut === 'true' || !token) {
        return;
    }
    
    // If still logged in, redirect back to appropriate dashboard
    const userRole = localStorage.getItem('userRole');
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

const loginForm = document.getElementById('loginForm');
const emailInput = document.getElementById('email');
const passwordInput = document.getElementById('password');
const alertBox = document.getElementById('alert');
const submitButton = loginForm.querySelector('button[type="submit"]');
const togglePasswordBtn = document.getElementById('togglePassword');
const eyeIcon = document.getElementById('eyeIcon');
const eyeOffIcon = document.getElementById('eyeOffIcon');
const skeletonLoader = document.getElementById('skeletonLoader');
const loginCard = document.querySelector('.login-card');
const capsLockWarning = document.getElementById('capsLockWarning');

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
    setTimeout(() => {
        alertBox.classList.remove('show');
    }, 5000);
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
        // Call Auth API login endpoint
        const response = await fetch('http://localhost:8001/auth/login', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify({
                email: email,
                password: password
            })
        });

        const data = await response.json();
        
        console.log('Login response:', response.ok, data);

        if (response.ok) {
            // Clear any old login data first
            localStorage.clear();
            
            // Clear logout flag when logging in
            sessionStorage.removeItem('loggedOut');
            
            // Store authentication data
            localStorage.setItem('token', data.token);
            localStorage.setItem('userEmail', data.email);
            localStorage.setItem('userRole', data.role);
            localStorage.setItem('fullName', data.full_name);
            
            console.log('Stored in localStorage:', {
                token: data.token,
                email: data.email,
                role: data.role,
                full_name: data.full_name
            });

            // Show success message
            showAlert('Login successful! Redirecting...', 'success');

            // Redirect based on user role with auth data in URL
            setTimeout(() => {
                console.log('Redirecting to:', data.role === 'admin' ? 'admin panel' : 'user panel');
                const params = new URLSearchParams({
                    token: data.token,
                    email: data.email,
                    role: data.role,
                    fullName: data.full_name
                });
                
                if (data.role === 'admin') {
                    window.location.href = `http://localhost:3002/index.html?${params.toString()}`;
                } else {
                    window.location.href = `http://localhost:3001/index.html?${params.toString()}`;
                }
            }, 1000);
        } else {
            // Show error message from server
            loginCard.classList.remove('loading');
            skeletonLoader.classList.remove('active');
            showAlert(data.detail || 'Invalid credentials');
            triggerShake();
            submitButton.disabled = false;
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

// Auto-fill for development (remove in production)
if (window.location.hostname === 'localhost') {
    console.log('Development mode - Form validation active');
}
