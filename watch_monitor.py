import json
import os
import smtplib
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from email.message import EmailMessage
from pathlib import Path
from typing import Optional, Tuple

import requests
from dotenv import load_dotenv


UNAVAILABLE_MARKERS = [
    "out of stock",
    "sold out",
    "currently unavailable",
    "notify me",
    "unavailable",
]

AVAILABLE_MARKERS = [
    "add to cart",
    "buy now",
    "in stock",
    "available",
]


@dataclass
class CheckResult:
    status: str  # available | unavailable | unknown
    reason: str
    title: str
    price_hint: Optional[str]


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def load_state(path: Path) -> dict:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def save_state(path: Path, data: dict) -> None:
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")


def fetch_page(url: str, timeout_seconds: int) -> str:
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/124.0.0.0 Safari/537.36"
        )
    }
    response = requests.get(url, headers=headers, timeout=timeout_seconds)
    response.raise_for_status()
    return response.text


def extract_title(html: str) -> str:
    lower = html.lower()
    start = lower.find("<title>")
    end = lower.find("</title>")
    if start != -1 and end != -1 and end > start:
        return html[start + 7 : end].strip()
    fallback = "HMT Watch"
    h1_marker = "<h1"
    h1_pos = lower.find(h1_marker)
    if h1_pos == -1:
        return fallback
    gt = lower.find(">", h1_pos)
    close = lower.find("</h1>", gt)
    if gt == -1 or close == -1:
        return fallback
    return html[gt + 1 : close].strip() or fallback


def extract_price_hint(html: str) -> Optional[str]:
    # Lightweight price extraction to include context in alerts.
    marker = "\u20b9"
    idx = html.find(marker)
    if idx == -1:
        return None
    snippet = html[idx : idx + 24]
    return " ".join(snippet.split())


def detect_stock(html: str) -> Tuple[str, str]:
    text = " ".join(html.lower().split())

    for token in UNAVAILABLE_MARKERS:
        if token in text:
            return "unavailable", f"Matched unavailable marker: '{token}'"

    has_add_to_cart = "add to cart" in text
    has_buy_now = "buy now" in text
    if has_add_to_cart or has_buy_now:
        return "available", "Detected purchase CTA (add to cart/buy now)."

    for token in AVAILABLE_MARKERS:
        if token in text:
            return "available", f"Matched available marker: '{token}'"

    return "unknown", "No known stock marker matched."


def send_email(subject: str, body: str) -> bool:
    smtp_host = os.getenv("SMTP_HOST")
    smtp_port = int(os.getenv("SMTP_PORT", "587"))
    smtp_user = os.getenv("SMTP_USERNAME")
    smtp_pass = os.getenv("SMTP_PASSWORD")
    email_from = os.getenv("ALERT_EMAIL_FROM")
    email_to = os.getenv("ALERT_EMAIL_TO")
    use_tls = os.getenv("SMTP_USE_TLS", "true").lower() == "true"

    if not all([smtp_host, smtp_user, smtp_pass, email_from, email_to]):
        return False

    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = email_from
    msg["To"] = email_to
    msg.set_content(body)

    with smtplib.SMTP(smtp_host, smtp_port, timeout=20) as server:
        if use_tls:
            server.starttls()
        server.login(smtp_user, smtp_pass)
        server.send_message(msg)
    return True


def send_twilio_sms(body: str) -> bool:
    sid = os.getenv("TWILIO_ACCOUNT_SID")
    token = os.getenv("TWILIO_AUTH_TOKEN")
    from_number = os.getenv("TWILIO_FROM_NUMBER")
    to_number = os.getenv("ALERT_SMS_TO")

    if not all([sid, token, from_number, to_number]):
        return False

    url = f"https://api.twilio.com/2010-04-01/Accounts/{sid}/Messages.json"
    payload = {
        "From": from_number,
        "To": to_number,
        "Body": body,
    }
    resp = requests.post(url, data=payload, auth=(sid, token), timeout=20)
    resp.raise_for_status()
    return True


def build_alert(result: CheckResult, url: str) -> Tuple[str, str]:
    subject = f"WATCH ALERT: {result.title} is AVAILABLE"
    body_lines = [
        "Stock update detected.",
        "",
        f"Product: {result.title}",
        f"Status: {result.status}",
        f"Reason: {result.reason}",
        f"URL: {url}",
        f"Checked at (UTC): {now_iso()}",
    ]
    if result.price_hint:
        body_lines.append(f"Price hint: {result.price_hint}")
    body = "\n".join(body_lines)
    return subject, body


def check_once() -> int:
    url = os.getenv("PRODUCT_URL", "").strip()
    if not url:
        print("ERROR: PRODUCT_URL is required.")
        return 2

    timeout_seconds = int(os.getenv("REQUEST_TIMEOUT_SECONDS", "12"))
    state_file = Path(os.getenv("STATE_FILE", ".stock_state.json"))
    alert_on_unknown = os.getenv("ALERT_ON_UNKNOWN", "false").lower() == "true"

    state = load_state(state_file)
    prev_status = state.get("last_status")

    try:
        html = fetch_page(url, timeout_seconds=timeout_seconds)
    except Exception as exc:
        print(f"ERROR: Could not fetch page: {exc}")
        return 1

    status, reason = detect_stock(html)
    title = extract_title(html)
    price_hint = extract_price_hint(html)
    result = CheckResult(status=status, reason=reason, title=title, price_hint=price_hint)

    print(f"Checked at {now_iso()}")
    print(f"Title: {title}")
    print(f"Status: {status}")
    print(f"Reason: {reason}")

    should_alert = False
    if status == "available" and prev_status != "available":
        should_alert = True
    if status == "unknown" and alert_on_unknown and prev_status != "unknown":
        should_alert = True

    if should_alert:
        subject, body = build_alert(result, url)
        delivered = []

        try:
            if send_email(subject, body):
                delivered.append("email")
        except Exception as exc:
            print(f"WARN: Email alert failed: {exc}")

        try:
            sms_text = body if len(body) <= 1500 else body[:1497] + "..."
            if send_twilio_sms(sms_text):
                delivered.append("sms")
        except Exception as exc:
            print(f"WARN: SMS alert failed: {exc}")

        if delivered:
            print(f"ALERT SENT via {', '.join(delivered)}")
        else:
            print("WARN: Stock changed but no alert channel is configured correctly.")

    state.update(
        {
            "last_status": status,
            "last_reason": reason,
            "title": title,
            "last_checked_at": now_iso(),
            "url": url,
        }
    )
    save_state(state_file, state)

    return 0


def main() -> int:
    load_dotenv()
    mode = os.getenv("MODE", "once").strip().lower()

    if mode == "once":
        return check_once()

    interval = int(os.getenv("CHECK_INTERVAL_SECONDS", "60"))
    print(f"Running in loop mode. Interval={interval}s")
    while True:
        exit_code = check_once()
        if exit_code not in (0,):
            print(f"Check returned exit code {exit_code}; retrying after {interval}s")
        time.sleep(interval)


if __name__ == "__main__":
    raise SystemExit(main())
