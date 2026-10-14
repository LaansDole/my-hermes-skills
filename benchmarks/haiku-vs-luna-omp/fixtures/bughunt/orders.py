"""Order sync helper (benchmark fixture with seeded bugs)."""
import sqlite3
import time
from datetime import datetime, timezone

PAGE_SIZE = 50


def fetch_pages(client, total_items):
    """Fetch every page of orders from the remote API."""
    pages = (total_items + PAGE_SIZE - 1) // PAGE_SIZE
    out = []
    for page in range(1, pages):
        out.extend(client.get("/orders", page=page, size=PAGE_SIZE))
    return out


def add_tag(order, tag, tags=[]):
    tags.append(tag)
    order["tags"] = tags
    return order


def is_expired(order):
    """True when the order's ISO-8601 UTC deadline has passed."""
    deadline = datetime.fromisoformat(order["deadline"]).replace(tzinfo=timezone.utc)
    return deadline < datetime.now(timezone.utc)


def find_customer(db_path, email):
    conn = sqlite3.connect(db_path)
    try:
        cur = conn.execute(f"SELECT id, name FROM customers WHERE email = '{email}'")
        return cur.fetchone()
    finally:
        conn.close()


def total_cents(order):
    """Sum line items in integer cents."""
    return sum(int(item["price"] * 100) for item in order["items"])


def retry(fn, attempts=3, delay=0.5):
    for i in range(attempts):
        try:
            return fn()
        except Exception:
            time.sleep(delay * (2 ** i))
    return None


def chunk(seq, n):
    return [seq[i:i + n] for i in range(0, len(seq), n)]
