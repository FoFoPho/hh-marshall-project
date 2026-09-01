import io
import os
from datetime import datetime

from reportlab.pdfgen import canvas as rl_canvas
from reportlab.lib.pagesizes import letter, landscape
from reportlab.lib.colors import HexColor


TEMPLATE_PATH = os.path.join(os.path.dirname(__file__), 'static', 'assets', 'MP Cert Template.png')

DARK = HexColor('#111111')
BLUE = HexColor('#1B4FBF')


def generate_certificate(first_name, last_name, module_title, cert_number, completed_at):
    page_w, page_h = landscape(letter)   # 792 x 612 pts

    buf = io.BytesIO()
    c = rl_canvas.Canvas(buf, pagesize=(page_w, page_h))

    # Full-page template background
    c.drawImage(TEMPLATE_PATH, 0, 0, width=page_w, height=page_h, preserveAspectRatio=False)

    # ── Name ─────────────────────────────────────────────────────────────
    # Centered on the blank underline between "This certifies that" and the rule
    name_text = f"{first_name} {last_name}".upper()
    c.setFillColor(BLUE)
    c.setFont('Helvetica-Bold', 32)
    c.drawCentredString(page_w * 0.500, page_h * 0.530, name_text)

    # ── Module title ──────────────────────────────────────────────────────
    # Centered on the blank underline between "has successfully completed" and the rule
    c.setFillColor(DARK)
    c.setFont('Helvetica-Bold', 34)
    c.drawCentredString(page_w * 0.500, page_h * 0.385, module_title.upper())

    # ── Date ─────────────────────────────────────────────────────────────
    # Over the DATE underline, right column
    try:
        date_fmt = datetime.strptime(completed_at, '%Y-%m-%d').strftime('%m/%d/%Y')
    except Exception:
        date_fmt = completed_at or ''
    c.setFont('Helvetica', 12)
    c.drawCentredString(page_w * 0.710, page_h * 0.183, date_fmt)

    # ── Certificate number ────────────────────────────────────────────────
    # On the underline after "CERTIFICATE NO."
    c.setFont('Helvetica', 10)
    c.drawString(page_w * 0.195, page_h * 0.068, cert_number)

    c.save()
    return buf.getvalue()
