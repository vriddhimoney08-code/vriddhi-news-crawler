"""Configuration and environment variables for Vriddhi News Crawler."""
from __future__ import annotations

import os
from datetime import timedelta, timezone
from pathlib import Path

from dotenv import load_dotenv  # type: ignore

# Base paths
PACKAGE_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = PACKAGE_DIR.parent
DATA_DIR = PROJECT_ROOT / "data"
DIGESTS_DIR = DATA_DIR / "digests"
LOGS_DIR = PROJECT_ROOT / "logs"

# Ensure data and logs directories exist
DATA_DIR.mkdir(parents=True, exist_ok=True)
DIGESTS_DIR.mkdir(parents=True, exist_ok=True)
LOGS_DIR.mkdir(parents=True, exist_ok=True)

# Load environment variables
load_dotenv(PROJECT_ROOT / ".env")

# Indian Standard Time (UTC+5:30)
IST = timezone(timedelta(hours=5, minutes=30))

# Server settings
PORT = int(os.getenv("PORT", "3009"))
HOST = os.getenv("HOST", "0.0.0.0")

# Dashboard Authentication
DASHBOARD_USERNAME = os.getenv("DASHBOARD_USERNAME", "Admin").strip()
DASHBOARD_PASSWORD = os.getenv("DASHBOARD_PASSWORD", "Admin@123").strip()
SESSION_SECRET = os.getenv("SESSION_SECRET", "vriddhi_auth_secret_key_2026_99x").strip()


# Safety switches & test recipient
TEST_MODE = os.getenv("TEST_MODE", "no").strip().lower() in ("yes", "true", "1")
TEST_WHATSAPP = os.getenv("TEST_WHATSAPP", "").strip()

# Interakt WhatsApp API
INTERAKT_API_KEY = os.getenv("INTERAKT_API_KEY", "").strip()
INTERAKT_TEMPLATE = os.getenv("INTERAKT_TEMPLATE", "vriddhi_daily_digest_49").strip()
INTERAKT_MACRO_TEMPLATE = os.getenv("INTERAKT_MACRO_TEMPLATE", "vriddhi_evening_macro_01").strip()
INTERAKT_LANGUAGE = os.getenv("INTERAKT_LANGUAGE", "en").strip()
INTERAKT_DOCUMENT_HEADER = os.getenv("INTERAKT_DOCUMENT_HEADER", "yes").strip().lower() in ("yes", "true", "1")

# Storage / S3 / R2 / GCS
S3_BUCKET = os.getenv("S3_BUCKET", "").strip()
S3_ENDPOINT_URL = os.getenv("S3_ENDPOINT_URL", "").strip() or None
S3_REGION = os.getenv("S3_REGION", "ap-south-1").strip()
S3_ACCESS_KEY = os.getenv("S3_ACCESS_KEY", "").strip()
S3_SECRET_KEY = os.getenv("S3_SECRET_KEY", "").strip()
S3_LINK_DAYS = int(os.getenv("S3_LINK_DAYS", "7"))

# Crawler settings
CRAWLER_CONTACT_EMAIL = os.getenv("CRAWLER_CONTACT_EMAIL", "research@vriddhicapital.com").strip()
PER_HOST_DELAY_SEC = float(os.getenv("PER_HOST_DELAY_SEC", "1.5"))
RESPECT_ROBOTS = os.getenv("RESPECT_ROBOTS", "yes").strip().lower() in ("yes", "true", "1")
MAX_ITEM_AGE_HOURS = int(os.getenv("MAX_ITEM_AGE_HOURS", "48"))
BODY_FETCH_LIMIT = int(os.getenv("BODY_FETCH_LIMIT", "300"))
GOOGLE_NEWS_EDITIONS = [e.strip() for e in os.getenv("GOOGLE_NEWS_EDITIONS", "en-IN,hi-IN").split(",") if e.strip()]

# Database path
DB_PATH = DATA_DIR / "crawler.db"
CONTROL_PANEL_PATH = PROJECT_ROOT / "control_panel.xlsx"

# Permanent portfolio baskets
DEFAULT_FOLDERS = ["GAME", "SET", "MATCH", "JUNIOR"]

# Canonical 61-Sector Institutional Taxonomy (BSE/NSE aligned)
DEFAULT_MACRO_SECTORS: list[str] = [
    "AEROSPACE & DEFENSE",
    "AGRICULTURAL, COMMERCIAL & CONSTRUCTION VEHICLES",
    "AGRICULTURAL FOOD & OTHER PRODUCTS",
    "AUTO COMPONENTS",
    "AUTOMOBILES",
    "BANKS",
    "BEVERAGES",
    "CAPITAL MARKETS",
    "CEMENT & CEMENT PRODUCTS",
    "CHEMICALS & PETROCHEMICALS",
    "CIGARETTES & TOBACCO PRODUCTS",
    "COMMERCIAL SERVICES & SUPPLIES",
    "CONSTRUCTION",
    "CONSUMABLE FUELS",
    "CONSUMER DURABLES",
    "DIVERSIFIED",
    "DIVERSIFIED FMCG",
    "DIVERSIFIED METALS",
    "ELECTRICAL EQUIPMENT",
    "ENGINEERING SERVICES",
    "ENTERTAINMENT",
    "ETFS",
    "FERROUS METALS",
    "FERTILIZERS & AGROCHEMICALS",
    "FINANCE",
    "FINANCIAL TECHNOLOGY (FINTECH)",
    "FOOD PRODUCTS",
    "GAS",
    "HEALTHCARE EQUIPMENT & SUPPLIES",
    "HEALTHCARE SERVICES",
    "HOUSEHOLD PRODUCTS",
    "INDUSTRIAL MANUFACTURING",
    "INDUSTRIAL PRODUCTS",
    "INSURANCE",
    "IT - HARDWARE",
    "IT - SERVICES",
    "IT - SOFTWARE",
    "LEISURE SERVICES",
    "MEDIA",
    "METALS & MINERALS TRADING",
    "MINERALS & MINING",
    "NON - FERROUS METALS",
    "OIL",
    "OTHER",
    "OTHER CONSTRUCTION MATERIALS",
    "OTHER CONSUMER SERVICES",
    "OTHER SUB-SECTORS",
    "OTHER UTILITIES",
    "PAPER, FOREST & JUTE PRODUCTS",
    "PERSONAL PRODUCTS",
    "PETROLEUM PRODUCTS",
    "PHARMACEUTICALS & BIOTECHNOLOGY",
    "POWER",
    "PRINTING & PUBLICATION",
    "REALTY",
    "RETAILING",
    "TELECOM - EQUIPMENT & ACCESSORIES",
    "TELECOM - SERVICES",
    "TEXTILES & APPARELS",
    "TRANSPORT INFRASTRUCTURE",
    "TRANSPORT SERVICES",
]

