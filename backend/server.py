"""Serein Cafe: static web server, JSON API, SQLite persistence, and email delivery."""
from __future__ import annotations

import json
import os
import re
import smtplib
import sqlite3
import ssl
import uuid
from datetime import datetime, timezone
from email.message import EmailMessage
from http import HTTPStatus
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

BACKEND_ROOT = Path(__file__).resolve().parent
PROJECT_ROOT = BACKEND_ROOT.parent
FRONTEND_ROOT = PROJECT_ROOT / "frontend"
DB_PATH = Path(os.getenv("DATABASE_PATH", str(BACKEND_ROOT / "data" / "serein.db")))
HOST = os.getenv("HOST", "0.0.0.0")
PORT = int(os.getenv("PORT", "8000"))
EMAIL_RE = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")

MENU = {
    "house-espresso": ("House Espresso", 180), "flat-white": ("Flat White", 240),
    "seasonal-pour-over": ("Seasonal Pour Over", 280), "spanish-latte": ("Spanish Latte", 260),
    "cold-brew-tonic": ("Cold Brew Tonic", 280), "ceremonial-matcha": ("Ceremonial Matcha", 290),
    "serein-breakfast": ("Serein Breakfast", 520), "ricotta-toast": ("Ricotta Toast", 390),
    "shakshuka": ("Shakshuka", 440), "coconut-granola": ("Coconut Granola", 320),
    "croque-madame": ("Croque Madame", 480), "mushroom-rosti": ("Mushroom Rosti", 420),
    "almond-croissant": ("Almond Croissant", 250), "sea-salt-cookie": ("Sea Salt Cookie", 190),
    "morning-bun": ("Morning Bun", 220), "basque-cheesecake": ("Basque Cheesecake", 320),
    "olive-oil-cake": ("Olive Oil Cake", 280), "sourdough-loaf": ("Sourdough Loaf", 350),
    "mango-burrata": ("Mango & Burrata", 480), "peach-iced-tea": ("Peach Iced Tea", 240),
    "summer-pea-risotto": ("Summer Pea Risotto", 520), "charred-corn-tartine": ("Charred Corn Tartine", 390),
    "berry-pavlova": ("Berry Pavlova", 330), "watermelon-spritz": ("Watermelon Spritz", 240),
}

def now() -> str:
    return datetime.now(timezone.utc).isoformat()

def db() -> sqlite3.Connection:
    connection = sqlite3.connect(DB_PATH, timeout=10)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    connection.execute("PRAGMA busy_timeout = 10000")
    return connection

def init_db() -> None:
    DB_PATH.parent.mkdir(exist_ok=True)
    with db() as con:
        con.executescript("""
        CREATE TABLE IF NOT EXISTS reservations (
          id TEXT PRIMARY KEY, name TEXT NOT NULL, email TEXT NOT NULL,
          booking_date TEXT NOT NULL, booking_time TEXT NOT NULL, guests INTEGER NOT NULL,
          status TEXT NOT NULL DEFAULT 'pending', created_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS orders (
          id TEXT PRIMARY KEY, name TEXT NOT NULL, email TEXT NOT NULL, phone TEXT NOT NULL,
          fulfillment TEXT NOT NULL, notes TEXT, total INTEGER NOT NULL,
          status TEXT NOT NULL DEFAULT 'received', created_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS order_items (
          id INTEGER PRIMARY KEY AUTOINCREMENT, order_id TEXT NOT NULL REFERENCES orders(id),
          menu_id TEXT NOT NULL, item_name TEXT NOT NULL, quantity INTEGER NOT NULL,
          unit_price INTEGER NOT NULL, line_total INTEGER NOT NULL
        );
        CREATE TABLE IF NOT EXISTS subscribers (
          email TEXT PRIMARY KEY, subscribed_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS email_log (
          id INTEGER PRIMARY KEY AUTOINCREMENT, recipient TEXT NOT NULL, subject TEXT NOT NULL,
          kind TEXT NOT NULL, status TEXT NOT NULL, error TEXT, created_at TEXT NOT NULL
        );
        """)

def clean(value, limit=200) -> str:
    return str(value or "").strip()[:limit]

def send_email(recipient: str, subject: str, html: str, kind: str) -> bool:
    host = os.getenv("SMTP_HOST")
    user = os.getenv("SMTP_USER")
    password = os.getenv("SMTP_PASSWORD")
    sender = os.getenv("SMTP_FROM", user or "hello@sereincafe.com")
    status, error = "queued", None
    if host and user and password:
        try:
            message = EmailMessage()
            message["From"], message["To"], message["Subject"] = sender, recipient, subject
            message.set_content("This email is best viewed as HTML.")
            message.add_alternative(html, subtype="html")
            context = ssl.create_default_context()
            with smtplib.SMTP(host, int(os.getenv("SMTP_PORT", "587")), timeout=20) as smtp:
                smtp.starttls(context=context)
                smtp.login(user, password)
                smtp.send_message(message)
            status = "sent"
        except Exception as exc:
            status, error = "failed", str(exc)[:500]
    with db() as con:
        con.execute("INSERT INTO email_log(recipient,subject,kind,status,error,created_at) VALUES(?,?,?,?,?,?)",
                    (recipient, subject, kind, status, error, now()))
    return status == "sent"

