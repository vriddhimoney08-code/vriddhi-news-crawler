"""AI Macro & Sector Intelligence Classifier and Impact Analyzer."""
from __future__ import annotations

import json
import logging
import re
from typing import Any

import requests

from .ai import get_gemini_key, is_gemini_active

log = logging.getLogger(__name__)

# Canonical 61-Sector Institutional Taxonomy (BSE/NSE aligned)
SECTOR_KEYWORDS: dict[str, list[str]] = {
    "AEROSPACE & DEFENSE": ["defense", "defence", "dac", "drdo", "missile", "naval", "warship", "fighter jet", "hal", "bel", "mazagon", "procurement", "arms", "military", "aerospace", "isro", "satellite", "spacecraft"],
    "AGRICULTURAL, COMMERCIAL & CONSTRUCTION VEHICLES": ["tractor", "commercial vehicle", "heavy vehicle", "tipper", "excavator", "loader", "jcb", "escorts", "ashok leyland", "force motors", "swaraj", "sml isuzu", "eicher trucks"],
    "AGRICULTURAL FOOD & OTHER PRODUCTS": ["agriculture", "farmer", "crop", "msp", "wheat", "rice", "paddy", "sugar", "sugarcane", "pulses", "cotton", "procurement", "apmc", "fci", "kharif", "rabi"],
    "AUTO COMPONENTS": ["auto component", "auto ancillary", "tyres", "tires", "batteries", "automotive glass", "braking", "mrf", "ceat", "apollo tyres", "balkrishna", "samvardhana", "motherson", "bosch", "endurance", "sona blw", "spark plug"],
    "AUTOMOBILES": ["automobile", "automotive", "car", "passenger vehicle", "two-wheeler", "motorcycle", "scooter", "electric vehicle", "ev", "siam", "fada", "maruti", "tata motors", "mahindra", "bajaj auto", "hero motocorp", "tvs motor"],
    "BANKS": ["rbi", "repo rate", "monetary policy", "bank", "banking", "sbi", "hdfc bank", "icici bank", "axis bank", "pnb", "canara bank", "deposit", "credit growth", "npa", "crr", "slr", "liquidity", "psu bank", "private bank"],
    "BEVERAGES": ["beverage", "soft drinks", "packaged water", "breweries", "distilleries", "liquor", "spirits", "alcohol", "beer", "wine", "tea", "coffee", "varun beverages", "united spirits", "radico", "tata consumer"],
    "CAPITAL MARKETS": ["sebi", "f&o", "derivatives", "mutual fund", "stock exchange", "nse", "bse", "ipo", "trading", "brokerage", "investor", "clearing corp", "cdsl", "nsdl", "amfi", "angel one", "bse ltd", "mcx"],
    "CEMENT & CEMENT PRODUCTS": ["cement", "clinker", "ultratech", "ambuja", "acc", "shree cement", "dalmia", "ramco", "jk cement", "ready mix concrete", "rmc"],
    "CHEMICALS & PETROCHEMICALS": ["chemical", "chemicals", "petrochemical", "specialty chemical", "aromatics", "polymers", "olefins", "caustic soda", "aarti industries", "srf", "deepak nitrite", "tata chemicals", "navin fluorine", "fluorochemical"],
    "CIGARETTES & TOBACCO PRODUCTS": ["cigarette", "tobacco", "bidi", "cigars", "itc", "godfrey phillips", "vst industries"],
    "COMMERCIAL SERVICES & SUPPLIES": ["facility management", "security services", "staffing", "quess corp", "teamlease", "sis", "commercial supplies", "waste management"],
    "CONSTRUCTION": ["construction", "epc", "highway", "nhai", "expressway", "bridges", "tunnels", "civil engineering", "road construction", "l&t", "nbcc", "knr", "pnc infratech", "ashoka buildcon"],
    "CONSUMABLE FUELS": ["coal", "lignite", "coking coal", "thermal coal", "coal india", "singareni", "fuel supply agreement", "fsa", "coal auction"],
    "CONSUMER DURABLES": ["consumer durables", "appliances", "air conditioner", "refrigerator", "washing machine", "led tv", "fans", "havells", "voltas", "whirlpool", "blue star", "crompton", "orient electric"],
    "DIVERSIFIED": ["conglomerate", "diversified", "tata sons", "reliance industries", "adani enterprises", "larsen & toubro", "grasim", "century textiles"],
    "DIVERSIFIED FMCG": ["fmcg", "consumer goods", "packaged goods", "fast moving consumer", "hul", "hindustan unilever", "itc", "nestle", "dabur", "marico", "godrej consumer", "patanjali"],
    "DIVERSIFIED METALS": ["diversified metals", "multi-metal", "vedanta", "base metals", "alloys", "rare earth"],
    "ELECTRICAL EQUIPMENT": ["electrical equipment", "transformer", "switchgear", "cables", "wires", "polycab", "havells", "kei industries", "abb", "siemens", "bhel", "cg power", "schneider"],
    "ENGINEERING SERVICES": ["engineering services", "er&d", "r&d services", "l&t technology services", "ltts", "tata elxsi", "kpit tech", "cyient"],
    "ENTERTAINMENT": ["entertainment", "cinema", "multiplex", "box office", "film", "studios", "pvr inox", "saregama", "tips industries"],
    "ETFS": ["etf", "exchange traded fund", "index fund", "gold etf", "silver etf", "bharat 22"],
    "FERROUS METALS": ["steel", "iron ore", "sponge iron", "tmt", "hot rolled", "cold rolled", "pellets", "tata steel", "jsw steel", "sail", "jindal steel", "jindal stainless", "ferrous"],
    "FERTILIZERS & AGROCHEMICALS": ["fertilizer", "fertilizers", "urea", "dap", "mop", "npk", "pesticides", "insecticides", "fungicides", "coromandel", "chambal", "upl", "pi industries", "sharda cropchem"],
    "FINANCE": ["nbfc", "lending", "credit", "loan", "housing finance", "gold loan", "bajaj finance", "bajaj finserv", "shriram finance", "cholamandalam", "muthoot finance", "manappuram", "lt finance"],
    "FINANCIAL TECHNOLOGY (FINTECH)": ["fintech", "digital payment", "upi", "payment aggregator", "paytm", "one97", "pb fintech", "policybazaar", "razorpay", "phonepe"],
    "FOOD PRODUCTS": ["food processing", "edible oil", "flour", "dairy", "milk", "biscuits", "packaged food", "britannia", "tata consumer", "adani wilmar", "hatsun", "parag milk"],
    "GAS": ["natural gas", "lng", "cng", "png", "city gas", "gas pipeline", "gail", "petronet lng", "indraprastha gas", "igl", "mahanagar gas", "mgl", "gujarat gas"],
    "HEALTHCARE EQUIPMENT & SUPPLIES": ["medical device", "surgical equipment", "implants", "stents", "syringes", "diagnostics equipment", "poly medicure"],
    "HEALTHCARE SERVICES": ["hospital", "healthcare", "diagnostics", "pathology", "clinic", "apollo hospitals", "fortis", "max healthcare", "narayana hrudayalaya", "medanta", "dr lal pathlabs", "metropolis"],
    "HOUSEHOLD PRODUCTS": ["household", "detergent", "cleaners", "insecticide", "dishwash", "mosquito repellent", "jyothy labs"],
    "INDUSTRIAL MANUFACTURING": ["manufacturing", "capital goods", "heavy machinery", "boilers", "turbines", "pumps", "thermax", "kirloskar", "triveni turbine", "cummins india"],
    "INDUSTRIAL PRODUCTS": ["bearings", "valves", "industrial seals", "abrasives", "pipes", "timken", "skf india", "schaeffler", "grindwell norton", "astral", "supreme industries"],
    "INSURANCE": ["irdai", "insurance", "life insurance", "general insurance", "health insurance", "premium", "lic", "sbi life", "hdfc life", "icici prudential", "icici lombard", "star health", "gic re"],
    "IT - HARDWARE": ["hardware", "semiconductor", "chip", "electronics manufacturing", "ems", "pcb", "dixon technologies", "kaynes technology", "syrma sgs"],
    "IT - SERVICES": ["it services", "it consulting", "outsourcing", "tcs", "infosys", "wipro", "hcl tech", "hcltech", "tech mahindra", "l&t technology", "persistent systems", "coforge", "mphasis"],
    "IT - SOFTWARE": ["software", "saas", "enterprise software", "cloud software", "product software", "zoho", "freshworks", "tanla platforms", "rate gain"],
    "LEISURE SERVICES": ["hotel", "hospitality", "tourism", "resorts", "restaurants", "qsr", "indian hotels", "ihcl", "lemon tree", "eihed", "jubilant foodworks", "devyani", "westlife", "sapphire"],
    "MEDIA": ["media", "broadcasting", "news channel", "tv channel", "cable", "zee entertainment", "sun tv", "network18", "tv18"],
    "METALS & MINERALS TRADING": ["metal trading", "mineral trading", "commodity trading", "mmtc", "stc", "metals export"],
    "MINERALS & MINING": ["mining", "mineral", "bauxite", "manganese", "chromite", "limestone", "nmdc", "moil", "gujarat mineral", "gmdc"],
    "NON - FERROUS METALS": ["aluminum", "copper", "zinc", "lead", "hindalco", "vedanta", "nalco", "national aluminium", "hindustan zinc", "hindustan copper"],
    "OIL": ["crude", "oil", "petroleum", "brent", "wti", "upstream", "drilling", "ongc", "oil india", "crude import", "windfall tax"],
    "OTHER": ["miscellaneous", "unclassified", "general"],
    "OTHER CONSTRUCTION MATERIALS": ["tiles", "sanitaryware", "plywood", "laminates", "paints", "kajaria ceramics", "somany", "cera", "century ply", "greenply", "asian paints", "berger paints"],
    "OTHER CONSUMER SERVICES": ["consumer services", "salons", "dry cleaning", "funeral services", "wedding services"],
    "OTHER SUB-SECTORS": ["sub-sectors", "ancillary services"],
    "OTHER UTILITIES": ["water utility", "waste management", "renewable utility"],
    "PAPER, FOREST & JUTE PRODUCTS": ["paper", "pulp", "paperboard", "forest products", "jute", "packaging paper", "jk paper", "west coast paper", "andhra paper"],
    "PERSONAL PRODUCTS": ["personal care", "cosmetics", "skincare", "hair care", "shampoo", "soaps", "nykaa", "fsn e-commerce", "emami", "honasa consumer", "mamaearth", "bajaj consumer"],
    "PETROLEUM PRODUCTS": ["refining", "petrol", "diesel", "atf", "jet fuel", "lpg", "omc", "refinery", "ioc", "indian oil", "bpcl", "hpcl", "mrpl", "chennai petro"],
    "PHARMACEUTICALS & BIOTECHNOLOGY": ["pharma", "pharmaceutical", "biotech", "biotechnology", "drug", "formulation", "api", "usfda", "fda", "nppa", "sun pharma", "dr reddy", "cipla", "zydus", "lupin", "aurobindo", "torrent pharma", "mankind pharma", "alkem"],
    "POWER": ["power", "electricity", "renewable energy", "solar", "wind", "hydro", "green hydrogen", "ntpc", "power grid", "tata power", "adani power", "jsw energy", "cerc", "discom", "transmission"],
    "PRINTING & PUBLICATION": ["printing", "publishing", "newspapers", "books", "db corp", "jagran prakashan", "navneet"],
    "REALTY": ["real estate", "housing", "realty", "rera", "residential", "commercial office", "reit", "dlf", "godrej properties", "macrotech", "lodha", "oberoi realty", "prestige estates", "sobha"],
    "RETAILING": ["retail", "shopping", "department store", "fashion retail", "avenue supermarts", "dmart", "trent", "v-mart", "shopper stop", "aditya birla fashion", "abfrl"],
    "TELECOM - EQUIPMENT & ACCESSORIES": ["telecom equipment", "optical fiber", "fiber optic", "routers", "switches", "tejas networks", "sterlite tech", "hfcl", "indus towers"],
    "TELECOM - SERVICES": ["telecom", "cellular", "mobile", "broadband", "5g", "6g", "spectrum", "trai", "bharti airtel", "airtel", "reliance jio", "jio", "vodafone idea", "tata comm", "tata communications"],
    "TEXTILES & APPARELS": ["textile", "textiles", "apparel", "garments", "yarn", "fabric", "spinning", "kpr mill", "page industries", "jockey", "trident", "welspun", "vardhman", "gokaldas"],
    "TRANSPORT INFRASTRUCTURE": ["port", "ports", "airport", "airports", "highway concession", "toll", "toll plaza", "adani ports", "gmr airports", "irb infrastructure", "jnpt"],
    "TRANSPORT SERVICES": ["logistics", "shipping", "cargo", "freight", "trucking", "express parcel", "container", "concor", "delhivery", "bluedart", "blue dart", "allcargo", "vrl logistics", "interglobe aviation", "indigo", "spicejet"],
}

