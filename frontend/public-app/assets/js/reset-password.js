(function(){
  const API_URL = 'http://localhost:8001';
  const params = new URLSearchParams(window.location.search);
  const token = params.get('token');
  const form = document.getElementById('resetForm');
  const newPwd = document.getElementById('newPassword');
  const confPwd = document.getElementById('confirmPassword');
  const alertEl = document.getElementById('alert');
  const intro = document.getElementById('intro');
  const submitBtn = document.getElementById('submitBtn');

  // No token — hide form and show error
  if (!token) {
    intro.textContent = 'Invalid or missing reset token. Please request a new link.';
    intro.style.color = '#EF4444';
    form.style.display = 'none';
  }

  // Password toggle buttons
  document.getElementById('toggleNew').addEventListener('click', () => {
    newPwd.type = newPwd.type === 'password' ? 'text' : 'password';
  });
  document.getElementById('toggleConfirm').addEventListener('click', () => {
    confPwd.type = confPwd.type === 'password' ? 'text' : 'password';
  });

  function showAlert(text, ok=true){
    alertEl.style.display = 'block';
    alertEl.textContent = text;
    alertEl.className = 'alert ' + (ok ? 'success' : 'error');
  }

  function validatePasswordStrength(pwd){
    const errs = [];
    if (pwd.length < 8) errs.push('at least 8 characters');
    if (!/[A-Z]/.test(pwd)) errs.push('an uppercase letter');
    if (!/[a-z]/.test(pwd)) errs.push('a lowercase letter');
    if (!/\d/.test(pwd)) errs.push('a digit');
    if (!/[!@#$%^&*(),.?":{}|<>]/.test(pwd)) errs.push('a special character');
    return errs;
  }

  form.addEventListener('submit', async (e) => {
    e.preventDefault();
    alertEl.style.display = 'none';
    const pwd = newPwd.value;
    const cp = confPwd.value;
    const pwdErrs = validatePasswordStrength(pwd);
    if (pwdErrs.length) return showAlert('Password must contain: ' + pwdErrs.join(', ') + '.', false);
    if (pwd !== cp) return showAlert('Passwords do not match.', false);

    submitBtn.disabled = true;
    submitBtn.textContent = 'Resetting...';

    try {
      const res = await fetch(`${API_URL}/auth/reset-password`, {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({ token: token, new_password: pwd })
      });
      const data = await res.json();
      if (res.ok) {
        showAlert('Password reset successful! Redirecting to login...', true);
        setTimeout(() => window.location.href = 'login.html', 2000);
      } else {
        showAlert(data.detail || 'Invalid or expired token.', false);
        submitBtn.disabled = false;
        submitBtn.textContent = 'Set New Password';
      }
    } catch(err) {
      showAlert('Unable to contact server. Try again later.', false);
      submitBtn.disabled = false;
      submitBtn.textContent = 'Set New Password';
    }
  });
})();
