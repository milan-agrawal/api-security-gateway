"""
Utility functions for password generation and email sending
"""
import string
import secrets
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import os
from typing import Optional
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Optional encryption for secrets at rest (Fernet)
try:
    from cryptography.fernet import Fernet, InvalidToken
except Exception:
    Fernet = None
    InvalidToken = Exception


def generate_secure_password(length: int = 12) -> str:
    """
    Generate a secure random password with:
    - Uppercase letters
    - Lowercase letters
    - Digits
    - Special characters
    
    Args:
        length: Password length (default 12)
    
    Returns:
        str: Generated secure password
    """
    # Define character sets
    uppercase = string.ascii_uppercase
    lowercase = string.ascii_lowercase
    digits = string.digits
    special = "!@#$%^&*"
    
    # Ensure at least one character from each set
    password = [
        secrets.choice(uppercase),
        secrets.choice(lowercase),
        secrets.choice(digits),
        secrets.choice(special)
    ]
    
    # Fill the rest with random characters from all sets
    all_chars = uppercase + lowercase + digits + special
    password += [secrets.choice(all_chars) for _ in range(length - 4)]
    
    # Shuffle to avoid predictable patterns
    secrets.SystemRandom().shuffle(password)
    
    return ''.join(password)


def _get_fernet() -> Optional[object]:
    """
    Return a Fernet instance if `ENCRYPTION_KEY` is configured and
    the cryptography library is available. Otherwise return None.
    """
    key = os.getenv('ENCRYPTION_KEY')
    if not key or Fernet is None:
        return None
    try:
        return Fernet(key)
    except Exception:
        return None


def encrypt_secret(plain: str) -> str:
    """Encrypt `plain` with Fernet if configured, otherwise return plain."""
    f = _get_fernet()
    if not f:
        return plain
    token = f.encrypt(plain.encode())
    return token.decode()


def decrypt_secret(token: str) -> str:
    """Decrypt a Fernet token if possible, otherwise return the original string.

    If decryption fails, assumes the value was stored plaintext and returns it.
    """
    f = _get_fernet()
    if not f:
        return token
    try:
        return f.decrypt(token.encode()).decode()
    except InvalidToken:
        return token
    except Exception:
        return token


