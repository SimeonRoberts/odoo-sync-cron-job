#!/usr/bin/env python3
import os, logging, pyodbc, xmlrpc.client, socket
from urllib.parse import urlparse
from datetime import datetime
# from email.mime.text import MIMEText
# import smtplib
from dotenv import load_dotenv
from xmlrpc.client import Fault

# ── one global HTTPS timeout ─────────────────────────────────────────────
socket.setdefaulttimeout(30)

load_dotenv()

def url_fix(u, scheme="https://"):
    return (u if urlparse(u).scheme else scheme + u).rstrip("/")

ODOO_URL  = url_fix(os.getenv("ODOO_URL", ""))
ODOO_DB   = os.getenv("ODOO_DB")
ODOO_USER = os.getenv("ODOO_USER")
ODOO_PWD  = os.getenv("ODOO_PASSWORD")
 
# ── pricelist mapping ─────────────────────────────────────────────
PRICELIST_MAP = {
    "PriceRetail": 14,
    "PricePref1":  16,
    "PricePref2":  17,
    "PricePref3":  19,
}
WEBSITE_PRICELIST_ID = 20 

# ── test mode ───────────────────────────────────────────────────────────
TEST_TEMPLATE_ID = int(os.getenv("TEST_TEMPLATE_ID", "0"))  # 0 = process all

# ── logging setup ───────────────────────────────────────────────────────
logging.basicConfig(
    filename="sync.log",
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)

# ── DB connection string (freetds) ───────────────────────────────────────
def conn_str():
    return (
        f"DRIVER=/opt/homebrew/opt/freetds/lib/libtdsodbc.so;"
        f"SERVER={os.getenv('DB_SERVER')},7445;"
        f"DATABASE={os.getenv('DB_DATABASE')};"
        f"UID={os.getenv('DB_USERNAME')};"
        f"PWD={os.getenv('DB_PASSWORD')};"
        "TDS_Version=8.0;"
    )

# ── fetch rows needing sync ──────────────────────────────────────────────
def fetch_products_to_sync():
    with pyodbc.connect(conn_str()) as conn:
        cur = conn.cursor()
        cur.execute("""
            SELECT OdooTemplateID, PriceRetail, PricePref1, PricePref2,
                   PricePref3, CostLatest
            FROM   TblCWS_Inventory
            WHERE  (LastOdooSync IS NULL OR LastPriceUpdate > LastOdooSync)
              AND  OdooTemplateID IS NOT NULL
        """)
        return [
            {
                "template_id": int(r[0]),
                "prices": {
                    "PriceRetail": r[1],
                    "PricePref1":  r[2],
                    "PricePref2":  r[3],
                    "PricePref3":  r[4],
                },
                "cost": r[5],
            }
            for r in cur.fetchall()
        ]

# ── single authenticated XML-RPC session ─────────────────────────────────
_uid = _models = None
def odoo():
    global _uid, _models
    if _uid is None:
        common  = xmlrpc.client.ServerProxy(f"{ODOO_URL}/xmlrpc/2/common", allow_none=True)
        _uid    = common.authenticate(ODOO_DB, ODOO_USER, ODOO_PWD, {})
        _models = xmlrpc.client.ServerProxy(f"{ODOO_URL}/xmlrpc/2/object", allow_none=True)
        if not _uid:
            raise RuntimeError("Odoo authentication failed")
    return _uid, _models

# ── helpers to write into Odoo ───────────────────────────────────────────
def update_list_price(tid, price):
    uid, m = odoo()
    m.execute_kw(ODOO_DB, uid, ODOO_PWD, "product.template", "write",
                 [[tid], {"list_price": price}])

def update_cost(tid, cost):
    uid, m = odoo()
    m.execute_kw(ODOO_DB, uid, ODOO_PWD, "product.template", "write",
                 [[tid], {"standard_price": cost}])

