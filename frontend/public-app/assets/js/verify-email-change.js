(function () {
  const API_URL = 'http://localhost:8001';
  const params = new URLSearchParams(window.location.search);
  const token = params.get('token');
  const alertEl = document.getElementById('alert');
  const intro = document.getElementById('intro');
  const verifyBtn = document.getElementById('verifyBtn');

  function showAlert(text, ok) {
    alertEl.style.display = 'block';
    alertEl.textContent = text;
    alertEl.className = 'alert ' + (ok ? 'success' : 'error');
  }

  if (!token) {
    intro.textContent = 'Invalid or missing verification token. Please request a new email change.';
    intro.style.color = '#EF4444';
    verifyBtn.disabled = true;
  }

  verifyBtn.addEventListener('click', async function () {
    if (!token) return;

    alertEl.style.display = 'none';
    verifyBtn.disabled = true;
    verifyBtn.textContent = 'Verifying...';

    try {
      const res = await fetch(`${API_URL}/user/verify-email-change`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ token: token })
      });
      const data = await res.json();

      if (res.ok) {
        showAlert(data.message || 'Email verified successfully. Redirecting to login...', true);
        setTimeout(() => {
          window.location.href = 'login.html';
        }, 2200);
        return;
      }

      showAlert(data.detail || 'Verification failed.', false);
    } catch (err) {
      showAlert('Unable to contact server. Try again later.', false);
    }

    verifyBtn.disabled = false;
    verifyBtn.textContent = 'Verify Email Address';
  });
})();