def send_credentials_email(
    recipient_email: str,
    full_name: str,
    password: str,
    role: str,
    mfa_enabled: bool = False
) -> bool:
    """
    Send credentials to new user via Gmail SMTP
    
    Args:
        recipient_email: User's email address
        full_name: User's full name
        password: Generated password
        role: User role (user/admin)
        mfa_enabled: Whether MFA/2FA is enabled for this account
    
    Returns:
        bool: True if email sent successfully, False otherwise
    """
    # Get SMTP configuration from environment
    smtp_host = os.getenv("SMTP_HOST", "smtp.gmail.com")
    smtp_port = int(os.getenv("SMTP_PORT", "587"))
    smtp_user = os.getenv("SMTP_USER")
    smtp_password = os.getenv("SMTP_PASSWORD")
    from_email = os.getenv("FROM_EMAIL", smtp_user)
    
    if not smtp_user or not smtp_password:
        print("ERROR: SMTP credentials not configured in .env file")
        print(f"WARNING: Failed to send credentials email to {recipient_email}")
        print(f"Please configure SMTP settings in .env file")
        # ⚠️ SECURITY: Never log passwords
        return False
    
    try:
        # Create message
        msg = MIMEMultipart("alternative")
        msg["Subject"] = f"🔐 Your API Security Gateway Account - {role.title()} Access Credentials"
        msg["From"] = f"API Security Gateway <{from_email}>"
        msg["To"] = recipient_email
        
        # Email body (HTML)
        html_body = f"""
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <style>
        * {{
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }}
        body {{
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;
            background-color: #f5f5f7;
            line-height: 1.6;
            margin: 0;
            padding: 20px;
        }}
        .email-wrapper {{
            max-width: 640px;
            margin: 0 auto;
            background: #ffffff;
            border-radius: 12px;
            overflow: hidden;
            box-shadow: 0 8px 24px rgba(0, 0, 0, 0.08);
        }}
        .header {{
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            padding: 48px 40px;
            text-align: center;
            position: relative;
        }}
        .header::after {{
            content: '';
            position: absolute;
            bottom: 0;
            left: 0;
            right: 0;
            height: 4px;
            background: linear-gradient(90deg, #A855F7, #EC4899, #F59E0B);
        }}
        .logo-section {{
            margin-bottom: 16px;
        }}
        .logo-icon {{
            font-size: 48px;
            line-height: 1;
            filter: drop-shadow(0 4px 8px rgba(0,0,0,0.2));
        }}
        .header h1 {{
            color: #ffffff;
            font-size: 28px;
            font-weight: 600;
            margin-top: 16px;
            letter-spacing: -0.5px;
        }}
        .header p {{
            color: rgba(255, 255, 255, 0.95);
            font-size: 15px;
            margin-top: 8px;
        }}
        .content {{
            padding: 48px 40px;
            color: #333333;
        }}
        .greeting {{
            font-size: 20px;
            color: #1a1a1a;
            margin-bottom: 24px;
            font-weight: 500;
        }}
        .intro-text {{
            font-size: 15px;
            color: #4a4a4a;
            margin-bottom: 32px;
            line-height: 1.7;
        }}
        .role-badge {{
            display: inline-block;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            padding: 6px 16px;
            border-radius: 20px;
            font-size: 13px;
            font-weight: 600;
            text-transform: uppercase;
            letter-spacing: 0.5px;
            margin: 0 4px;
        }}
        .section {{
            margin: 32px 0;
        }}
        .section-title {{
            font-size: 16px;
            font-weight: 600;
            color: #1a1a1a;
            margin-bottom: 16px;
            display: flex;
            align-items: center;
        }}
        .section-title .icon {{
            margin-right: 8px;
            font-size: 20px;
        }}
        .credentials-box {{
            background: linear-gradient(135deg, #f8f9ff 0%, #f0f4ff 100%);
            border: 2px solid #e0e7ff;
            border-radius: 8px;
            padding: 28px;
            margin: 24px 0;
        }}
        .credential-row {{
            margin: 20px 0;
        }}
        .credential-row:first-child {{
            margin-top: 0;
        }}
        .credential-row:last-child {{
            margin-bottom: 0;
        }}
        .credential-label {{
            font-size: 13px;
            font-weight: 600;
            color: #667eea;
            text-transform: uppercase;
            letter-spacing: 0.5px;
            margin-bottom: 8px;
            display: flex;
            align-items: center;
        }}
        .credential-label .icon {{
            margin-right: 6px;
        }}
        .credential-value {{
            font-family: 'SF Mono', Monaco, 'Cascadia Code', 'Courier New', monospace;
            font-size: 16px;
            color: #1a1a1a;
            background: #ffffff;
            padding: 14px 18px;
            border-radius: 6px;
            border: 1px solid #d1d5db;
            display: inline-block;
            min-width: 280px;
            font-weight: 500;
            letter-spacing: 0.3px;
            box-shadow: 0 2px 4px rgba(0, 0, 0, 0.04);
        }}
        .info-box {{
            background: #ecfdf5;
            border-left: 4px solid #10b981;
            padding: 20px 24px;
            margin: 24px 0;
            border-radius: 0 8px 8px 0;
        }}
        .info-box .title {{
            font-weight: 600;
            color: #065f46;
            font-size: 15px;
            margin-bottom: 8px;
            display: flex;
            align-items: center;
        }}
        .info-box .title .icon {{
            margin-right: 8px;
            font-size: 18px;
        }}
        .info-box .text {{
            color: #047857;
            font-size: 14px;
            line-height: 1.6;
        }}
        .alert-box {{
            background: #fef3c7;
            border-left: 4px solid #f59e0b;
            padding: 20px 24px;
            margin: 24px 0;
            border-radius: 0 8px 8px 0;
        }}
        .alert-box .title {{
            font-weight: 600;
            color: #92400e;
            font-size: 15px;
            margin-bottom: 8px;
            display: flex;
            align-items: center;
        }}
        .alert-box .title .icon {{
            margin-right: 8px;
            font-size: 18px;
        }}
        .alert-box .text {{
            color: #b45309;
            font-size: 14px;
            line-height: 1.6;
        }}
        .alert-box ul {{
            margin: 12px 0 0 20px;
            padding: 0;
        }}
        .alert-box li {{
            color: #b45309;
            margin: 6px 0;
            font-size: 14px;
        }}
        .next-steps {{
            background: #f9fafb;
            border-radius: 8px;
            padding: 24px;
            margin: 24px 0;
        }}
        .next-steps .step {{
            display: flex;
            margin: 16px 0;
            align-items: flex-start;
        }}
        .next-steps .step-number {{
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            width: 28px;
            height: 28px;
            border-radius: 50%;
            display: flex;
            align-items: center;
            justify-content: center;
            font-weight: 600;
            font-size: 13px;
            flex-shrink: 0;
            margin-right: 12px;
        }}
        .next-steps .step-content {{
            flex: 1;
            padding-top: 2px;
        }}
        .next-steps .step-text {{
            color: #4a4a4a;
            font-size: 14px;
            line-height: 1.6;
        }}
        .login-button {{
            display: inline-block;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            padding: 14px 32px;
            border-radius: 8px;
            text-decoration: none;
            font-weight: 600;
            font-size: 15px;
            margin: 24px 0;
            transition: transform 0.2s, box-shadow 0.2s;
            box-shadow: 0 4px 12px rgba(102, 126, 234, 0.4);
        }}
        .login-button:hover {{
            transform: translateY(-2px);
            box-shadow: 0 6px 16px rgba(102, 126, 234, 0.5);
        }}
        .divider {{
            height: 1px;
            background: linear-gradient(90deg, transparent, #e5e7eb, transparent);
            margin: 32px 0;
        }}
        .support-section {{
            background: #f9fafb;
            border-radius: 8px;
            padding: 20px;
            text-align: center;
            margin: 24px 0;
        }}
        .support-section p {{
            color: #6b7280;
            font-size: 13px;
            margin: 4px 0;
        }}
        .footer {{
            background: #f9fafb;
            padding: 32px 40px;
            text-align: center;
            border-top: 1px solid #e5e7eb;
        }}
        .footer-logo {{
            font-size: 24px;
            margin-bottom: 12px;
        }}
        .footer p {{
            color: #9ca3af;
            font-size: 13px;
            margin: 8px 0;
            line-height: 1.6;
        }}
        .footer-links {{
            margin: 16px 0;
        }}
        .footer-links a {{
            color: #667eea;
            text-decoration: none;
            margin: 0 12px;
            font-size: 13px;
        }}
        .footer-links a:hover {{
            text-decoration: underline;
        }}
        @media only screen and (max-width: 640px) {{
            .content, .header, .footer {{
                padding-left: 24px;
                padding-right: 24px;
            }}
            .credential-value {{
                min-width: 100%;
                width: 100%;
            }}
        }}
    </style>
</head>
<body>
    <div class="email-wrapper">
        <!-- Header -->
        <div class="header">
            <div class="logo-section">
                <div class="logo-icon">🔐</div>
            </div>
            <h1>API Security Gateway</h1>
            <p>Secure Access Management Platform</p>
        </div>
        
        <!-- Main Content -->
        <div class="content">
            <div class="greeting">Welcome, {full_name}! 👋</div>
            
            <p class="intro-text">
                Your account has been successfully created with <span class="role-badge">{role}</span> access level. 
                You now have access to the API Security Gateway platform.
            </p>
            
            <!-- Credentials Section -->
            <div class="section">
                <div class="section-title">
                    <span class="icon">🔑</span>
                    <span>Your Login Credentials</span>
                </div>
                
                <div class="credentials-box">
                    <div class="credential-row">
                        <div class="credential-label">
                            <span class="icon">📧</span>
                            <span>Email Address</span>
                        </div>
                        <div class="credential-value">{recipient_email}</div>
                    </div>
                    
                    <div class="credential-row">
                        <div class="credential-label">
                            <span class="icon">🔒</span>
                            <span>Temporary Password</span>
                        </div>
                        <div class="credential-value">{password}</div>
                    </div>
                </div>
            </div>
            
            <!-- MFA/2FA Notice (if enabled) -->
            {"" if not mfa_enabled else '''
            <div class="info-box" style="border-left: 4px solid #667eea;">
                <div class="title">
                    <span class="icon">🔐</span>
                    <span>''' + ("Multi-Factor Authentication (MFA)" if role == "admin" else "Two-Factor Authentication (2FA)") + '''</span>
                </div>
                <div class="text">
                    <strong>''' + ("MFA is mandatory for admin accounts." if role == "admin" else "2FA has been enabled for your account.") + '''</strong><br><br>
                    On your first login, you will be prompted to set up an authenticator app (Google Authenticator, Microsoft Authenticator, or Authy).
                    <br><br>
                    <strong>Setup process:</strong>
                    <ol style="margin: 10px 0; padding-left: 20px;">
                        <li>Download Google Authenticator or Microsoft Authenticator on your phone</li>
                        <li>Scan the QR code shown after your first login</li>
                        <li>Enter the 6-digit code from the app to complete setup</li>
                    </ol>
                    After setup, you will need to enter a code from your authenticator app each time you log in.
                </div>
            </div>
            '''}
            
            <!-- Activation Info -->
            <div class="info-box">
                <div class="title">
                    <span class="icon">⏱️</span>
                    <span>Account Activation</span>
                </div>
                <div class="text">
                    Your account will be automatically activated in <strong>2 minutes</strong> from the time this email was sent. 
                    Please wait for the activation period to complete before attempting your first login.
                </div>
            </div>
            
            <!-- Next Steps -->
            <div class="section">
                <div class="section-title">
                    <span class="icon">📋</span>
                    <span>Next Steps</span>
                </div>
                
                <div class="next-steps">
                    <div class="step">
                        <div class="step-number">1</div>
                        <div class="step-content">
                            <div class="step-text">
                                <strong>Wait for activation</strong> - Your account will be ready in 2 minutes
                            </div>
                        </div>
                    </div>
                    
                    <div class="step">
                        <div class="step-number">2</div>
                        <div class="step-content">
                            <div class="step-text">
                                <strong>Access the login page</strong> - Click the button below to navigate to the platform
                            </div>
                        </div>
                    </div>
                    
                    <div class="step">
                        <div class="step-number">3</div>
                        <div class="step-content">
                            <div class="step-text">
                                <strong>Sign in with your credentials</strong> - Use the email and password provided above
                            </div>
                        </div>
                    </div>
                    
                    <div class="step">
                        <div class="step-number">4</div>
                        <div class="step-content">
                            <div class="step-text">
                                <strong>Change your password</strong> - For security, update your password immediately after first login
                            </div>
                        </div>
                    </div>
                </div>
            </div>
            
            <!-- Login Button -->
            <div style="text-align: center;">
                <a href="http://localhost:3000/login.html" class="login-button">Access Login Page →</a>
            </div>
            
            <!-- Security Notice -->
            <div class="alert-box">
                <div class="title">
                    <span class="icon">⚠️</span>
                    <span>Important Security Guidelines</span>
                </div>
                <div class="text">
                    Please follow these security best practices to protect your account:
                </div>
                <ul>
                    <li>Change your temporary password immediately after first login</li>
                    <li>Never share your password with anyone, including administrators</li>
                    <li>Use a strong, unique password that you don't use elsewhere</li>
                    <li>Enable two-factor authentication if available</li>
                    <li>Report any suspicious activity to your system administrator</li>
                </ul>
            </div>
            
            <div class="divider"></div>
            
            <!-- Support Section -->
            <div class="support-section">
                <p><strong>Need Help?</strong></p>
                <p>If you experience any issues accessing your account, please contact your system administrator.</p>
            </div>
        </div>
        
        <!-- Footer -->
        <div class="footer">
            <div class="footer-logo">🔐</div>
            <p><strong>API Security Gateway</strong></p>
            <p>This is an automated security notification. Please do not reply to this email.</p>
            <p style="margin-top: 16px; color: #d1d5db;">© 2026 API Security Gateway. All rights reserved.</p>
        </div>
    </div>
</body>
</html>
        """
        
        # Plain text version (for email clients that don't support HTML)
        text_body = f"""
════════════════════════════════════════════════════════════════
                    API SECURITY GATEWAY
                Secure Access Management Platform
════════════════════════════════════════════════════════════════

Welcome, {full_name}!

Your account has been successfully created with {role.upper()} access level.
You now have access to the API Security Gateway platform.

────────────────────────────────────────────────────────────────
YOUR LOGIN CREDENTIALS
────────────────────────────────────────────────────────────────

📧 Email Address:
   {recipient_email}

🔒 Temporary Password:
   {password}

────────────────────────────────────────────────────────────────
ACCOUNT ACTIVATION
────────────────────────────────────────────────────────────────

⏱️  Your account will be automatically activated in 2 MINUTES from 
   the time this email was sent. Please wait for the activation 
   period to complete before attempting your first login.

────────────────────────────────────────────────────────────────
NEXT STEPS
────────────────────────────────────────────────────────────────

1. Wait for activation - Your account will be ready in 2 minutes

2. Access the login page:
   http://localhost:3000/login.html

3. Sign in with your credentials using the email and password 
   provided above

4. Change your password - For security, update your password 
   immediately after first login

────────────────────────────────────────────────────────────────
IMPORTANT SECURITY GUIDELINES
────────────────────────────────────────────────────────────────

⚠️  Please follow these security best practices:

   • Change your temporary password immediately after first login
   • Never share your password with anyone, including administrators
   • Use a strong, unique password that you don't use elsewhere
   • Enable two-factor authentication if available
   • Report any suspicious activity to your system administrator

────────────────────────────────────────────────────────────────
NEED HELP?
────────────────────────────────────────────────────────────────

If you experience any issues accessing your account, please 
contact your system administrator.

────────────────────────────────────────────────────────────────

This is an automated security notification.
Please do not reply to this email.

© 2026 API Security Gateway. All rights reserved.

════════════════════════════════════════════════════════════════
        """
        
        # Attach both versions
        part1 = MIMEText(text_body, "plain")
        part2 = MIMEText(html_body, "html")
        msg.attach(part1)
        msg.attach(part2)
        
        # Send email
        with smtplib.SMTP(smtp_host, smtp_port) as server:
            server.starttls()
            server.login(smtp_user, smtp_password)
            server.send_message(msg)
        
        print(f"✓ Credentials email sent successfully to {recipient_email}")
        return True
        
    except Exception as e:
        print(f"ERROR sending email to {recipient_email}: {str(e)}")
        print(f"WARNING: Failed to deliver credentials. Please send manually.")
        # ⚠️ SECURITY: Never log passwords
        return False


