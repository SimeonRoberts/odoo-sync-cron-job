import os, csv, xmlrpc.client
from dotenv import load_dotenv
from urllib.parse import urlparse

# ── config ─────────────────────────────────────────────────────────────
load_dotenv()                                                   # .env file
def _url(url, scheme="https://"):                               # make sure http(s)://
    return (url if urlparse(url).scheme else scheme + url).rstrip("/")

ODOO_URL  = _url(os.getenv("ODOO_URL", ""))
ODOO_DB   = os.getenv("ODOO_DB")
ODOO_USER = os.getenv("ODOO_USER")
ODOO_PWD  = os.getenv("ODOO_PASSWORD")

FIELDS    = ["id", "name", "default_code", "barcode"]          # pick the fields you want
LIMIT     = 1000                                               # fetch in batches

# ── connect ────────────────────────────────────────────────────────────
common  = xmlrpc.client.ServerProxy(f"{ODOO_URL}/xmlrpc/2/common")
uid     = common.authenticate(ODOO_DB, ODOO_USER, ODOO_PWD, {})
models  = xmlrpc.client.ServerProxy(f"{ODOO_URL}/xmlrpc/2/object")

# ── fetch all templates ───────────────────────────────────────────────
offset  = 0
rows    = []

while True:
    batch = models.execute_kw(
        ODOO_DB, uid, ODOO_PWD,
        "product.template", "search_read",
        [[]],                               # empty domain = all products
        {"fields": FIELDS, "limit": LIMIT, "offset": offset},
    )
    if not batch:
        break
    rows.extend(batch)
    offset += LIMIT

print(f"Fetched {len(rows)} templates")

# ── write to CSV so you can open in Excel / Sheets ─────────────────────
with open("odoo_templates.csv", "w", newline="", encoding="utf-8") as fh:
    writer = csv.DictWriter(fh, fieldnames=FIELDS)
    writer.writeheader()
    writer.writerows(rows)
