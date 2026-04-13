# HMT Watch Stock Monitor

Fast stock checker for this product:
- https://www.hmtwatches.store/product/bc27db38-fcc7-44bc-8c51-325c43ef58bd

It checks the page text for stock markers and alerts you when status changes to **available**.

## Features

- Quick check (single HTTP request)
- Detects `out of stock` and purchase CTAs like `add to cart` / `buy now`
- Sends alert via SMTP email and/or Twilio SMS
- Persists status in `.stock_state.json` to avoid repeated alerts
- Easy deployment via GitHub Actions schedule

## 1) Local Setup (2 minutes)

1. Install Python 3.10+
2. In this folder, install dependencies:

```bash
pip install -r requirements.txt
```

3. Copy `.env.example` to `.env` and fill your credentials.
4. Run one check:

```bash
python watch_monitor.py
```

5. Optional continuous mode:

```bash
# In .env set MODE=loop
python watch_monitor.py
```

## 2) Email/SMS Config

### Email (SMTP)

Set these in `.env`:
- `SMTP_HOST`
- `SMTP_PORT`
- `SMTP_USERNAME`
- `SMTP_PASSWORD`
- `ALERT_EMAIL_FROM`
- `ALERT_EMAIL_TO`

For Gmail, use an App Password (not normal password).

### SMS (Twilio)

Set these in `.env`:
- `TWILIO_ACCOUNT_SID`
- `TWILIO_AUTH_TOKEN`
- `TWILIO_FROM_NUMBER`
- `ALERT_SMS_TO`

## 3) Easy Deploy with GitHub Actions

Create these GitHub repository secrets:
- `PRODUCT_URL`
- `SMTP_HOST`
- `SMTP_PORT`
- `SMTP_USERNAME`
- `SMTP_PASSWORD`
- `ALERT_EMAIL_FROM`
- `ALERT_EMAIL_TO`
- `SMTP_USE_TLS`
- `TWILIO_ACCOUNT_SID` (optional)
- `TWILIO_AUTH_TOKEN` (optional)
- `TWILIO_FROM_NUMBER` (optional)
- `ALERT_SMS_TO` (optional)

Then push this project to GitHub. The workflow in `.github/workflows/stock-check.yml` runs every 5 minutes.

## Detection Logic

- If page contains `out of stock`, `sold out`, etc. -> `unavailable`
- Else if page contains `add to cart` or `buy now` -> `available`
- Else -> `unknown`

Current page snapshot includes `Out of Stock`, so it should currently show `unavailable`.

## Notes

- Respect website terms and avoid very short polling intervals.
- If the site changes wording, update marker lists in `watch_monitor.py`.