# =============================================================================
# MFA/2FA UTILITIES
# =============================================================================

import pyotp
import qrcode
import io
import base64
import json
import hashlib


def generate_mfa_secret() -> str:
    """
    Generate a new TOTP secret for MFA setup.
    
    Returns:
        str: Base32-encoded secret key
    """
    return pyotp.random_base32()


def get_totp_uri(secret: str, email: str, issuer: str = "API Security Gateway") -> str:
    """
    Generate the OTP auth URI for QR code.
    
    Args:
        secret: Base32-encoded secret
        email: User's email (used as account name)
        issuer: App name shown in authenticator
    
    Returns:
        str: otpauth:// URI
    """
    totp = pyotp.TOTP(secret)
    return totp.provisioning_uri(name=email, issuer_name=issuer)


def generate_qr_code_base64(secret: str, email: str) -> str:
    """
    Generate QR code as base64 image for authenticator app setup.
    
    Args:
        secret: Base32-encoded TOTP secret
        email: User's email
    
    Returns:
        str: Base64-encoded PNG image
    """
    uri = get_totp_uri(secret, email)
    
    # Generate QR code
    qr = qrcode.QRCode(
        version=1,
        error_correction=qrcode.constants.ERROR_CORRECT_L,
        box_size=10,
        border=4,
    )
    qr.add_data(uri)
    qr.make(fit=True)
    
    # Create image
    img = qr.make_image(fill_color="black", back_color="white")
    
    # Convert to base64 with data URI prefix so it can be used directly in <img src="...">
    buffer = io.BytesIO()
    img.save(buffer, format='PNG')
    buffer.seek(0)
    
    b64 = base64.b64encode(buffer.getvalue()).decode('utf-8')
    return f"data:image/png;base64,{b64}"


