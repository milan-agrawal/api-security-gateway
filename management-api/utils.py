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


def send_credentials_email(
    recipient_email: str,
    full_name: str,
    password: str,
    role: str
) -> bool:
    """
    Send credentials to new user via Gmail SMTP
    
    Args:
        recipient_email: User's email address
        full_name: User's full name
        password: Generated password
        role: User role (user/admin)
    
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
