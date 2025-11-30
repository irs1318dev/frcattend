"""Send QR Code Emails."""

from collections.abc import Iterator
from email import encoders
from email.mime import base, image, multipart, text
import pathlib
import smtplib
import time
from typing import cast, Optional

from irsattend import config, model
from irsattend.features import qr_code_generator


class EmailError(Exception):
    """Error while creating or sending emails."""


def send_all_emails(
    qr_folder: pathlib.Path,
    students: list[model.Student],
    email: Optional[str] = None,
) -> Iterator[tuple[str, bool]]:
    """Send an email with a QR code to all students.

    Yields a tuple of student ID and a boolean indicating success.
    """
    for student in students:
        qr_path = qr_folder / f"{student.student_id}.png"
        if not qr_path.exists():
            qr_code_generator.generate_qr_code_image(student.student_id, qr_path)
        try:
            send_email(
                student.email if email is None else email,
                f"{student.first_name} {student.last_name}",
                qr_path,
            )
        except (
            smtplib.SMTPAuthenticationError,
            smtplib.SMTPAuthenticationError,
            smtplib.SMTPException,
        ):
            yield student.student_id, False
        else:
            yield student.student_id, True
        time.sleep(0.5)  # Experimental
        # Several emails were not sent when emails sent to entire team on 3 Sep 2025.
        #   Of 105 students, only 94 emails were actually sent, but there were no
        #   errors. Our hypothesis is that Gmail didn't like us sending many emails
        #   in quick succession, and that adding a short pause between each email
        #   might address the problem.


def send_email(
    email: str, student_name: str, qr_code_path: pathlib.Path
) -> tuple[bool, str]:
    """
    Sends an email with a QR Code to a student.
    """
    if any(
        [
            config.settings.smtp_server is None,
            config.settings.smtp_username is None,
            config.settings.smtp_password is None,
            config.settings.smtp_port is None,
        ]
    ):
        missing = []
        if config.settings.smtp_server is None:
            missing.append("SMTP_SERVER")
        if config.settings.smtp_username is None:
            missing.append("SMTP_USERNAME")
        if config.settings.smtp_password is None:
            missing.append("SMTP_PASSWORD")
        return False, f"SMTP settings missing: {', '.join(missing)}"
    else:
        smtp_server = cast(str, config.settings.smtp_server)
        smtp_username = cast(str, config.settings.smtp_username)
        smtp_password = cast(str, config.settings.smtp_password)
        email_sender_name = cast(str, config.settings.email_sender_name)
        smtp_port = cast(int, config.settings.smtp_port)
    # Create email
    msg = multipart.MIMEMultipart("related")
    msg["Subject"] = "Your Attendance Pass"
    msg["From"] = f"{email_sender_name} <{smtp_username}>"
    msg["To"] = email
    # Email using HTML, makes it look nicer
    html_body = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <style>
            body {{
                font-family: 'Arial',
                sans-serif;
                margin: 0;
                padding: 20px;
                background-color: #f5f5f5; }}
            .container {{
                max-width: 600px;
                margin: 0 auto;
                background-color: white;
                border-radius: 10px;
                overflow: hidden;
                box-shadow: 0 4px 6px rgba(0,0,0,0.1); }}
            .header {{
                background: #662382;
                background:
                    linear-gradient(135deg,rgba(102, 35, 130, 1) 39%,
                    rgba(249, 178, 52, 1) 100%);
                color: white;
                padding: 30px;
                text-align: center; }}
            .header h1 {{
                margin: 0;
                font-size: 24px;
                font-weight: bold;
                color: #fff; }}
            .content {{
                padding: 30px;
                background-color:
                #eee; text-align:
                # center; }}
            .pass-container {{
                text-align: center;
                margin: 30px 0;
                padding: 20px;
                background-color: #f8f9fa;
                border-radius: 8px; }}
            .pass-container img {{
                max-width: 100%;
                height: auto;
                border: 2px solid #e9ecef;
                border-radius: 12px; }}
            .footer {{
                background-color: #f8f9fa;
                padding: 20px;
                text-align: center;
                color: #6c757d;
                font-size: 14px; }}
        </style>
    </head>
    <body>
        <div class="container">
            <div class="header">
                <h1>🤖 IRS 1318 Attendance System</h1>
                <p>Your Attendance Pass</p>
            </div>
            <div class="content">
                <h2>Hello {student_name}! 👋</h2>
                <p>Your attendance pass is ready! This pass is unique to you and
                will be used to track your attendance at every meeting.</p>
                <p>Please star this email or save the attached image file
                to a convenient location on your phone.</p>

                <div class="pass-container">
                    <h3>Your Attendance Pass:</h3>
                    <img src="cid:qr_code" alt="Your personal pass">
                </div>

                <p><strong>Important:</strong> This pass is personal to you.
                You are not to share it with others.</p>
            </div>
            <div class="footer">
                <p>IRS 1318 Robotics Team | Attendance Management System</p>
                <p>If you have any questions, please speak with a mentor.</p>
            </div>
        </div>
    </body>
    </html>
    """
    msg.attach(text.MIMEText(html_body, "html"))
    with open(qr_code_path, "rb") as fp:
        img = image.MIMEImage(fp.read())
    img.add_header("Content-ID", "<qr_code>")
    img.add_header("Content-Disposition", "inline", filename=qr_code_path.name)
    msg.attach(img)
    # Also send QR code as attachment, to make it easy to save to gallary.
    with open(qr_code_path, "rb") as fp:
        attachment = base.MIMEBase("application", "octet-stream")
        attachment.set_payload(fp.read())
    encoders.encode_base64(attachment)
    attachment.add_header("Content-Disposition", "attachment", filename="irsattend.jpg")
    msg.attach(attachment)
    # Note: IHS WIFI has been known to block email.
    if smtp_port == 465:
        with smtplib.SMTP_SSL(smtp_server, smtp_port) as server:
            server.login(smtp_username, smtp_password)
            server.send_message(msg)
    else:  # Port 587 is for TLS encryption.
        with smtplib.SMTP(smtp_server, smtp_port) as server:
            server.starttls()
            server.login(smtp_username, smtp_password)
            server.send_message(msg)

    return True, "Email sent successfully."