def verify_totp(secret: str, code: str, valid_window: int = 1) -> bool:
    """
    Verify a TOTP code.
    
    Args:
        secret: Base32-encoded secret
        code: 6-digit code from authenticator
        valid_window: Number of 30-sec windows to allow (1 = ±30 sec)
    
    Returns:
        bool: True if code is valid
    """
    if not secret or not code:
        return False
    
    # Clean the code (remove spaces, ensure 6 digits)
    code = code.replace(" ", "").strip()
    if not code.isdigit() or len(code) != 6:
        return False
    
    totp = pyotp.TOTP(secret)
    return totp.verify(code, valid_window=valid_window)


def generate_backup_codes(count: int = 8) -> tuple[list[str], list[str]]:
    """
    Generate backup codes for MFA recovery.
    
    Args:
        count: Number of backup codes to generate
    
    Returns:
        tuple: (plain_codes for user, hashed_codes for storage)
    """
    plain_codes = []
    hashed_codes = []
    
    for _ in range(count):
        # Generate 8-character alphanumeric code
        code = secrets.token_hex(4).upper()  # e.g., "A1B2C3D4"
        plain_codes.append(code)
        
        # Hash for secure storage
        hashed = hashlib.sha256(code.encode()).hexdigest()
        hashed_codes.append(hashed)
    
    return plain_codes, hashed_codes


