import os
import smtplib
import asyncio
import logging
from datetime import datetime
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

logger = logging.getLogger("jarvis.skills.notifier")

class NotifierSkill:
    """
    Centralized notification system for J.A.R.V.I.S.
    Handles Email, Desktop, and (future) Telegram/SMS.
    """
    def __init__(self):
        self.email_enabled = os.getenv("JARVIS_EMAIL_ENABLED", "false").lower() == "true"
        self.last_notifications = {} # Throttling

    async def notify(self, title: str, message: str, priority: str = "normal"):
        """Main entry point for all notifications."""
        logger.info(f"Notification triggered: {title} ({priority})")
        
        # Always try desktop if on Windows
        if os.name == "nt":
            self.notify_desktop(title, message)
        
        # Email for high priority or if enabled
        if self.email_enabled or priority == "high":
            await self.notify_email(title, message)

    def notify_desktop(self, title: str, message: str):
        """Send a Windows notification."""
        import subprocess
        # Clean message for powershell
        clean_msg = message.replace("'", "").replace("\"", "").replace("\n", " ")
        clean_title = title.replace("'", "").replace("\"", "")
        powershell_cmd = f"$wshell = New-Object -ComObject WScript.Shell; $wshell.Popup('{clean_msg}', 0, '{clean_title}', 64)"
        try:
            subprocess.Popen(["powershell", "-NoProfile", "-Command", powershell_cmd], shell=False)
        except Exception as e:
            logger.error(f"Desktop notification failed: {e}")

    async def notify_email(self, title: str, message: str):
        """Send an email using JARVIS Identity."""
        recipient = os.getenv("NOTIFY_EMAIL_RECIPIENT")
        smtp_server = os.getenv("SMTP_SERVER")
        smtp_port = int(os.getenv("SMTP_PORT", "587"))
        
        # Prioritize JARVIS Identity for the sender
        smtp_user = os.getenv("JARVIS_EMAIL") or os.getenv("SMTP_USER")
        smtp_pass = os.getenv("JARVIS_EMAIL_PASS") or os.getenv("SMTP_PASS")

        if not all([smtp_server, smtp_user, smtp_pass, recipient]):
            logger.warning("Email notification skipped: Missing SMTP configuration.")
            return

        try:
            msg = MIMEMultipart()
            msg['From'] = f"J.A.R.V.I.S. <{smtp_user}>"
            msg['To'] = recipient
            msg['Subject'] = title
            
            # Prepare message for HTML
            html_message = message.replace('\n', '<br>')
            
            # Format as HTML for better presentation (Elite Stark-esque Theme)
            html = f"""
            <html>
            <body style="font-family: 'Segoe UI', Roboto, Helvetica, Arial, sans-serif; background-color: #0a0e14; padding: 20px; color: #e1e1e1;">
                <div style="max-width: 600px; margin: 0 auto; background-color: #161b22; padding: 30px; border-radius: 12px; border: 1px solid #30363d; box-shadow: 0 4px 24px rgba(0,0,0,0.5);">
                    <div style="text-align: center; margin-bottom: 30px;">
                        <h1 style="color: #58a6ff; font-weight: 300; letter-spacing: 2px; margin: 0;">J.A.R.V.I.S.</h1>
                        <p style="color: #8b949e; font-size: 12px; text-transform: uppercase; margin-top: 5px;">Elite Autonomous Intelligence</p>
                    </div>
                    
                    <h2 style="color: #ffffff; border-bottom: 1px solid #30363d; padding-bottom: 15px; font-size: 18px;">Action Report: {title}</h2>
                    
                    <div style="background-color: rgba(88, 166, 255, 0.05); padding: 20px; border-left: 3px solid #58a6ff; border-radius: 4px; margin: 25px 0;">
                        <p style="margin: 0; line-height: 1.6; font-size: 15px;">{html_message}</p>
                    </div>
                    
                    <div style="margin-top: 30px; padding-top: 20px; border-top: 1px solid #30363d; color: #8b949e; font-size: 11px;">
                        <table style="width: 100%;">
                            <tr>
                                <td>TIMESTAMP: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}</td>
                                <td style="text-align: right;">PROTOCOL: MARK-VIII CORE</td>
                            </tr>
                            <tr>
                                <td>ASSETS: GITHUB | GMAIL | COLAB</td>
                                <td style="text-align: right;">STATUS: SYNCED</td>
                            </tr>
                        </table>
                    </div>
                </div>
            </body>
            </html>
            """
            msg.attach(MIMEText(html, 'html'))

            def _send_smtp():
                import socket
                try:
                    # Attempt connection with a strict timeout to avoid hanging the loop
                    with smtplib.SMTP(smtp_server, smtp_port, timeout=10) as server:
                        server.starttls()
                        server.login(smtp_user, smtp_pass)
                        server.send_message(msg)
                    return True
                except (socket.gaierror, socket.timeout) as dns_err:
                    logger.warning(f"Network/DNS error during email dispatch: {dns_err}. This usually indicates a momentary internet dropout.")
                    return False
                except Exception as e:
                    logger.error(f"Critical SMTP failure: {e}")
                    return False

            success = await asyncio.get_running_loop().run_in_executor(None, _send_smtp)
            if success:
                logger.info(f"Autonomous email sent to {recipient}")
        except Exception as e:
            logger.error(f"Email notification pipeline failed: {e}")

# Singleton
notifier = NotifierSkill()
