# tests/test_mailer.py

import unittest
from pathlib import Path
import tempfile
from cscm.simulation.mailer import build_simulation_email


class TestMailer(unittest.TestCase):

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.dir_path = Path(self.temp_dir.name)

        # Minimal valid 1x1 PNG
        self.png_path = self.dir_path / "overview.png"
        png_data = (
            b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
            b"\x08\x06\x00\x00\x00\x1f\x15c4\x00\x00\x00\nIDATx\x9cc\x00\x01\x00"
            b"\x00\x05\x00\x01\r\n-\xb4\x00\x00\x00\x00IEND\xaeB`\x82"
        )
        self.png_path.write_bytes(png_data)

        # Dummy GPX attachment
        self.gpx_path = self.dir_path / "route.gpx"
        self.gpx_path.write_text("<gpx></gpx>", encoding="utf-8")

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_build_email_with_overview_and_attachments(self):
        msg = build_simulation_email(
            to_list=["test@example.com"],
            subject="Test Simulation Report",
            html_body="<h1>Rapport</h1><img src='cid:overview'>",
            overview_map_path=self.png_path,
            attachment_paths=[self.gpx_path],
            plain_body="Custom plain text body",
            from_addr="sender@example.com"
        )

        self.assertEqual(msg["Subject"], "Test Simulation Report")
        self.assertEqual(msg["From"], "sender@example.com")
        self.assertEqual(msg["To"], "test@example.com")
        self.assertEqual(msg.get_content_type(), "multipart/mixed")

        # Root parts: [0] = multipart/related, [1] = application/octet-stream (attachment)
        root_parts = msg.get_payload()
        self.assertEqual(len(root_parts), 2)

        part_related = root_parts[0]
        self.assertEqual(part_related.get_content_type(), "multipart/related")

        part_attachment = root_parts[1]
        self.assertEqual(part_attachment.get_content_type(), "application/octet-stream")
        self.assertIn("attachment", part_attachment.get("Content-Disposition"))
        self.assertIn("route.gpx", part_attachment.get("Content-Disposition"))

        # Inside multipart/related: [0] = multipart/alternative, [1] = image/png
        related_parts = part_related.get_payload()
        self.assertEqual(len(related_parts), 2)

        part_alt = related_parts[0]
        self.assertEqual(part_alt.get_content_type(), "multipart/alternative")

        part_img = related_parts[1]
        self.assertEqual(part_img.get_content_type(), "image/png")
        self.assertEqual(part_img.get("Content-ID"), "<overview>")
        self.assertIn("inline", part_img.get("Content-Disposition"))
        self.assertIn("overview.png", part_img.get("Content-Disposition"))

        # Inside multipart/alternative: [0] = text/plain, [1] = text/html
        alt_parts = part_alt.get_payload()
        self.assertEqual(len(alt_parts), 2)
        self.assertEqual(alt_parts[0].get_content_type(), "text/plain")
        self.assertIn("Custom plain text body", alt_parts[0].get_payload(decode=True).decode("utf-8"))
        self.assertEqual(alt_parts[1].get_content_type(), "text/html")
        self.assertIn("<h1>Rapport</h1>", alt_parts[1].get_payload(decode=True).decode("utf-8"))

    def test_build_email_without_image(self):
        msg = build_simulation_email(
            to_list=["test@example.com"],
            subject="Report without Image",
            html_body="<p>No map attached</p>",
            overview_map_path=None,
            attachment_paths=[self.gpx_path]
        )

        self.assertEqual(msg.get_content_type(), "multipart/mixed")
        root_parts = msg.get_payload()
        self.assertEqual(len(root_parts), 2)

        # Directly multipart/alternative under root when there is no inline image
        part_alt = root_parts[0]
        self.assertEqual(part_alt.get_content_type(), "multipart/alternative")
        alt_parts = part_alt.get_payload()
        self.assertEqual(len(alt_parts), 2)
        self.assertEqual(alt_parts[0].get_content_type(), "text/plain")
        self.assertEqual(alt_parts[1].get_content_type(), "text/html")

        # Attachment is attached directly to root
        part_attachment = root_parts[1]
        self.assertEqual(part_attachment.get_content_type(), "application/octet-stream")

    def test_fallback_plain_text(self):
        msg = build_simulation_email(
            to_list=["test@example.com"],
            subject="Fallback Test",
            html_body="<p>HTML only provided</p>",
            plain_body=None
        )

        # Find text/plain part
        plain_part = None
        for p in msg.walk():
            if p.get_content_type() == "text/plain":
                plain_part = p
                break

        self.assertIsNotNone(plain_part)
        payload = plain_part.get_payload(decode=True).decode("utf-8")
        self.assertIn("Fallback Test", payload)
        self.assertIn("CSCM Simulator", payload)


if __name__ == "__main__":
    unittest.main()