def verify_backup_code(code: str, hashed_codes_json: str) -> tuple[bool, str]:
    """
    Verify a backup code and remove it from the list if valid.
    
    Args:
        code: Plain backup code entered by user
        hashed_codes_json: JSON string of hashed backup codes
    
    Returns:
        tuple: (is_valid, updated_hashed_codes_json)
    """
    if not code or not hashed_codes_json:
        return False, hashed_codes_json
    
    code = code.replace(" ", "").replace("-", "").upper().strip()
    hashed_input = hashlib.sha256(code.encode()).hexdigest()
    
    try:
        hashed_codes = json.loads(hashed_codes_json)
    except json.JSONDecodeError:
        return False, hashed_codes_json
    
    if hashed_input in hashed_codes:
        # Remove used code
        hashed_codes.remove(hashed_input)
        return True, json.dumps(hashed_codes)
    
    return False, hashed_codes_json


def format_backup_codes_for_display(codes: list[str]) -> str:
    """
    Format backup codes for user display (grouped pairs).
    
    Args:
        codes: List of backup codes
    
    Returns:
        str: Formatted string with codes in pairs
    """
    formatted = []
    for i in range(0, len(codes), 2):
        pair = codes[i:i+2]
        formatted.append("  •  ".join(pair))
    return "\n".join(formatted)

