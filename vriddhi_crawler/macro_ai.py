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
    "AEROSPACE & DEFENSE": ["defense", "defence", "dac", "drdo", "missile", "naval", "warship", "fighter jet", "hal", "bel", "mazagon", "procurement", "arms", "military", "aerospace", "isro", "satellite", "spacecraft", "defense corridor", "idex", "defense export"],
    "AGRICULTURAL, COMMERCIAL & CONSTRUCTION VEHICLES": ["tractor", "commercial vehicle", "heavy vehicle", "tipper", "excavator", "loader", "jcb", "escorts", "ashok leyland", "force motors", "swaraj", "sml isuzu", "eicher trucks", "cv sales", "medium and heavy commercial"],
    "AGRICULTURAL FOOD & OTHER PRODUCTS": ["agriculture", "farmer", "crop", "msp", "wheat", "rice", "paddy", "sugar", "sugarcane", "pulses", "cotton", "procurement", "apmc", "fci", "kharif", "rabi", "agri export", "kisan credit", "pm kisan"],
    "AUTO COMPONENTS": ["auto component", "auto ancillary", "tyres", "tires", "batteries", "automotive glass", "braking", "mrf", "ceat", "apollo tyres", "balkrishna", "samvardhana", "motherson", "bosch", "endurance", "sona blw", "spark plug", "traction motor", "battery storage", "bess", "battery swapping", "component manufacturing", "wheel rims", "transmission parts"],
    "AUTOMOBILES": ["automobile", "automotive", "car", "passenger vehicle", "two-wheeler", "motorcycle", "scooter", "electric vehicle", "ev", "siam", "fada", "maruti", "tata motors", "mahindra", "bajaj auto", "hero motocorp", "tvs motor", "pm e-drive", "fame scheme", "fame subsidy", "fame policy", "fame-ii", "fame-iii", "pli auto", "auto sales", "electric mobility", "ev policy", "cafe norms", "scrappage policy", "vehicle scrappage", "heavy industries", "e-bus", "charging station", "hybrid vehicle"],
    "BANKS": ["rbi", "repo rate", "monetary policy", "bank", "banking", "sbi", "hdfc bank", "icici bank", "axis bank", "pnb", "canara bank", "deposit", "credit growth", "npa", "crr", "slr", "liquidity", "psu bank", "private bank", "priority sector lending", "capital adequacy", "prompt corrective action"],
    "BEVERAGES": ["beverage", "soft drinks", "packaged water", "breweries", "distilleries", "liquor", "spirits", "alcohol", "beer", "wine", "tea", "coffee", "varun beverages", "united spirits", "radico", "tata consumer", "ethanol blending", "grain distillery"],
    "CAPITAL MARKETS": ["sebi", "f&o", "derivatives", "mutual fund", "stock exchange", "nse", "bse", "ipo", "trading", "brokerage", "investor", "clearing corp", "cdsl", "nsdl", "amfi", "angel one", "bse ltd", "mcx", "settlement cycle", "insider trading", "algo trading", "fpi", "foreign portfolio"],
    "CEMENT & CEMENT PRODUCTS": ["cement", "clinker", "ultratech", "ambuja", "acc", "shree cement", "dalmia", "ramco", "jk cement", "ready mix concrete", "rmc", "anti-dumping duty on cement", "limestone lease", "slag cement", "cement capacity", "bis standard for cement", "cement dispatches", "blended cement"],
    "CHEMICALS & PETROCHEMICALS": ["chemical", "chemicals", "petrochemical", "specialty chemical", "aromatics", "polymers", "olefins", "caustic soda", "aarti industries", "srf", "deepak nitrite", "tata chemicals", "navin fluorine", "fluorochemical", "soda ash", "chlor-alkali", "feedstock", "inversion duty", "anti-dumping duty", "bis certification for chemicals", "pesticides", "pcpirl"],
    "CIGARETTES & TOBACCO PRODUCTS": ["cigarette", "tobacco", "bidi", "cigars", "itc", "godfrey phillips", "vst industries", "tobacco board", "sin tax"],
    "COMMERCIAL SERVICES & SUPPLIES": ["facility management", "security services", "staffing", "quess corp", "teamlease", "sis", "commercial supplies", "waste management"],
    "CONSTRUCTION": ["construction", "epc", "highway", "nhai", "expressway", "bridges", "tunnels", "civil engineering", "road construction", "l&t", "nbcc", "knr", "pnc infratech", "ashoka buildcon", "bharatmala", "pm gatishakti", "paving"],
    "CONSUMABLE FUELS": ["coal", "lignite", "coking coal", "thermal coal", "coal india", "singareni", "fuel supply agreement", "fsa", "coal auction", "commercial coal", "coal block", "coal linkage", "shakti scheme", "ministry of coal"],
    "CONSUMER DURABLES": ["consumer durables", "appliances", "air conditioner", "refrigerator", "washing machine", "led tv", "fans", "havells", "voltas", "whirlpool", "blue star", "crompton", "orient electric", "white goods", "pli white goods", "bee star rating", "energy efficiency star"],
    "DIVERSIFIED": ["conglomerate", "diversified", "tata sons", "reliance industries", "adani enterprises", "larsen & toubro", "grasim", "century textiles"],
    "DIVERSIFIED FMCG": ["fmcg", "consumer goods", "packaged goods", "fast moving consumer", "hul", "hindustan unilever", "itc", "nestle", "dabur", "marico", "godrej consumer", "patanjali"],
    "DIVERSIFIED METALS": ["diversified metals", "multi-metal", "vedanta", "base metals", "alloys", "rare earth"],
    "ELECTRICAL EQUIPMENT": ["electrical equipment", "transformer", "switchgear", "cables", "wires", "polycab", "havells", "kei industries", "abb", "siemens", "bhel", "cg power", "schneider", "smart grid", "power transmission equipment"],
    "ENGINEERING SERVICES": ["engineering services", "er&d", "r&d services", "l&t technology services", "ltts", "tata elxsi", "kpit tech", "cyient"],
    "ENTERTAINMENT": ["entertainment", "cinema", "multiplex", "box office", "film", "studios", "pvr inox", "saregama", "tips industries", "ott regulation", "broadcasting services"],
    "ETFS": ["etf", "exchange traded fund", "index fund", "gold etf", "silver etf", "bharat 22"],
    "FERROUS METALS": ["steel", "iron ore", "sponge iron", "tmt", "hot rolled", "cold rolled", "pellets", "tata steel", "jsw steel", "sail", "jindal steel", "jindal stainless", "ferrous", "steel import duty", "safeguard duty", "melt and pour", "ministry of steel", "coking coal import"],
    "FERTILIZERS & AGROCHEMICALS": ["fertilizer", "fertilizers", "urea", "dap", "mop", "npk", "pesticides", "insecticides", "fungicides", "coromandel", "chambal", "upl", "pi industries", "sharda cropchem", "nutrient based subsidy", "nbs", "fertilizer subsidy", "nano urea", "neem coated", "ssp"],
    "FINANCE": ["nbfc", "lending", "credit", "loan", "housing finance", "gold loan", "bajaj finance", "bajaj finserv", "shriram finance", "cholamandalam", "muthoot finance", "manappuram", "lt finance", "microfinance", "mfi", "debt recovery"],
    "FINANCIAL TECHNOLOGY (FINTECH)": ["fintech", "digital payment", "upi", "payment aggregator", "paytm", "one97", "pb fintech", "policybazaar", "razorpay", "phonepe", "central bank digital currency", "cbdc", "digital lending"],
    "FOOD PRODUCTS": ["food processing", "edible oil", "flour", "dairy", "milk", "biscuits", "packaged food", "britannia", "tata consumer", "adani wilmar", "hatsun", "parag milk", "pmksy", "mega food park", "cold chain"],
    "GAS": ["natural gas", "lng", "cng", "png", "city gas", "gas pipeline", "gail", "petronet lng", "indraprastha gas", "igl", "mahanagar gas", "mgl", "gujarat gas", "apms gas", "pngrb"],
    "HEALTHCARE EQUIPMENT & SUPPLIES": ["medical device", "surgical equipment", "implants", "stents", "syringes", "diagnostics equipment", "poly medicure", "medical device pli", "medical parks"],
    "HEALTHCARE SERVICES": ["hospital", "healthcare", "diagnostics", "pathology", "clinic", "apollo hospitals", "fortis", "max healthcare", "narayana hrudayalaya", "medanta", "dr lal pathlabs", "metropolis", "ayushman bharat"],
    "HOUSEHOLD PRODUCTS": ["household", "detergent", "cleaners", "insecticide", "dishwash", "mosquito repellent", "jyothy labs"],
    "INDUSTRIAL MANUFACTURING": ["manufacturing", "capital goods", "heavy machinery", "boilers", "turbines", "pumps", "thermax", "kirloskar", "triveni turbine", "cummins india", "industrial corridor", "make in india", "dpiit"],
    "INDUSTRIAL PRODUCTS": ["bearings", "valves", "industrial seals", "abrasives", "pipes", "timken", "skf india", "schaeffler", "grindwell norton", "astral", "supreme industries"],
    "INSURANCE": ["irdai", "insurance", "life insurance", "general insurance", "health insurance", "premium", "lic", "sbi life", "hdfc life", "icici prudential", "icici lombard", "star health", "gic re", "solvency margin"],
    "IT - HARDWARE": ["hardware", "semiconductor", "chip", "electronics manufacturing", "ems", "pcb", "dixon technologies", "kaynes technology", "syrma sgs", "fab", "fabrication", "atmp", "osat", "meity", "ism", "india semiconductor mission", "spex", "it hardware pli", "laptop import"],
    "IT - SERVICES": ["it services", "it consulting", "outsourcing", "tcs", "infosys", "wipro", "hcl tech", "hcltech", "tech mahindra", "l&t technology", "persistent systems", "coforge", "mphasis", "h1b visa", "offshore revenue"],
    "IT - SOFTWARE": ["software", "saas", "enterprise software", "cloud software", "product software", "zoho", "freshworks", "tanla platforms", "rate gain", "data protection", "dpdp", "digital india", "indiaai", "ai mission", "cybersecurity directive"],
    "LEISURE SERVICES": ["hotel", "hospitality", "tourism", "resorts", "restaurants", "qsr", "indian hotels", "ihcl", "lemon tree", "eihed", "jubilant foodworks", "devyani", "westlife", "sapphire", "swadesh darshan"],
    "MEDIA": ["media", "broadcasting", "news channel", "tv channel", "cable", "zee entertainment", "sun tv", "network18", "tv18", "prasar bharati", "mib"],
    "METALS & MINERALS TRADING": ["metal trading", "mineral trading", "commodity trading", "mmtc", "stc", "metals export"],
    "MINERALS & MINING": ["mining", "mineral", "bauxite", "manganese", "chromite", "limestone", "nmdc", "moil", "gujarat mineral", "gmdc", "critical minerals", "mineral auction", "lithium", "rare earth", "mddr", "ministry of mines", "royalty on minerals"],
    "NON - FERROUS METALS": ["aluminum", "copper", "zinc", "lead", "hindalco", "vedanta", "nalco", "national aluminium", "hindustan zinc", "hindustan copper"],
    "OIL": ["crude", "oil", "petroleum", "brent", "wti", "upstream", "drilling", "ongc", "oil india", "crude import", "windfall tax", "opec", "strategic petroleum reserves"],
    "OTHER": ["miscellaneous", "unclassified", "general"],
    "OTHER CONSTRUCTION MATERIALS": ["tiles", "sanitaryware", "plywood", "laminates", "paints", "kajaria ceramics", "somany", "cera", "century ply", "greenply", "asian paints", "berger paints"],
    "OTHER CONSUMER SERVICES": ["consumer services", "salons", "dry cleaning", "funeral services", "wedding services"],
    "OTHER SUB-SECTORS": ["sub-sectors", "ancillary services"],
    "OTHER UTILITIES": ["water utility", "waste management", "renewable utility", "jal jeevan mission", "desalination"],
    "PAPER, FOREST & JUTE PRODUCTS": ["paper", "pulp", "paperboard", "forest products", "jute", "packaging paper", "jk paper", "west coast paper", "andhra paper", "jute packaging", "jute msp"],
    "PERSONAL PRODUCTS": ["personal care", "cosmetics", "skincare", "hair care", "shampoo", "soaps", "nykaa", "fsn e-commerce", "emami", "honasa consumer", "mamaearth", "bajaj consumer"],
    "PETROLEUM PRODUCTS": ["refining", "petrol", "diesel", "atf", "jet fuel", "lpg", "omc", "refinery", "ioc", "indian oil", "bpcl", "hpcl", "mrpl", "chennai petro", "fuel retail", "under-recovery"],
    "PHARMACEUTICALS & BIOTECHNOLOGY": ["pharma", "pharmaceutical", "biotech", "biotechnology", "drug", "formulation", "api", "usfda", "fda", "nppa", "sun pharma", "dr reddy", "cipla", "zydus", "lupin", "aurobindo", "torrent pharma", "mankind pharma", "alkem", "pli pharma", "bulk drug park"],
    "POWER": ["power", "electricity", "renewable energy", "solar", "wind", "hydro", "green hydrogen", "ntpc", "power grid", "tata power", "adani power", "jsw energy", "cerc", "discom", "transmission", "bess viability gap", "tariff policy", "national grid"],
    "PRINTING & PUBLICATION": ["printing", "publishing", "newspapers", "books", "db corp", "jagran prakashan", "navneet"],
    "REALTY": ["real estate", "housing", "realty", "rera", "residential", "commercial office", "reit", "dlf", "godrej properties", "macrotech", "lodha", "oberoi realty", "prestige estates", "sobha", "pmay", "affordable housing"],
    "RETAILING": ["retail", "shopping", "department store", "fashion retail", "avenue supermarts", "dmart", "trent", "v-mart", "shopper stop", "aditya birla fashion", "abfrl", "e-commerce policy", "fdi in retail"],
    "TELECOM - EQUIPMENT & ACCESSORIES": ["telecom equipment", "optical fiber", "fiber optic", "routers", "switches", "tejas networks", "sterlite tech", "hfcl", "indus towers", "bharatnet", "telecom pli"],
    "TELECOM - SERVICES": ["telecom", "cellular", "mobile", "broadband", "5g", "6g", "spectrum", "trai", "bharti airtel", "airtel", "reliance jio", "jio", "vodafone idea", "tata comm", "tata communications", "agr dues", "telecom bill"],
    "TEXTILES & APPARELS": ["textile", "textiles", "apparel", "garments", "yarn", "fabric", "spinning", "kpr mill", "page industries", "jockey", "trident", "welspun", "vardhman", "gokaldas", "pm mitra", "textile pli"],
    "TRANSPORT INFRASTRUCTURE": ["port", "ports", "airport", "airports", "highway concession", "toll", "toll plaza", "adani ports", "gmr airports", "irb infrastructure", "jnpt", "sagarmala", "inland waterways"],
    "TRANSPORT SERVICES": ["logistics", "shipping", "cargo", "freight", "trucking", "express parcel", "container", "concor", "delhivery", "bluedart", "blue dart", "allcargo", "vrl logistics", "interglobe aviation", "indigo", "spicejet", "national logistics policy"],
}

