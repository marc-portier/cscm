# src/cscm/simulation/mailer.py

import os
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.base import MIMEBase
from email.mime.image import MIMEImage
from email import encoders
from pathlib import Path
from logging import getLogger
from typing import Optional, List
import smtplib
from tempfile import NamedTemporaryFile

log = getLogger(__name__)


def send_simulation_email(
    to_list: List[str],
    subject: str,
    html_body: str,
    overview_map_path: Optional[Path] = None,
    attachment_paths: Optional[List[Path]] = None
) -> None:
    """
    Sends simulation HTML reports with CID embedded overview map and GPX attachments.
    Uses local SMTP relay configurations from .env.
    """
    smtp_host = os.environ.get("SMTP_HOST")

    if not smtp_host:
        log.error("SMTP_HOST environment variable is not set. Cannot send email.")
        log.info("Please set SMTP_HOST in your .env file or environment variables to a valid SMTP relay host.")
        # Save the HTML body to a tmp file for manual review
        tempfile = NamedTemporaryFile(delete=False, suffix=".html", prefix="simulation_email_")
        with open(tempfile.name, "w") as f:
            f.write(html_body)
        log.info(f"email-html message saved to {tempfile.name} for manual evaluation.")
        return

    smtp_port_str = os.environ.get("SMTP_PORT", "25")
    smtp_user = os.environ.get("SMTP_USER")
    smtp_pass = os.environ.get("SMTP_PASS")
    smtp_port = int(smtp_port_str)

    msg = MIMEMultipart("mixed")
    msg["Subject"] = subject
    msg["From"] = os.environ.get("SMTP_FROM", "me@example.org")
    msg["To"] = ", ".join(to_list)

    # Alternate part for HTML body and inline images
    msg_alternative = MIMEMultipart("alternative")
    msg.attach(msg_alternative)

    # Attach HTML
    msg_html = MIMEText(html_body, "html", "utf-8")
    msg_alternative.attach(msg_html)

    # Embed overview image using Content-ID (CID) if present
    if overview_map_path and overview_map_path.exists():
        try:
            with open(overview_map_path, "rb") as img_f:
                msg_img = MIMEImage(img_f.read())
                msg_img.add_header("Content-ID", "<overview>")
                msg_img.add_header("Content-Disposition", "inline", filename=overview_map_path.name)
                msg_alternative.attach(msg_img)
                log.info(f"Embedded overview chart inline: {overview_map_path.name}")
        except Exception as e:
            log.warning(f"Could not inline embed overview image {overview_map_path}: {e}")

    # Attach GPX or other binary files
    if attachment_paths:
        for a_path in attachment_paths:
            if a_path.exists():
                try:
                    with open(a_path, "rb") as f:
                        part = MIMEBase("application", "octet-stream")
                        part.set_payload(f.read())
                        encoders.encode_base64(part)
                        part.add_header(
                            "Content-Disposition",
                            f"attachment; filename={a_path.name}"
                        )
                        msg.attach(part)
                        log.info(f"Attached GPX file: {a_path.name}")
                except Exception as e:
                    log.warning(f"Could not attach file {a_path}: {e}")

    # SMTP Transmission block
    log.info(f"Connecting to SMTP relay server at {smtp_host}:{smtp_port}...")
    with smtplib.SMTP(smtp_host, smtp_port, timeout=10) as server:
        if smtp_user and smtp_pass:
            log.info(f"Authenticating SMTP session for user: {smtp_user}...")
            server.login(smtp_user, smtp_pass)

        server.sendmail(msg["From"], to_list, msg.as_string())
        log.info(f"Successfully sent simulation report email to: {', '.join(to_list)}")
