# src/cscm/simulation/mailer.py

import os
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.base import MIMEBase
from email.mime.image import MIMEImage
from email import encoders
from pathlib import Path
from logging import getLogger
from typing import Optional
import smtplib
from tempfile import NamedTemporaryFile

log = getLogger(__name__)


def send_simulation_email(
    to_list: list[str],
    subject: str,
    html_body: str,
    overview_map_path: Optional[Path] = None,
    attachment_paths: Optional[list[Path]] = None
) -> None:
    """
    Sends an HTML formatted simulation update email with inline CID-linked image embedding
    and attachments over local SMTP relay or credentials-authenticated Google Mail server.
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

    try:
        smtp_port = int(os.environ.get("SMTP_PORT", "25"))
    except ValueError:
        smtp_port = 25

    smtp_user = os.environ.get("SMTP_USER")
    smtp_pass = os.environ.get("SMTP_PASS")

    msg = MIMEMultipart("related")
    msg["Subject"] = subject
    msg["From"] = os.environ.get("SMTP_FROM", "cscm-simulator@example.org")
    msg["To"] = ", ".join(to_list)

    # HTML Body Container
    msg_alternative = MIMEMultipart("alternative")
    msg.attach(msg_alternative)

    # Plain text fallback
    plain_text = "Goeiemorgen, hierbij de nieuwste update van de getijden- en trajectsimulaties."
    msg_alternative.attach(MIMEText(plain_text, "plain", "utf-8"))

    # HTML body
    msg_alternative.attach(MIMEText(html_body, "html", "utf-8"))

    # Inline Overview Map Embedding
    if overview_map_path and overview_map_path.exists():
        try:
            with open(overview_map_path, "rb") as img_f:
                msg_img = MIMEImage(img_f.read())
                msg_img.add_header("Content-ID", "<overview>")
                msg_img.add_header("Content-Disposition", "inline", filename=overview_map_path.name)
                msg.attach(msg_img)
                log.info(f"Embedded overview chart inline: {overview_map_path.name}")
        except Exception as e:
            log.error(f"Failed to embed inline image {overview_map_path.name}: {e}")

    # Standard MIME Attachments (e.g., GPX tracks)
    if attachment_paths:
        for p in attachment_paths:
            if p.exists():
                try:
                    with open(p, "rb") as f:
                        part = MIMEBase("application", "octet-stream")
                        part.set_payload(f.read())
                        encoders.encode_base64(part)
                        part.add_header(
                            "Content-Disposition",
                            f"attachment; filename={p.name}"
                        )
                        msg.attach(part)
                        log.info(f"Attached GPX file: {p.name}")
                except Exception as e:
                    log.error(f"Failed to attach file {p.name}: {e}")

    # SMTP Transmission block
    log.info(f"Connecting to SMTP relay server at {smtp_host}:{smtp_port}...")
    try:
        # Use SSL/TLS port 465 or standard 25/587 port with STARTTLS
        if smtp_port == 465:
            server = smtplib.SMTP_SSL(smtp_host, smtp_port, timeout=15)
        else:
            server = smtplib.SMTP(smtp_host, smtp_port, timeout=15)

        # SMTP EHLO & STARTTLS handshake
        if smtp_port == 587 or smtp_port == 25:
            try:
                server.starttls()
            except Exception as e:
                # Local open SMTP relays do not require TLS
                log.warning(f"STARTTLS handshake skipped or failed: {e}")

        if smtp_user and smtp_pass:
            server.login(smtp_user, smtp_pass)

        server.sendmail(msg["From"], to_list, msg.as_string())
        server.quit()
        log.info("Email transmitted successfully!")
    except Exception as e:
        log.error(f"Failed to transmit email via SMTP relay {smtp_host}:{smtp_port}: {e}")
        # Re-raise so simulation supervisor is informed of transport issues
        raise e