def send_password_reset_email(recipient_email: str, token: str, expires_minutes: int = 60) -> bool:
    """
    Send a password reset email containing a one-time link with the raw token.
    Returns True if sent successfully.
    """
    smtp_host = os.getenv("SMTP_HOST", "smtp.gmail.com")
    smtp_port = int(os.getenv("SMTP_PORT", "587"))
    smtp_user = os.getenv("SMTP_USER")
    smtp_password = os.getenv("SMTP_PASSWORD")
    from_email = os.getenv("FROM_EMAIL", smtp_user)

    if not smtp_user or not smtp_password:
        print("ERROR: SMTP credentials not configured in .env file")
        return False

    reset_link = f"http://localhost:3000/reset-password.html?token={token}"

    try:
        msg = MIMEMultipart("alternative")
        msg["Subject"] = "Reset your API Security Gateway password"
        msg["From"] = f"API Security Gateway <{from_email}>"
        msg["To"] = recipient_email

        html_body = f"""
        <html>
        <body>
        <p>Hello,</p>
        <p>We received a request to reset the password for your API Security Gateway account.</p>
        <p>Please click the link below to reset your password. This link will expire in {expires_minutes} minutes and can be used only once.</p>
        <p><a href=\"{reset_link}\">Reset your password</a></p>
        <p>If you did not request this, you can safely ignore this email.</p>
        </body>
        </html>
        """

        msg.attach(MIMEText(html_body, "html"))

        server = smtplib.SMTP(smtp_host, smtp_port, timeout=10)
        server.ehlo()
        server.starttls()
        server.login(smtp_user, smtp_password)
        server.sendmail(from_email, recipient_email, msg.as_string())
        server.quit()
        return True
    except Exception as e:
        print(f"ERROR: Failed to send password reset email to {recipient_email}: {str(e)}")
        return False