def email_shell(title: str, content: str) -> str:
    return f"""<!doctype html><html><body style='margin:0;background:#f1ede4;font-family:Arial,sans-serif;color:#1a1713'>
    <div style='max-width:600px;margin:30px auto;background:#fff;padding:42px'>
    <p style='letter-spacing:4px;font-size:12px'>SEREIN CAFE</p><h1 style='font-family:Georgia,serif;font-weight:400'>{title}</h1>
    {content}<hr style='border:0;border-top:1px solid #ddd;margin:30px 0'><small>12 Willow Lane, Indiranagar, Bengaluru</small></div></body></html>"""

class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(FRONTEND_ROOT), **kwargs)

    def end_headers(self):
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("X-Frame-Options", "DENY")
        self.send_header("Referrer-Policy", "strict-origin-when-cross-origin")
        super().end_headers()

    def json_response(self, data, status=200):
        body = json.dumps(data).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def read_json(self):
        length = int(self.headers.get("Content-Length", "0"))
        if length <= 0 or length > 100_000:
            raise ValueError("Invalid request size")
        return json.loads(self.rfile.read(length))

    def do_GET(self):
        path = urlparse(self.path).path
        if path == "/api/health":
            return self.json_response({"status": "ok", "database": DB_PATH.name})
        if path == "/api/menu":
            return self.json_response({"items": [{"id": key, "name": value[0], "price": value[1]} for key, value in MENU.items()]})
        super().do_GET()

    def do_POST(self):
        try:
            data = self.read_json()
            path = urlparse(self.path).path
            if path == "/api/reservations": return self.reservation(data)
            if path == "/api/orders": return self.order(data)
            if path == "/api/newsletter": return self.newsletter(data)
            self.json_response({"error": "Not found"}, 404)
        except (ValueError, json.JSONDecodeError) as exc:
            self.json_response({"error": str(exc)}, 400)
        except Exception as exc:
            print(f"API error: {exc}")
            self.json_response({"error": "Something went wrong. Please try again."}, 500)

    def reservation(self, data):
        name, email = clean(data.get("name"), 80), clean(data.get("email"), 150).lower()
        date, time = clean(data.get("date"), 10), clean(data.get("time"), 20)
        try: guests = int(re.sub(r"\D", "", str(data.get("guests", 2))) or 2)
        except ValueError: guests = 2
        if not name or not EMAIL_RE.match(email) or not date or not time or not 1 <= guests <= 12:
            raise ValueError("Please provide valid reservation details")
        ref = "RSV-" + uuid.uuid4().hex[:8].upper()
        with db() as con:
            con.execute("INSERT INTO reservations VALUES(?,?,?,?,?,?,?,?)", (ref,name,email,date,time,guests,"pending",now()))
        sent = send_email(email, f"Your Serein table request · {ref}", email_shell("Your table request is in.", f"<p>Hi {name},</p><p>We have your request for <b>{guests} guests</b> on <b>{date}</b> at <b>{time}</b>.</p><p>Reference: {ref}</p>"), "reservation")
        self.json_response({"ok": True, "reference": ref, "emailSent": sent}, 201)

    def order(self, data):
        name, email = clean(data.get("name"), 80), clean(data.get("email"), 150).lower()
        phone, fulfillment = clean(data.get("phone"), 30), clean(data.get("fulfillment"), 20)
        raw_items = data.get("items") or []
        if not name or not EMAIL_RE.match(email) or len(phone) < 7 or fulfillment not in ("pickup", "delivery") or not raw_items:
            raise ValueError("Please provide valid order and customer details")
        items, total = [], 0
        for item in raw_items[:30]:
            menu_id = clean(item.get("id"), 60)
            if menu_id not in MENU: raise ValueError("One or more menu items are invalid")
            quantity = max(1, min(int(item.get("quantity", 1)), 10))
            item_name, price = MENU[menu_id]
            line_total = price * quantity
            total += line_total
            items.append((menu_id, item_name, quantity, price, line_total))
        ref = "ORD-" + uuid.uuid4().hex[:8].upper()
        with db() as con:
            con.execute("INSERT INTO orders VALUES(?,?,?,?,?,?,?,?,?)", (ref,name,email,phone,fulfillment,clean(data.get("notes"),500),total,"received",now()))
            con.executemany("INSERT INTO order_items(order_id,menu_id,item_name,quantity,unit_price,line_total) VALUES(?,?,?,?,?,?)", [(ref,*item) for item in items])
        rows = "".join(f"<tr><td style='padding:8px 0'>{qty}× {item_name}</td><td style='text-align:right'>₹{line}</td></tr>" for _,item_name,qty,_,line in items)
        sent = send_email(email, f"We received your Serein order · {ref}", email_shell("Your order is brewing.", f"<p>Hi {name},</p><p>We’ve received your {fulfillment} order.</p><table style='width:100%'>{rows}<tr><td style='padding-top:12px'><b>Total</b></td><td style='text-align:right;padding-top:12px'><b>₹{total}</b></td></tr></table><p>Reference: {ref}</p>"), "order")
        self.json_response({"ok": True, "reference": ref, "total": total, "emailSent": sent}, 201)

    def newsletter(self, data):
        email = clean(data.get("email"), 150).lower()
        if not EMAIL_RE.match(email): raise ValueError("Please enter a valid email")
        with db() as con:
            con.execute("INSERT OR IGNORE INTO subscribers VALUES(?,?)", (email, now()))
        self.json_response({"ok": True}, 201)

if __name__ == "__main__":
    init_db()
    print(f"Serein is running at http://{HOST}:{PORT}")
    print(f"Database: {DB_PATH}")
    ThreadingHTTPServer((HOST, PORT), Handler).serve_forever()
