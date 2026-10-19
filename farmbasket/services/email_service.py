import logging

from flask import current_app

logger = logging.getLogger("farmbasket.email")


class EmailService:
    """Outbound email is written to the application log. No SMTP server is
    configured in this build, so nothing is delivered to a real inbox. To send
    real email, replace the body of send() with an SMTP or provider call."""

    @staticmethod
    def send(to, subject, body):
        message = f"To: {to}\nSubject: {subject}\n\n{body}"
        logger.info("Email (logged, not sent)\n%s", message)
        return message

    @staticmethod
    def order_confirmation_email(order):
        business = current_app.config.get("BUSINESS_NAME", "FarmBasket")
        body = (
            f"Hello {order.delivery_name},\n\n"
            f"Your order {order.order_number} for Rs. {order.total_amount:.2f} is confirmed.\n"
            f"Delivery window: {order.delivery_slot}\n"
            f"Payment: {order.payment_method} ({order.payment_status})\n"
            f"Deliver to: {order.delivery_address}, {order.delivery_city} {order.delivery_pincode}\n\n"
            f"{business}"
        )
        return EmailService.send(order.buyer.email, f"Order {order.order_number} confirmed", body)

    @staticmethod
    def order_status_email(order):
        business = current_app.config.get("BUSINESS_NAME", "FarmBasket")
        body = f"Hello {order.delivery_name},\n\nOrder {order.order_number} is now: {order.status}.\n\n{business}"
        return EmailService.send(order.buyer.email, f"Order {order.order_number} update", body)
