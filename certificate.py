import io
from datetime import datetime

from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.colors import HexColor, white, black
from reportlab.pdfgen import canvas as rl_canvas


BLUE       = HexColor('#1B4FBF')
DARK_GRAY  = HexColor('#555555')
LIGHT_GRAY = HexColor('#AAAAAA')
BLACK      = HexColor('#111111')


def _format_date(date_str):
    try:
        dt = datetime.strptime(date_str, '%Y-%m-%d')
        day = dt.day
        suffix = 'th' if 11 <= day <= 13 else {1: 'st', 2: 'nd', 3: 'rd'}.get(day % 10, 'th')
        return dt.strftime(f'%B {day}{suffix}, %Y')
    except Exception:
        return date_str


def generate_certificate(first_name, last_name, module_id, cert_number, completed_at):
    buf = io.BytesIO()
    pw, ph = landscape(A4)   # 841.89 x 595.28 pts

    c = rl_canvas.Canvas(buf, pagesize=landscape(A4))

    # ------------------------------------------------------------------
    # Background
    # ------------------------------------------------------------------
    c.setFillColor(white)
    c.rect(0, 0, pw, ph, fill=1, stroke=0)

    # ------------------------------------------------------------------
    # Border — double rule
    # ------------------------------------------------------------------
    m = 18
    c.setStrokeColor(BLUE)
    c.setLineWidth(3)
    c.rect(m, m, pw - 2*m, ph - 2*m, fill=0, stroke=1)
    c.setLineWidth(0.75)
    c.rect(m + 7, m + 7, pw - 2*(m + 7), ph - 2*(m + 7), fill=0, stroke=1)

    cx = pw / 2   # horizontal centre

    # ------------------------------------------------------------------
    # Logo area — "THE MARSHALL PROJECT / A HAMMER HAAG INITIATIVE"
    # ------------------------------------------------------------------
    y = ph - 68
    c.setFillColor(BLACK)
    c.setFont('Helvetica-Bold', 20)
    c.drawCentredString(cx, y, 'THE MARSHALL PROJECT')
    c.setFont('Helvetica', 9)
    c.setFillColor(DARK_GRAY)
    c.drawCentredString(cx, y - 14, 'A HAMMER HAAG INITIATIVE')

    # ------------------------------------------------------------------
    # "SAFETY TRAINING" label
    # ------------------------------------------------------------------
    y -= 44
    c.setFillColor(BLUE)
    c.setFont('Helvetica-Bold', 11)
    c.drawCentredString(cx, y, 'SAFETY TRAINING')

    # ------------------------------------------------------------------
    # "CERTIFICATE OF COMPLETION"
    # ------------------------------------------------------------------
    y -= 38
    c.setFillColor(BLACK)
    c.setFont('Helvetica-Bold', 34)
    c.drawCentredString(cx, y, 'CERTIFICATE OF COMPLETION')

    # Thin rule
    y -= 18
    c.setStrokeColor(LIGHT_GRAY)
    c.setLineWidth(0.5)
    c.line(cx - 220, y, cx + 220, y)

    # "This certifies that"
    y -= 18
    c.setFillColor(BLACK)
    c.setFont('Helvetica', 12)
    c.drawCentredString(cx, y, 'This certifies that')

    # ------------------------------------------------------------------
    # Name — large blue
    # ------------------------------------------------------------------
    y -= 52
    full_name = f"{first_name.upper()} {last_name.upper()}"
    c.setFillColor(BLUE)
    c.setFont('Helvetica-Bold', 46)
    c.drawCentredString(cx, y, full_name)

    # "has successfully completed"
    y -= 28
    c.setFillColor(BLACK)
    c.setFont('Helvetica', 12)
    c.drawCentredString(cx, y, 'has successfully completed')

    # Module number
    y -= 30
    c.setFont('Helvetica-Bold', 22)
    c.drawCentredString(cx, y, f'MODULE {module_id}')

    # subtitle
    y -= 20
    c.setFont('Helvetica', 11)
    c.drawCentredString(cx, y, 'of The Marshall Project Safety Training')

    # ------------------------------------------------------------------
    # Bottom row: Training Director | seal | Date
    # ------------------------------------------------------------------
    base_y = m + 36
    col_l  = pw * 0.25
    col_r  = pw * 0.75

    # Lines
    c.setStrokeColor(BLACK)
    c.setLineWidth(0.5)
    c.line(col_l - 90, base_y + 32, col_l + 90, base_y + 32)
    c.line(col_r - 90, base_y + 32, col_r + 90, base_y + 32)

    c.setFillColor(DARK_GRAY)
    c.setFont('Helvetica', 8)
    c.drawCentredString(col_l, base_y + 20, 'TRAINING DIRECTOR')
    c.drawCentredString(col_r, base_y + 20, 'DATE')

    # Date value
    c.setFillColor(BLACK)
    c.setFont('Helvetica', 11)
    c.drawCentredString(col_r, base_y + 48, _format_date(completed_at))

    # ------------------------------------------------------------------
    # Seal (circle with module text)
    # ------------------------------------------------------------------
    seal_x = cx
    seal_y = base_y + 36
    c.setFillColor(BLUE)
    c.circle(seal_x, seal_y, 38, fill=1, stroke=0)
    c.setFillColor(white)
    c.setFont('Helvetica-Bold', 9)
    c.drawCentredString(seal_x, seal_y + 14, f'MODULE {module_id}')
    c.setFont('Helvetica-Bold', 8)
    c.drawCentredString(seal_x, seal_y + 2, 'COMPLETE')

    # Checkmark (drawn as path)
    c.setStrokeColor(white)
    c.setLineWidth(2.5)
    c.setLineCap(1)
    p = c.beginPath()
    p.moveTo(seal_x - 10, seal_y - 10)
    p.lineTo(seal_x - 3,  seal_y - 17)
    p.lineTo(seal_x + 12, seal_y - 4)
    c.drawPath(p, stroke=1, fill=0)

    # ------------------------------------------------------------------
    # Footer: cert number (left) + tagline (right)
    # ------------------------------------------------------------------
    c.setFillColor(DARK_GRAY)
    c.setFont('Helvetica', 7.5)
    c.drawString(m + 14, m + 14, f'CERTIFICATE NO. {cert_number}')
    c.drawRightString(pw - m - 14, m + 14, 'A HAMMER HAAG INITIATIVE')

    c.save()
    return buf.getvalue()