MACRO_PROMPT = """You are a senior macroeconomic equity strategist for Indian stock markets.
Analyze this official government or regulatory announcement:

Authority: {authority}
Title: {title}
Snippet: {snippet}

Evaluate for institutional capital markets:
1. Impacted Sectors (select 1 to 3 most relevant from the official taxonomy: AEROSPACE & DEFENSE, AGRICULTURAL, COMMERCIAL & CONSTRUCTION VEHICLES, AGRICULTURAL FOOD & OTHER PRODUCTS, AUTO COMPONENTS, AUTOMOBILES, BANKS, BEVERAGES, CAPITAL MARKETS, CEMENT & CEMENT PRODUCTS, CHEMICALS & PETROCHEMICALS, CIGARETTES & TOBACCO PRODUCTS, COMMERCIAL SERVICES & SUPPLIES, CONSTRUCTION, CONSUMABLE FUELS, CONSUMER DURABLES, DIVERSIFIED, DIVERSIFIED FMCG, DIVERSIFIED METALS, ELECTRICAL EQUIPMENT, ENGINEERING SERVICES, ENTERTAINMENT, ETFS, FERROUS METALS, FERTILIZERS & AGROCHEMICALS, FINANCE, FINANCIAL TECHNOLOGY (FINTECH), FOOD PRODUCTS, GAS, HEALTHCARE EQUIPMENT & SUPPLIES, HEALTHCARE SERVICES, HOUSEHOLD PRODUCTS, INDUSTRIAL MANUFACTURING, INDUSTRIAL PRODUCTS, INSURANCE, IT - HARDWARE, IT - SERVICES, IT - SOFTWARE, LEISURE SERVICES, MEDIA, METALS & MINERALS TRADING, MINERALS & MINING, NON - FERROUS METALS, OIL, OTHER, OTHER CONSTRUCTION MATERIALS, OTHER CONSUMER SERVICES, OTHER SUB-SECTORS, OTHER UTILITIES, PAPER, FOREST & JUTE PRODUCTS, PERSONAL PRODUCTS, PETROLEUM PRODUCTS, PHARMACEUTICALS & BIOTECHNOLOGY, POWER, PRINTING & PUBLICATION, REALTY, RETAILING, TELECOM - EQUIPMENT & ACCESSORIES, TELECOM - SERVICES, TEXTILES & APPARELS, TRANSPORT INFRASTRUCTURE, TRANSPORT SERVICES, GENERAL_MACRO).
2. Materiality Tier:
   - "Tier 1 (Market Mover)" if it shifts repo rate, GDP/CPI, broad taxation, crude policy, or multi-billion dollar cabinet sanction.
   - "Tier 2 (Sector Impact)" if it catalysts a specific industry (e.g. anti-dumping duty, defense DAC clearance, PLI sanction).
   - "Tier 3 (Routine)" if procedural or administrative.
3. Market Bias: "POSITIVE", "NEGATIVE", or "NEUTRAL".
4. Implication: 1 crisp sentence explaining which listed equities/sectors benefit or face headwinds.

Respond strictly in valid JSON format:
{{
  "sectors": ["AEROSPACE & DEFENSE", "CONSTRUCTION"],
  "impact_grade": "Tier 2 (Sector Impact)",
  "impact_bias": "POSITIVE",
  "impact_summary": "Beneficial for defense equipment manufacturers due to fresh indigenous procurement clearance."
}}
"""


