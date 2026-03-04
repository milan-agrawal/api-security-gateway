(function(){
  const API_URL = 'http://localhost:8001';
  const form = document.getElementById('forgotForm');
  const emailEl = document.getElementById('email');
  const alert = document.getElementById('alert');
  const submitBtn = document.getElementById('submitBtn');

  function showAlert(text, ok=true){
    alert.style.display = 'block';
    alert.textContent = text;
    alert.className = 'alert ' + (ok ? 'success' : 'error');
  }

  form.addEventListener('submit', async (e)=>{
    e.preventDefault();
    alert.style.display = 'none';
    const email = emailEl.value.trim();
    if (!email) return showAlert('Please enter your email address.', false);

    submitBtn.disabled = true;
    submitBtn.textContent = 'Sending...';

    try{
      const res = await fetch(`${API_URL}/auth/forgot-password`, {
        method: 'POST',
        headers: {'Content-Type':'application/json'},
        body: JSON.stringify({email})
      });
      if (res.status === 429){
        const data = await res.json();
        return showAlert(data.detail || 'Too many requests. Please wait and try again.', false);
      }
      // Always show generic success message (no enumeration)
      showAlert('If that email exists, you will receive a reset link shortly.', true);
      form.reset();
    }catch(err){
      showAlert('Unable to contact server. Try again later.', false);
    } finally {
      submitBtn.disabled = false;
      submitBtn.textContent = 'Send Reset Link';
    }
  });
})();
