from flask_wtf import FlaskForm
from flask_wtf.file import FileField, FileAllowed
from wtforms import (
    StringField, PasswordField, SelectField, TextAreaField,
    FloatField, IntegerField, BooleanField,
)
from wtforms.validators import (
    DataRequired, Email, Length, EqualTo, NumberRange, Optional, Regexp,
)

from farmbasket.models import PRODUCT_CATEGORIES

PHONE_RULE = Regexp(r"^[0-9+\- ]{7,20}$", message="Enter a valid phone number.")


class RegisterForm(FlaskForm):
    full_name = StringField("Full name", validators=[DataRequired(), Length(min=2, max=120)])
    email = StringField("Email", validators=[DataRequired(), Email(), Length(max=150)])
    phone = StringField("Phone", validators=[Optional(), PHONE_RULE])
    role = SelectField("I am a", choices=[("buyer", "Buyer"), ("farmer", "Farmer or seller")],
                       validators=[DataRequired()])
    locality_id = SelectField("Area", coerce=int, validators=[DataRequired(message="Choose your area.")])
    password = PasswordField("Password", validators=[DataRequired(), Length(min=8, max=100)])
    confirm_password = PasswordField(
        "Confirm password",
        validators=[DataRequired(), EqualTo("password", message="Passwords must match.")],
    )
    accept_terms = BooleanField(
        "I agree to the Terms and Conditions and the Privacy Policy",
        validators=[DataRequired(message="You must accept the Terms and Privacy Policy to register.")],
    )


class LoginForm(FlaskForm):
    email = StringField("Email", validators=[DataRequired(), Email()])
    password = PasswordField("Password", validators=[DataRequired()])


class ProductForm(FlaskForm):
    name = StringField("Product name", validators=[DataRequired(), Length(max=150)])
    category = SelectField("Category", choices=[(c, c) for c in PRODUCT_CATEGORIES],
                           validators=[DataRequired()])
    description = TextAreaField("Description", validators=[Optional(), Length(max=1000)])
    price = FloatField("Price (Rs.)", validators=[DataRequired(), NumberRange(min=0.01, max=1000000)])
    unit = SelectField("Unit", choices=[
        ("kg", "kg"), ("gram", "gram"), ("dozen", "dozen"), ("litre", "litre"), ("piece", "piece"),
    ], validators=[DataRequired()])
    stock = IntegerField("Quantity in stock", validators=[NumberRange(min=0, max=1000000)])
    freshness = StringField("Harvest or freshness note", validators=[Optional(), Length(max=120)])
    photo = FileField("Photo", validators=[
        Optional(), FileAllowed(["png", "jpg", "jpeg", "webp"], "Use a png, jpg, jpeg or webp image."),
    ])
    is_available = BooleanField("Listed for sale", default=True)


class CheckoutForm(FlaskForm):
    delivery_name = StringField("Name", validators=[DataRequired(), Length(max=120)])
    delivery_phone = StringField("Phone", validators=[DataRequired(), PHONE_RULE])
    delivery_address = TextAreaField("Delivery address", validators=[DataRequired(), Length(max=255)])
    delivery_city = StringField("City", validators=[DataRequired(), Length(max=100)])
    delivery_pincode = StringField("Pincode", validators=[DataRequired(), Regexp(r"^[0-9]{6}$", message="Enter a 6 digit pincode.")])
    delivery_slot = SelectField("Delivery window", validators=[DataRequired()])
    payment_method = SelectField("Payment method", choices=[("COD", "Cash on delivery")],
                                 validators=[DataRequired()])
    coupon_code = StringField("Coupon code", validators=[Optional(), Length(max=30)])
    redeem_points = IntegerField("Points to redeem", validators=[Optional(), NumberRange(min=0)], default=0)


class ReviewForm(FlaskForm):
    rating = SelectField("Rating", choices=[(str(i), f"{i} out of 5") for i in range(5, 0, -1)],
                         validators=[DataRequired()])
    comment = TextAreaField("Comment", validators=[Optional(), Length(max=500)])


class CouponForm(FlaskForm):
    code = StringField("Code", validators=[DataRequired(), Length(max=30)])
    discount_type = SelectField("Type", choices=[("percent", "Percentage"), ("flat", "Flat amount (Rs.)")],
                                validators=[DataRequired()])
    discount_value = FloatField("Discount value", validators=[DataRequired(), NumberRange(min=0.01)])
    min_order_amount = FloatField("Minimum order (Rs.)", validators=[Optional(), NumberRange(min=0)])
    max_uses = IntegerField("Maximum uses", validators=[Optional(), NumberRange(min=1)])


class KYCUploadForm(FlaskForm):
    document = FileField("Identity or farm ownership document", validators=[
        DataRequired(), FileAllowed(["png", "jpg", "jpeg", "webp", "pdf"], "Use an image or a PDF."),
    ])


class TwoFactorSetupForm(FlaskForm):
    code = StringField("6 digit code", validators=[DataRequired(), Length(min=6, max=6)])


class TwoFactorVerifyForm(FlaskForm):
    code = StringField("6 digit code", validators=[DataRequired(), Length(min=6, max=6)])


class LocalityChoiceForm(FlaskForm):
    locality_id = SelectField("Delivery area", coerce=int, validators=[DataRequired(message="Choose an area.")])


class LocalityAdminForm(FlaskForm):
    name = StringField("Area name", validators=[DataRequired(), Length(min=2, max=80)])
    city = StringField("City", validators=[DataRequired(), Length(min=2, max=80)])