_GEMINI_DISABLED = False


def classify_macro_with_ai(title: str, snippet: str, authority: str) -> dict[str, Any]:
    """Classify official macro announcement using Gemini AI or robust heuristic fallback."""
    global _GEMINI_DISABLED
    if is_gemini_active() and not _GEMINI_DISABLED:
        try:
            api_key = get_gemini_key()
            url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={api_key}"
            prompt = MACRO_PROMPT.format(authority=authority, title=title, snippet=snippet[:1000])
            payload = {
                "contents": [{"parts": [{"text": prompt}]}],
                "generationConfig": {"temperature": 0.1, "maxOutputTokens": 300, "responseMimeType": "application/json"}
            }
            resp = requests.post(url, json=payload, timeout=4)
            if resp.status_code == 200:
                raw_text = resp.json()["candidates"][0]["content"]["parts"][0]["text"].strip()
                parsed = json.loads(raw_text)
                return {
                    "sectors": parsed.get("sectors") or ["GENERAL_MACRO"],
                    "impact_grade": parsed.get("impact_grade", "Tier 2 (Sector Impact)"),
                    "impact_bias": parsed.get("impact_bias", "NEUTRAL").upper(),
                    "impact_summary": parsed.get("impact_summary", title)
                }
            elif resp.status_code == 429:
                _GEMINI_DISABLED = True
                log.info("Gemini quota reached (429). Fast heuristic classifier activated.")
        except Exception as e:
            log.debug("Gemini macro classification failed: %s. Using heuristic fallback.", e)

    # Heuristic Fallback Classifier
    return classify_macro_heuristically(title, snippet, authority)



