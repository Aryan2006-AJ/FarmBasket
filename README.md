# FarmBasket

A local marketplace where buyers order fresh produce from farmers in their own area. Each buyer and farmer belongs to one area, such as Katraj in Pune. A buyer sees and orders only from farmers who deliver to that area, picks a delivery window at checkout, and pays cash on delivery.

There are three roles that run at the same time on one database, each with its own login session: buyer, farmer and admin.

## Run it (Windows)

```cmd
cd FarmBasket
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
python app.py
```

Open http://127.0.0.1:5000. On macOS or Linux, use `source venv/bin/activate` instead of the activate line.

The first run creates the database in `instance/` and a list of starter areas for Pune and Pimpri-Chinchwad. It also creates a private secret key in `instance/secret_key` so every install has its own. No accounts or products are created for you.

### Create the admin

Admins cannot sign up on the public form. Run this once:

```cmd
python seed_admin.py
```

Log in at `/auth/login`. You land on the admin dashboard. Turn on two-factor authentication from the footer link "Two-factor".

### Try all three roles at once

Use three browser profiles (for example Chrome, Edge and Brave). Sign up a farmer and a buyer in the same area, list a product as the farmer, order it as the buyer, then follow the order from the farmer and admin screens. The farmer sees a notification the moment the order is placed.

## How areas work

- Admin, then Areas: add an area (name and city), open or close it, and open any area to see what is in stock, what is out of stock or unlisted, which categories have nothing available, and how many buyers, farmers and orders it has.
- Sign-up offers only open areas. A closed area keeps its existing users.
- A buyer can change their area from the shop. Items in the cart from other areas must be removed before checkout.
- Server rules enforce this, not just the page: a buyer cannot add or order a product from a farmer in another area, even with a direct link.

## What each role can do

**Buyer:** browse and search the shop for their area, see what is currently unavailable there, cart, wishlist, checkout with a delivery window, coupon and loyalty points, order tracking, cancel before an order is out for delivery, invoice PDF, reviews after delivery.

**Farmer:** list products with photos, stock and price, see each order with the buyer's name, phone, address and delivery window, move an order one step at a time (Packed, Out for Delivery, Delivered), see earnings and payouts, submit a verification document, view sales charts.

**Admin:** live counts of buyers, farmers, products, orders and money, area management, user activation and deactivation, farmer verification with access to the submitted document, coupons, payment and payout records, analytics, audit log, CSV exports.

## Configuration

Copy `.env.example` to `.env` and edit.

| Setting | Purpose |
|---|---|
| `FARMBASKET_SECRET_KEY` | Optional. If empty, a key is generated and stored in `instance/secret_key`. |
| `FARMBASKET_BUSINESS_NAME` | Name shown in the header, footer, legal pages and invoices. |
| `FARMBASKET_SUPPORT_EMAIL` | Contact address shown on the Privacy Policy, Terms and footer. If empty, no contact address is shown and a warning is logged at start. |
| `FARMBASKET_JURISDICTION` | Optional. Adds a governing law section to the Terms, for example "Pune, Maharashtra". |
| `FARMBASKET_HTTPS` | Set to `true` when the site is served over HTTPS. |
| `FARMBASKET_DEBUG` | Local use only. Never on a public server. |

## Design

Everything visual lives in one file, `farmbasket/static/css/app.css`. Change the colours in the `:root` block at the top and the whole site follows.

- **Palette:** deep green and burnt orange on a warm white page, with a sage green area bar. Green means healthy, orange means waiting or the main action, red means a problem, blue is a plain count. Each product category has its own tint.
- **Style:** solid fills, thin borders, rounded corners, line icons drawn as inline vector paths. No gradients and no emoji.
- **Type:** Plus Jakarta Sans, served from `static/vendor/fonts`.
- **Motion:** short (half a second at most) and plays once. Pages and product cards rise in, flash messages drop in, cards lift and buttons press on hover and click, and charts draw once. Nothing loops, nothing reacts to scrolling or the cursor, button fill colours never change, and everything is switched off for visitors whose device asks for reduced motion.
- **No photo:** a product without a photo shows its category icon on the category tint.

## Tests

```cmd
pip install -r requirements-dev.txt
pytest
```

The suite covers sign-up and login, role separation, area rules, cart and checkout, stock safety, cancellation, order status flow, payouts, verification, the API, two-factor login, rate limiting, and CSRF on every button. It also enforces the site rules: no emoji, no dashes, no gradients, no endless or scroll or cursor driven motion, no colour change on button hover, accessible contrast for every colour pair, no third-party requests, no inline scripts or styles, and no placeholder or promotional content.

## Reset

```cmd
python reset_db.py
```

Deletes all data and recreates empty tables and the starter areas. Uploaded files are kept.

## Layout

```
app.py, config.py, seed_admin.py, reset_db.py
farmbasket/
  models.py, forms.py, utils.py, scheduler.py
  repositories/   database access
  services/       orders, cart, loyalty, coupons, notifications, invoices
  routes/         auth, marketplace, buyer, farmer, admin, api, legal, ...
  templates/      one folder per role
  static/         css/app.css, js/app.js, vendor/ (Chart.js, Socket.IO client, font, all bundled)
tests/
```

The site makes no requests to other domains. The font (Plus Jakarta Sans, SIL Open Font License) and the two JavaScript libraries are served from `static/vendor`.

## Before a public launch

These are real gaps in this version. None is hidden by the interface.

1. **Payments.** Only cash on delivery exists. There is no online payment. Adding one means integrating a payment provider, which needs your account and keys. The Terms say payment is cash on delivery, so update them when this changes.
2. **Email.** Nothing is emailed. Order messages appear as notifications on the site, and the Privacy Policy says so. The email service writes to `logs/farmbasket.log` only.
3. **Legal pages.** The Privacy Policy and Terms describe what this software does. Have a lawyer review them for your business, and set the support email.
4. **Account deletion.** Users ask by email and an admin handles it by hand. There is no self-service delete.
5. **Hosting.** `python app.py` is the development server. For production use a proper server behind HTTPS and read the Flask-SocketIO deployment notes. Rate limiting keeps its counters in memory, so use a shared store such as Redis if you run more than one process.
6. **Database.** SQLite is fine for a pilot in a few areas. Move to PostgreSQL or similar and take regular backups before real volume.
7. **Payouts.** The software records what each farmer is owed and marks it paid after delivery. It does not transfer money.
8. **Delivery time.** Delivery windows are chosen by the buyer and shown to the farmer. There is no tracking or lateness handling.
