import pyodbc
import xmlrpc.client
import os
from db_config import get_connection_string

ODOO_URL = os.getenv("ODOO_URL")
ODOO_DB = os.getenv("ODOO_DB")
ODOO_USER = os.getenv("ODOO_USER")
ODOO_PASSWORD = os.getenv("ODOO_PASSWORD")

def update_price(reference: str, price: float):
    common = xmlrpc.client.ServerProxy(f"{ODOO_URL}/xmlrpc/2/common")
    uid = common.authenticate(ODOO_DB, ODOO_USER, ODOO_PASSWORD, {})
    models = xmlrpc.client.ServerProxy(f"{ODOO_URL}/xmlrpc/2/object")

    ids = models.execute_kw(
        ODOO_DB, uid, ODOO_PASSWORD,
        'product.product', 'search',
        [[['default_code', '=', reference]]]
    )

    if not ids:
        print(f"❌ Product '{reference}' not found.")
        return

    result = models.execute_kw(
        ODOO_DB, uid, ODOO_PASSWORD,
        'product.product', 'write',
        [ids, {'list_price': price}]
    )

    print(f"✔ Updated '{reference}' to {price}: {result}")

def fetch_products():
    conn = pyodbc.connect(get_connection_string())
    cursor = conn.cursor()

    # Adjust this SQL to match your schema
    cursor.execute("SELECT InternalReference, NewPrice FROM Products WHERE Updated = 1")

    products = cursor.fetchall()
    return [(row[0], row[1]) for row in products]

def main():
    products = fetch_products()

    if not products:
        print("No updates to sync.")
        return

    for reference, price in products:
        update_price(reference, price)

if __name__ == "__main__":
    main()
