import io
import base64

import qrcode
from flask import current_app
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.lib import colors
from reportlab.pdfgen import canvas
from reportlab.lib.utils import ImageReader


def _qr_png(payload):
    img = qrcode.make(payload)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    buf.seek(0)
    return buf


class InvoiceService:

    @staticmethod
    def generate_order_qr_base64(order):
        """QR code that encodes the order reference, for the buyer to show on delivery."""
        payload = f"Order {order.order_number} | Rs. {order.total_amount:.2f} | {order.payment_method}"
        return base64.b64encode(_qr_png(payload).read()).decode("utf-8")

    @staticmethod
    def generate_invoice_pdf(order):
        business = current_app.config.get("BUSINESS_NAME", "FarmBasket")
        buf = io.BytesIO()
        c = canvas.Canvas(buf, pagesize=A4)
        width, height = A4
        ink = colors.HexColor("#1c1f1d")
        muted = colors.HexColor("#5b625e")
        line = colors.HexColor("#d9ddd9")

        y = height - 22 * mm
        c.setFillColor(ink)
        c.setFont("Helvetica-Bold", 18)
        c.drawString(20 * mm, y, business)
        c.setFont("Helvetica", 10)
        c.setFillColor(muted)
        c.drawRightString(width - 20 * mm, y, f"Invoice {order.order_number}")
        y -= 5 * mm
        c.line(20 * mm, y, width - 20 * mm, y)
        c.setStrokeColor(line)

        y -= 9 * mm
        c.setFillColor(ink)
        c.setFont("Helvetica", 10)
        rows = [
            ("Date", order.created_at.strftime("%d %b %Y, %I:%M %p")),
            ("Order status", order.status),
            ("Payment", f"{order.payment_method}, {order.payment_status}"),
            ("Delivery window", order.delivery_slot or "Not set"),
        ]
        for label, value in rows:
            c.setFillColor(muted)
            c.drawString(20 * mm, y, label)
            c.setFillColor(ink)
            c.drawString(55 * mm, y, value)
            y -= 5.5 * mm

        y -= 3 * mm
        c.setFont("Helvetica-Bold", 10)
        c.drawString(20 * mm, y, "Deliver to")
        y -= 5.5 * mm
        c.setFont("Helvetica", 10)
        c.drawString(20 * mm, y, f"{order.delivery_name}, {order.delivery_phone}")
        y -= 5 * mm
        c.drawString(20 * mm, y, f"{order.delivery_address}, {order.delivery_city} {order.delivery_pincode}")

        y -= 11 * mm
        c.setFont("Helvetica-Bold", 10)
        c.drawString(20 * mm, y, "Item")
        c.drawString(100 * mm, y, "Price")
        c.drawString(128 * mm, y, "Qty")
        c.drawRightString(width - 20 * mm, y, "Amount")
        y -= 3 * mm
        c.line(20 * mm, y, width - 20 * mm, y)
        y -= 6 * mm

        c.setFont("Helvetica", 10)
        for item in order.items:
            if y < 45 * mm:
                c.showPage()
                y = height - 25 * mm
                c.setFont("Helvetica", 10)
            c.drawString(20 * mm, y, item.product_name[:42])
            c.drawString(100 * mm, y, f"Rs. {item.price:.2f}")
            c.drawString(128 * mm, y, str(item.quantity))
            c.drawRightString(width - 20 * mm, y, f"Rs. {item.subtotal:.2f}")
            y -= 6 * mm

        y -= 2 * mm
        c.line(20 * mm, y, width - 20 * mm, y)
        y -= 6 * mm
        if order.discount_amount:
            c.drawRightString(width - 20 * mm, y, f"Discount: -Rs. {order.discount_amount:.2f}")
            y -= 6 * mm
        c.setFont("Helvetica-Bold", 12)
        c.drawRightString(width - 20 * mm, y, f"Total: Rs. {order.total_amount:.2f}")

        c.drawImage(ImageReader(_qr_png(f"{order.order_number}")), 20 * mm, 18 * mm, width=24 * mm, height=24 * mm)
        c.setFont("Helvetica", 8)
        c.setFillColor(muted)
        c.drawString(20 * mm, 14 * mm, "Order reference")
        c.drawString(20 * mm, 10 * mm, "Payment is cash on delivery.")

        c.showPage()
        c.save()
        buf.seek(0)
        return buf.read()