MINISTRY_TO_SECTORS: dict[str, list[str]] = {
    "Ministry of Heavy Industries": ["AUTOMOBILES", "AUTO COMPONENTS"],
    "Ministry of Road Transport (MoRTH)": ["CONSTRUCTION", "TRANSPORT INFRASTRUCTURE"],
    "Ministry of Power & MNRE": ["POWER"],
    "Ministry of Petroleum & Natural Gas": ["OIL", "GAS", "PETROLEUM PRODUCTS"],
    "Ministry of Chemicals & Fertilizers": ["CHEMICALS & PETROCHEMICALS", "FERTILIZERS & AGROCHEMICALS"],
    "Ministry of Steel": ["FERROUS METALS"],
    "Ministry of Mines": ["MINERALS & MINING", "NON - FERROUS METALS"],
    "Ministry of Electronics & IT (MeitY)": ["IT - HARDWARE", "IT - SOFTWARE"],
    "Ministry of Railways": ["TRANSPORT INFRASTRUCTURE", "TRANSPORT SERVICES"],
    "Ministry of Defense": ["AEROSPACE & DEFENSE"],
    "Reserve Bank of India (RBI)": ["BANKS", "FINANCE"],
    "Securities & Exchange Board (SEBI)": ["CAPITAL MARKETS"],
    "Ministry of Civil Aviation": ["TRANSPORT SERVICES"],
    "Ministry of Coal": ["CONSUMABLE FUELS"],
    "Ministry of Housing & Urban Affairs": ["REALTY", "CONSTRUCTION"],
    "Ministry of Agriculture": ["AGRICULTURAL FOOD & OTHER PRODUCTS"],
    "Ministry of Commerce & Industry": ["INDUSTRIAL MANUFACTURING", "CAPITAL MARKETS"],
    "Ministry of Consumer Affairs & Food": ["FOOD PRODUCTS", "DIVERSIFIED FMCG"],
    "Ministry of Textiles": ["TEXTILES & APPARELS"],
    "Ministry of Communications (DoT)": ["TELECOM - SERVICES", "TELECOM - EQUIPMENT & ACCESSORIES"],
    "MoSPI (National Statistics)": ["GENERAL_MACRO"]
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
            from .db import get_ai_prompt
            cfg = get_ai_prompt("macro_directive") or {}
            template = cfg.get("prompt_text") or MACRO_PROMPT
            model_name = cfg.get("model") or "gemini-1.5-flash"
            temperature = float(cfg.get("temperature", 0.1))
            max_tokens = int(cfg.get("max_tokens", 300))

            url = f"https://generativelanguage.googleapis.com/v1beta/models/{model_name}:generateContent?key={api_key}"
            prompt = template
            for tag, val in [
                ("{authority}", authority),
                ("{title}", title),
                ("{snippet}", snippet[:1000])
            ]:
                prompt = prompt.replace(tag, val)
            payload = {
                "contents": [{"parts": [{"text": prompt}]}],
                "generationConfig": {"temperature": temperature, "maxOutputTokens": max_tokens, "responseMimeType": "application/json"}
            }
            resp = requests.post(url, json=payload, timeout=4)
            if resp.status_code == 200:
                raw_text = resp.json()["candidates"][0]["content"]["parts"][0]["text"].strip()
                parsed = json.loads(raw_text)
                secs = parsed.get("sectors") or []
                if not secs:
                    h_res = classify_macro_heuristically(title, snippet, authority)
                    secs = h_res.get("sectors") or ["GENERAL_MACRO"]
                return {
                    "is_material": True,
                    "sectors": secs,
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



NON_ECONOMIC_NOISE = [
    r"\bgreets\b", r"\bgreetings\b", r"\bcondol(es|ence)\b", r"\bhomage\b", r"\btribute\b",
    r"\bbirth anniversary\b", r"\bdeath anniversary\b", r"\bfestival\b", r"\byoga\b",
    r"\bfit india\b", r"\bsports award\b", r"\bswachh\b", r"\bflorence nightingale\b",
    r"\bconvocation\b", r"\bfelicitate(s|d)?\b", r"\bpujas?\b", r"\bpariksha pe charcha\b",
    r"\bmann ki baat\b", r"\bvocal for local exhibition\b", r"\bcultural festival\b",
    r"\bbook launch\b", r"\binaugurates exhibition\b", r"\bcommemorat(es|ion)\b",
    r"\bnational youth festival\b", r"\bmedal winners?\b", r"\bsangam\b", r"\bkala utsav\b",
    r"\bsangeet natak\b", r"\bsahitya akademi\b",
    # Celebrity gossip, personal property leases, residential retail
    r"\bhall of fame\b", r"\blease(s|d)?\s+out\b", r"\bsq\s*ft\b", r"\bsqft\b", r"\bsquare feet\b",
    r"\bbuys\s+(flat|apartment|bungalow|villa|house|penthouse)\b",
    r"\bsells\s+(flat|apartment|bungalow|villa|house|penthouse)\b",
    r"\brents\s+(flat|apartment|bungalow|villa|house|space)\b",
    r"\bactor\b", r"\bactress\b", r"\bbollywood\b", r"\bcricket(er)?\b",
    # Exams, admit cards, routine recruitment
    r"\brecruitment results?\b", r"\bexam results?\b", r"\badmit card\b", r"\bhall ticket\b",
    r"\banswer key\b", r"\bcutoff marks?\b", r"\bselection list\b", r"\binterview schedule\b",
    # Routine shlokas / ceremonial quotes
    r"\bsubhashitam\b", r"\bsanskrit\b", r"\bshloka\b", r"\bplot subdivision\b",
]

ECONOMIC_TRIGGERS = [
    r"\bcrore\b", r"\bbillion\b", r"\btrillion\b", r"\btax\b", r"\bgst\b", r"\bduty\b",
    r"\bpolicy\b", r"\bsubsidy\b", r"\btariff\b", r"\bscheme\b", r"\binvestment\b",
    r"\btender\b", r"\bexport\b", r"\bimport\b", r"\bguidelines\b", r"\bcircular\b",
    r"\bbill\b", r"\bamendment\b", r"\bclearance\b", r"\bcontract\b", r"\bprocurement\b",
    r"\beconomy\b", r"\bgdp\b", r"\binflation\b", r"\bcpi\b", r"\brate\b", r"\brepo\b"
]

MACRO_INDICATORS = [
    r"\beconomy\b", r"\bgdp\b", r"\binflation\b", r"\bcpi\b", r"\bwpi\b", r"\brbi\b",
    r"\bfiscal\b", r"\btax\b", r"\bbudget\b", r"\bmonetary\b", r"\bforex\b", r"\bsovereign\b",
    r"\bfdi\b", r"\bexport\b", r"\bimport\b", r"\brepo\b", r"\binterest rate\b", r"\bcrude\b",
    r"\bcurrency\b", r"\brupee\b", r"\bdollar\b", r"\bgst collection\b", r"\btrade deficit\b"
]


def classify_macro_heuristically(title: str, snippet: str, authority: str) -> dict[str, Any]:
    """Institutional heuristic rule-based macro classifier."""
    combined = f"{title} {snippet} {authority}".lower()

    # Discard non-economic ceremonial government PR, personal gossip, or routine exams
    if any(re.search(p, combined) for p in NON_ECONOMIC_NOISE):
        return {
            "is_material": False,
            "sectors": [],
            "impact_grade": "Tier 3 (Routine)",
            "impact_bias": "NEUTRAL",
            "impact_summary": "Non-institutional noise or personal transaction"
        }

    # 1. Match sectors from Ministry & Keywords
    matched_sectors: list[str] = []

    # Map detected ministry to primary sectors
    for min_name, secs in MINISTRY_TO_SECTORS.items():
        if min_name.lower() in authority.lower():
            for s in secs:
                if s not in matched_sectors and s != "GENERAL_MACRO":
                    matched_sectors.append(s)

    # Map keywords
    for sector, kws in SECTOR_KEYWORDS.items():
        if any(re.search(rf"\b{re.escape(k)}\b", combined) for k in kws):
            if sector not in matched_sectors:
                matched_sectors.append(sector)

    # If still no sector matched, only assign GENERAL_MACRO if genuine sovereign macro indicators exist
    if not matched_sectors:
        if any(re.search(p, combined) for p in MACRO_INDICATORS):
            matched_sectors = ["GENERAL_MACRO"]
        else:
            return {
                "is_material": False,
                "sectors": [],
                "impact_grade": "Tier 3 (Routine)",
                "impact_bias": "NEUTRAL",
                "impact_summary": "Non-macro routine news release"
            }

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
        "is_material": True,
        "sectors": matched_sectors[:3],
        "impact_grade": impact_grade,
        "impact_bias": impact_bias,
        "impact_summary": impact_summary
    }