def classify_macro_heuristically(title: str, snippet: str, authority: str) -> dict[str, Any]:
    """Institutional heuristic rule-based macro classifier."""
    combined = f"{title} {snippet} {authority}".lower()

    # 1. Match sectors
    matched_sectors: list[str] = []
    for sector, kws in SECTOR_KEYWORDS.items():
        if any(re.search(rf"\b{re.escape(k)}\b", combined) for k in kws):
            matched_sectors.append(sector)

    if not matched_sectors:
        matched_sectors = ["GENERAL_MACRO"]

    # 2. Materiality tier
    tier1_triggers = [
        r"\brepo\b", r"\bmonetary policy\b", r"\bgdp\b", r"\binflation\b", r"\bcpi\b",
        r"\bgst collection\b", r"\bunion budget\b", r"\bcabinet approves\b", r"\bcapital gains\b",
        r"\bf&o\b", r"\bderivative\b", r"\bcrude\b", r"\bopec\b", r"\binterest rate\b"
    ]
    if any(re.search(p, combined) for p in tier1_triggers):
        impact_grade = "Tier 1 (Market Mover)"
    elif len(matched_sectors) > 0 and matched_sectors != ["GENERAL_MACRO"]:
        impact_grade = "Tier 2 (Sector Impact)"
    else:
        impact_grade = "Tier 3 (Routine)"

    # 3. Market Bias
    pos_triggers = [r"\bapprov(es|ed|al)\b", r"\bsanction\b", r"\brise\b", r"\bgrowth\b", r"\bincentive\b", r"\bbonus\b", r"\bscheme\b", r"\bsurplus\b", r"\breduce(s|d)? duty\b", r"\bclear(s|ance)\b"]
    neg_triggers = [r"\bpenalty\b", r"\bcurb\b", r"\bban\b", r"\brestrict(ion|ed)?\b", r"\bdeficit\b", r"\bdecline\b", r"\bfall\b", r"\bhike duty\b", r"\btax hike\b"]

    has_pos = any(re.search(p, combined) for p in pos_triggers)
    has_neg = any(re.search(p, combined) for p in neg_triggers)

    if has_pos and not has_neg:
        impact_bias = "POSITIVE"
    elif has_neg and not has_pos:
        impact_bias = "NEGATIVE"
    else:
        impact_bias = "NEUTRAL"

    # 4. Summary
    sector_str = ", ".join(matched_sectors[:2])
    if impact_bias == "POSITIVE":
        impact_summary = f"Favorable policy catalyst for {sector_str} following official government clearance."
    elif impact_bias == "NEGATIVE":
        impact_summary = f"Regulatory caution or operational headwind for {sector_str}."
    else:
        impact_summary = f"Institutional development monitored for {sector_str}."

    return {
        "sectors": matched_sectors[:3],
        "impact_grade": impact_grade,
        "impact_bias": impact_bias,
        "impact_summary": impact_summary
    }
