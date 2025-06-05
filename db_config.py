import os
import platform
from dotenv import load_dotenv
load_dotenv()

# Load from environment variables
DB_SERVER = os.getenv("DB_SERVER")
DB_DATABASE = os.getenv("DB_DATABASE")
DB_USERNAME = os.getenv("DB_USERNAME")
DB_PASSWORD = os.getenv("DB_PASSWORD")

def get_connection_string():
    is_mac = platform.system() == "Darwin"

    driver = (
        "/opt/homebrew/opt/freetds/lib/libtdsodbc.so"
        if is_mac else
        "ODBC Driver 17 for SQL Server"
    )

    return (
        f"DRIVER={driver};"
        f"SERVER={DB_SERVER};"
        f"DATABASE={DB_DATABASE};"
        f"UID={DB_USERNAME};"
        f"PWD={DB_PASSWORD};"
    )