def send_password_changed_notification(recipient_email: str, ip_address: str = "Unknown") -> bool:
    """
    Send a notification email to the user that their password was changed.
    This alerts them to unauthorized access if they didn't initiate the reset.
    Returns True if sent successfully.
    """
    from datetime import datetime
    
    smtp_host = os.getenv("SMTP_HOST", "smtp.gmail.com")
    smtp_port = int(os.getenv("SMTP_PORT", "587"))
    smtp_user = os.getenv("SMTP_USER")
    smtp_password = os.getenv("SMTP_PASSWORD")
    from_email = os.getenv("FROM_EMAIL", smtp_user)

    if not smtp_user or not smtp_password:
        print("ERROR: SMTP credentials not configured in .env file")
        return False

    change_time = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S UTC")

    try:
        msg = MIMEMultipart("alternative")
        msg["Subject"] = "⚠️ Your API Security Gateway password was changed"
        msg["From"] = f"API Security Gateway <{from_email}>"
        msg["To"] = recipient_email

        html_body = f"""
        <html>
        <body style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; line-height: 1.6; color: #333;">
        <div style="max-width: 600px; margin: 0 auto; padding: 20px;">
            <h2 style="color: #EF4444;">🔒 Password Changed</h2>
            <p>Hello,</p>
            <p>This is a confirmation that the password for your API Security Gateway account (<strong>{recipient_email}</strong>) was successfully changed.</p>
            <table style="background: #f5f5f5; padding: 16px; border-radius: 8px; margin: 16px 0; width: 100%;">
                <tr><td><strong>Time:</strong></td><td>{change_time}</td></tr>
                <tr><td><strong>IP Address:</strong></td><td>{ip_address}</td></tr>
            </table>
            <p><strong>If you made this change</strong>, no further action is required.</p>
            <p style="color: #EF4444;"><strong>If you did NOT make this change</strong>, your account may be compromised. Please contact your administrator immediately.</p>
            <hr style="border: none; border-top: 1px solid #ddd; margin: 24px 0;">
            <p style="color: #666; font-size: 12px;">This is an automated security notification from API Security Gateway.</p>
        </div>
        </body>
        </html>
        """

        msg.attach(MIMEText(html_body, "html"))

        server = smtplib.SMTP(smtp_host, smtp_port, timeout=10)
        server.ehlo()
        server.starttls()
        server.login(smtp_user, smtp_password)
        server.sendmail(from_email, recipient_email, msg.as_string())
        server.quit()
        return True
    except Exception as e:
        print(f"ERROR: Failed to send password change notification to {recipient_email}: {str(e)}")
        return False


# ============================================================================
# User-Agent Parser — lightweight, no external dependency
# ============================================================================

import re as _re

def parse_user_agent(ua: str) -> str:
    """Parse a User-Agent string into a short 'Browser on OS' label."""
    if not ua:
        return "Unknown Device"

    # Detect browser
    browser = "Unknown Browser"
    if _re.search(r"Edg(e|A)?/", ua):
        browser = "Edge"
    elif _re.search(r"OPR/|Opera", ua):
        browser = "Opera"
    elif _re.search(r"Chrome/", ua) and not _re.search(r"Edg", ua):
        browser = "Chrome"
    elif _re.search(r"Firefox/", ua):
        browser = "Firefox"
    elif _re.search(r"Safari/", ua) and not _re.search(r"Chrome", ua):
        browser = "Safari"
    elif _re.search(r"MSIE|Trident", ua):
        browser = "Internet Explorer"

    # Detect OS
    os_name = "Unknown OS"
    if _re.search(r"Windows NT 10", ua):
        os_name = "Windows"
    elif _re.search(r"Windows", ua):
        os_name = "Windows"
    elif _re.search(r"Macintosh|Mac OS X", ua):
        os_name = "macOS"
    elif _re.search(r"Android", ua):
        os_name = "Android"
    elif _re.search(r"iPhone|iPad", ua):
        os_name = "iOS"
    elif _re.search(r"Linux", ua):
        os_name = "Linux"
    elif _re.search(r"CrOS", ua):
        os_name = "ChromeOS"

    return f"{browser} on {os_name}"


# ============================================================================
# Audit Logging
# ============================================================================

def log_audit(db, user_id: int, event_type: str, detail: str = None, request=None):
    """
    Record a security-relevant account event.
    `request` is a FastAPI Request object (optional) — used to extract IP and User-Agent.
    """
    from models import AuditLog
    from datetime import datetime, timezone

    ip = None
    ua = None
    if request is not None:
        ip = request.client.host if request.client else None
        ua = request.headers.get("user-agent", "")

    entry = AuditLog(
        user_id=user_id,
        event_type=event_type,
        detail=detail,
        ip_address=ip,
        user_agent=ua,
        created_at=datetime.now(timezone.utc),
    )
    db.add(entry)
    # Don't commit here — let the caller's commit include the audit row atomically