def update_pricelist(pricelist_id, tid, price):
    uid, m = odoo()
    domain = [["pricelist_id", "=", pricelist_id],
              ["product_tmpl_id", "=", tid],
              ["applied_on", "=", "1_product"]]
    item_ids = m.execute_kw(ODOO_DB, uid, ODOO_PWD,
                            "product.pricelist.item", "search", [domain])

    vals = {
        "compute_price": "fixed",
        "fixed_price":   price,
        "applied_on":    "1_product",
        "product_tmpl_id": tid,
        "pricelist_id":  pricelist_id,
    }

    if item_ids:
        m.execute_kw(ODOO_DB, uid, ODOO_PWD,
                     "product.pricelist.item", "write",
                     [item_ids, vals])
    else:
        m.execute_kw(ODOO_DB, uid, ODOO_PWD,
                     "product.pricelist.item", "create",
                     [vals])

def mark_synced(tid):
    with pyodbc.connect(conn_str()) as conn:
        cur = conn.cursor()
        cur.execute("UPDATE TblCWS_Inventory SET LastOdooSync=? WHERE OdooTemplateID=?",
                    (datetime.now().strftime("%Y-%m-%d %H:%M:%S"), tid))
        conn.commit()

# ── missing/zero checker ────────────────────────────────────────────────
def missing(x) -> bool:
    try:
        return x is None or float(x) == 0.0
    except (TypeError, ValueError):
        return True

# ── sync one row ────────────────────────────────────────────────────────
def sync_one(p):
    tid = p["template_id"]

    # --- fallback chain --------------------------------------------------
    retail = p["prices"]["PriceRetail"]
    pref1  = p["prices"]["PricePref1"] if not missing(p["prices"]["PricePref1"]) else retail
    pref2  = p["prices"]["PricePref2"] if not missing(p["prices"]["PricePref2"]) else pref1
    pref3  = p["prices"]["PricePref3"] if not missing(p["prices"]["PricePref3"]) else pref2

    resolved = {
        "PriceRetail": retail,
        "PricePref1":  pref1,
        "PricePref2":  pref2,
        "PricePref3":  pref3,
    }

    # --- list price & cost ----------------------------------------------
    update_list_price(tid, float(retail))
    update_cost(tid, float(p["cost"]))

    # --- pricelists ------------------------------------------------------
    for fld, val in resolved.items():
        update_pricelist(PRICELIST_MAP[fld], tid, float(val))

    # --- new Website pricelist at zero -----------------------------------
    update_pricelist(WEBSITE_PRICELIST_ID, tid, 0.0)

# ── main driver ──────────────────────────────────────────────────────────
def main():
    ok, failed = 0, []

    products = fetch_products_to_sync()
    print("📦", len(products), "products fetched for sync")
    logging.info("📦 %s products fetched for sync", len(products))

    if TEST_TEMPLATE_ID:
        products = [p for p in products if p["template_id"] == TEST_TEMPLATE_ID]
        print(f"🧪 Test mode: {len(products)} product(s) match template {TEST_TEMPLATE_ID}")
        logging.info("🧪 Test mode: %s product(s) match template %s",
                     len(products), TEST_TEMPLATE_ID)

    for i, p in enumerate(products, start=1):
        print(f"🔄 [{i}/{len(products)}] template {p['template_id']}")
        try:
            sync_one(p)
            mark_synced(p["template_id"])
            ok += 1
        except (Fault, Exception) as e:
            logging.error("❌ %s on template %s", e, p["template_id"])
            failed.append(p["template_id"])

    print(f"✅ Sync finished – {ok} succeeded, {len(failed)} failed")

    # -- optional e-mail summary -----------------------------------------
    # if EMAIL_HOST:
    #     body = (f"Finished {datetime.now():%Y-%m-%d %H:%M:%S}\n\n"
    #             f"✅ Success: {ok}\n❌ Failed : {len(failed)}\n\n"
    #             f"Failed templates: {', '.join(map(str, failed)) or 'None'}")
    #     send_email(f"Odoo price sync — {ok} ok, {len(failed)} failed", body)

if __name__ == "__main__":
    main()