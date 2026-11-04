"""
Client Excel / CSV Import & Export Engine for Vriddhi Research Desk Terminal.
Supports bulk client creation, updates, and automatic distribution group linking.
"""

import io
import re
import csv
from datetime import datetime, timezone
import openpyxl
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from openpyxl.utils import get_column_letter

from .controlpanel import Analyst, ClientGroup
from .db import get_analysts, get_client_groups, save_analyst, save_client_group, get_folders


def generate_clients_workbook(include_template: bool = False) -> bytes:
    """
    Generates a professionally formatted Excel (.xlsx) file containing either
    all registered clients or a sample starter template.
    """
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Clients & Subscribers"

    # Styling
    header_fill = PatternFill(start_color="1E1B4B", end_color="1E1B4B", fill_type="solid")
    header_font = Font(name="Calibri", size=11, bold=True, color="FFFFFF")
    sample_fill = PatternFill(start_color="F0FDF4", end_color="F0FDF4", fill_type="solid")
    center_align = Alignment(horizontal="center", vertical="center")
    left_align = Alignment(horizontal="left", vertical="center")

    thin_border = Border(
        left=Side(style='thin', color='E2E8F0'),
        right=Side(style='thin', color='E2E8F0'),
        top=Side(style='thin', color='E2E8F0'),
        bottom=Side(style='thin', color='E2E8F0')
    )

    headers = [
        "Full Name",
        "WhatsApp Phone (10 Digits)",
        "Group(s)",
        "Portfolio Baskets",
        "Direct Companies",
        "Macro Sectors",
        "Delivery Active",
        "Email Address"
    ]
    ws.append(headers)

    for col_idx in range(1, len(headers) + 1):
        cell = ws.cell(row=1, column=col_idx)
        cell.fill = header_fill
        cell.font = header_font
        cell.alignment = center_align
        cell.border = thin_border

    if include_template:
        # Sample starter rows to guide the user
        sample_rows = [
            [
                "Rahul Sharma",
                "9820012345",
                "VIP Advisory, Vriddhi",
                "GAME, SET",
                "TCS, INFY",
                "ALL",
                "YES",
                "rahul@example.com"
            ],
            [
                "Pooja Mehta",
                "9821122334",
                "VRIDDHi 2",
                "ALL",
                "",
                "BANKS, FINANCIAL TECHNOLOGY (FINTECH)",
                "YES",
                "pooja@mehta.com"
            ],
            [
                "Vikram Desai",
                "9833445566",
                "Institutional Desk",
                "MATCH, JUNIOR",
                "RELIANCE",
                "ALL",
                "NO",
                ""
            ]
        ]
        for row in sample_rows:
            ws.append(row)
            row_idx = ws.max_row
            for col_idx in range(1, len(headers) + 1):
                c = ws.cell(row=row_idx, column=col_idx)
                c.fill = sample_fill
                c.border = thin_border
                c.alignment = center_align if col_idx in [2, 7] else left_align
    else:
        analysts = get_analysts()
        groups = get_client_groups()
        aid_to_groups = {}
        for g in groups:
            for cid in g.client_ids:
                aid_to_groups.setdefault(cid, []).append(g.name)

        for a in analysts:
            g_names = ", ".join(aid_to_groups.get(a.id, []))
            baskets = ", ".join(a.assigned_folders) if a.assigned_folders else "ALL"
            companies = ", ".join(a.assigned_companies) if getattr(a, "assigned_companies", None) else ""
            sectors = ", ".join(a.macro_sectors) if a.macro_sectors else "ALL"
            ws.append([
                a.name,
                a.phone,
                g_names,
                baskets,
                companies,
                sectors,
                "YES" if getattr(a, "is_active", True) else "NO",
                getattr(a, "email", "") or ""
            ])
            row_idx = ws.max_row
            for col_idx in range(1, len(headers) + 1):
                c = ws.cell(row=row_idx, column=col_idx)
                c.border = thin_border
                c.alignment = center_align if col_idx in [2, 7] else left_align

    # Auto-adjust column widths
    for col in ws.columns:
        max_len = max(len(str(cell.value or '')) for cell in col)
        col_letter = get_column_letter(col[0].column)
        ws.column_dimensions[col_letter].width = max(max_len + 4, 14)

    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)
    return buf.getvalue()


def generate_clients_csv(include_template: bool = False) -> str:
    """Generates clean CSV text representation of clients or template."""
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow([
        "Full Name",
        "WhatsApp Phone (10 Digits)",
        "Group(s)",
        "Portfolio Baskets",
        "Direct Companies",
        "Macro Sectors",
        "Delivery Active",
        "Email Address"
    ])

    if include_template:
        writer.writerow(["Rahul Sharma", "9820012345", "VIP Advisory, Vriddhi", "GAME, SET", "TCS, INFY", "ALL", "YES", "rahul@example.com"])
        writer.writerow(["Pooja Mehta", "9821122334", "VRIDDHi 2", "ALL", "", "BANKS, IT", "YES", "pooja@mehta.com"])
    else:
        analysts = get_analysts()
        groups = get_client_groups()
        aid_to_groups = {}
        for g in groups:
            for cid in g.client_ids:
                aid_to_groups.setdefault(cid, []).append(g.name)

        for a in analysts:
            g_names = ", ".join(aid_to_groups.get(a.id, []))
            baskets = ", ".join(a.assigned_folders) if a.assigned_folders else "ALL"
            companies = ", ".join(a.assigned_companies) if getattr(a, "assigned_companies", None) else ""
            sectors = ", ".join(a.macro_sectors) if a.macro_sectors else "ALL"
            writer.writerow([
                a.name,
                a.phone,
                g_names,
                baskets,
                companies,
                sectors,
                "YES" if getattr(a, "is_active", True) else "NO",
                getattr(a, "email", "") or ""
            ])

    return output.getvalue()


def parse_client_sheet(file_bytes: bytes, filename: str) -> dict:
    """Parses Excel (.xlsx/.xls) or CSV bytes into validated client rows."""
    rows = []
    is_csv = filename.lower().endswith(".csv")
    if is_csv:
        text = file_bytes.decode("utf-8-sig", errors="ignore")
        reader = csv.reader(io.StringIO(text))
        rows = list(reader)
    else:
        try:
            wb = openpyxl.load_workbook(io.BytesIO(file_bytes), data_only=True)
            ws = wb.active
            for r in ws.iter_rows(values_only=True):
                if any(cell is not None for cell in r):
                    rows.append([str(c) if c is not None else "" for c in r])
        except Exception as e:
            return {"error": f"Failed to parse Excel file: {str(e)}"}

    if not rows or len(rows) < 2:
        return {"error": "The uploaded file is empty or missing data rows."}

    # Map headers flexibly
    raw_header = [str(c).strip().lower() for c in rows[0]]
    col_map = {}
    for idx, col in enumerate(raw_header):
        cleaned = re.sub(r'[^a-z0-9]', '', col)
        if any(k in cleaned for k in ["name", "clientname", "subscriber", "fullname", "contactname"]):
            col_map.setdefault("name", idx)
        elif any(k in cleaned for k in ["phone", "whatsapp", "mobile", "number", "cell"]):
            col_map.setdefault("phone", idx)
        elif any(k in cleaned for k in ["group", "groups", "distribution", "list", "team"]):
            col_map.setdefault("groups", idx)
        elif any(k in cleaned for k in ["basket", "baskets", "folder", "folders", "portfolio"]):
            col_map.setdefault("folders", idx)
        elif any(k in cleaned for k in ["sector", "sectors", "macro"]):
            col_map.setdefault("sectors", idx)
        elif any(k in cleaned for k in ["company", "companies", "ticker", "tickers", "stocks"]):
            col_map.setdefault("companies", idx)
        elif any(k in cleaned for k in ["active", "status", "enabled", "delivery"]):
            col_map.setdefault("active", idx)
        elif any(k in cleaned for k in ["email", "mail"]):
            col_map.setdefault("email", idx)

    if "name" not in col_map or "phone" not in col_map:
        return {
            "error": f"Missing required headers ('Full Name' and 'WhatsApp Phone'). Headers detected: {', '.join(raw_header[:6])}"
        }

    available_folders = get_folders()
    parsed_records = []

    for row_idx, r in enumerate(rows[1:], start=2):
        name = r[col_map["name"]].strip() if col_map["name"] < len(r) else ""
        raw_phone = r[col_map["phone"]].strip() if col_map["phone"] < len(r) else ""
        if not name and not raw_phone:
            continue

        # Clean and validate phone number
        phone_digits = re.sub(r'\D', '', raw_phone.split('.')[0])
        if phone_digits.startswith("91") and len(phone_digits) == 12:
            phone_digits = phone_digits[2:]
        elif len(phone_digits) > 10 and phone_digits.startswith("0"):
            phone_digits = phone_digits[1:]

        if len(phone_digits) != 10:
            parsed_records.append({
                "row": row_idx,
                "error": f"Invalid phone '{raw_phone}'. Must be a 10-digit mobile number."
            })
            continue

        if not name:
            parsed_records.append({
                "row": row_idx,
                "error": f"Client Name is empty for phone '{phone_digits}'."
            })
            continue

        groups_raw = r[col_map["groups"]].strip() if "groups" in col_map and col_map["groups"] < len(r) else ""
        group_names = [g.strip() for g in re.split(r'[,;]+', groups_raw) if g.strip()]

        folders_raw = r[col_map["folders"]].strip() if "folders" in col_map and col_map["folders"] < len(r) else ""
        if not folders_raw or folders_raw.upper() == "ALL":
            assigned_folders = available_folders
        else:
            assigned_folders = [f.strip().upper() for f in re.split(r'[,;]+', folders_raw) if f.strip()]

        sectors_raw = r[col_map["sectors"]].strip() if "sectors" in col_map and col_map["sectors"] < len(r) else ""
        if not sectors_raw or sectors_raw.upper() == "ALL":
            macro_sectors = ["ALL"]
        else:
            macro_sectors = [s.strip().upper() for s in re.split(r'[,;]+', sectors_raw) if s.strip()]

        companies_raw = r[col_map["companies"]].strip() if "companies" in col_map and col_map["companies"] < len(r) else ""
        assigned_companies = [c.strip().upper() for c in re.split(r'[,;]+', companies_raw) if c.strip()]

        active_raw = r[col_map["active"]].strip().upper() if "active" in col_map and col_map["active"] < len(r) else "YES"
        is_active = active_raw not in ["NO", "FALSE", "0", "INACTIVE", "PAUSED"]

        email = r[col_map["email"]].strip() if "email" in col_map and col_map["email"] < len(r) else ""

        parsed_records.append({
            "row": row_idx,
            "name": name,
            "phone": phone_digits,
            "email": email,
            "groups": group_names,
            "assigned_folders": assigned_folders,
            "assigned_companies": assigned_companies,
            "macro_sectors": macro_sectors,
            "is_active": is_active
        })

    return {"records": parsed_records}


def import_clients_records(records: list[dict], auto_create_groups: bool = True) -> dict:
    """Saves parsed records to the database and links to distribution groups."""
    existing_analysts = get_analysts()
    phone_map = {}
    name_map = {}
    for a in existing_analysts:
        digits = re.sub(r'\D', '', a.phone)[-10:]
        if digits:
            phone_map[digits] = a
        if a.name:
            name_map[a.name.strip().lower()] = a

    existing_groups = get_client_groups()
    grp_map = {g.name.strip().lower(): g for g in existing_groups}

    imported_count = 0
    updated_count = 0
    groups_created_count = 0
    errors = []

    for r in records:
        if "error" in r:
            errors.append(f"Row {r['row']}: {r['error']}")
            continue

        name = r["name"]
        phone = r["phone"]
        email = r.get("email", "")
        folders = r.get("assigned_folders", [])
        companies = r.get("assigned_companies", [])
        sectors = r.get("macro_sectors", ["ALL"])
        is_active = r.get("is_active", True)

        # Match existing client by phone or name
        matched = phone_map.get(phone) or name_map.get(name.strip().lower())
        if matched:
            cid = matched.id
            updated_count += 1
        else:
            base_slug = re.sub(r'[^a-z0-9_]', '', name.strip().lower().replace(' ', '_'))[:18]
            cid = base_slug or f"cl_{phone[-6:]}"
            if any(a.id == cid for a in existing_analysts):
                cid = f"{cid}_{phone[-4:]}"
            imported_count += 1

        analyst = Analyst(
            id=cid,
            name=name,
            phone=phone,
            email=email,
            assigned_companies=companies,
            assigned_folders=folders,
            macro_sectors=sectors,
            is_active=is_active
        )
        save_analyst(analyst)
        phone_map[phone] = analyst
        name_map[name.strip().lower()] = analyst

        # Synchronize group memberships
        for gname in r.get("groups", []):
            clean_gname = gname.strip()
            if not clean_gname:
                continue
            gkey = clean_gname.lower()
            if gkey in grp_map:
                grp = grp_map[gkey]
                if cid not in grp.client_ids:
                    grp.client_ids.append(cid)
                    save_client_group(grp)
            elif auto_create_groups:
                new_gid = re.sub(r'[^a-z0-9_]', '', gkey.replace(' ', '_'))[:20] or f"grp_{len(grp_map)+1}"
                new_grp = ClientGroup(
                    id=new_gid,
                    name=clean_gname,
                    description="Auto-created from Excel import",
                    morning_active=True,
                    evening_active=True,
                    client_ids=[cid]
                )
                save_client_group(new_grp)
                grp_map[gkey] = new_grp
                groups_created_count += 1

    return {
        "status": "ok",
        "imported_count": imported_count,
        "updated_count": updated_count,
        "groups_created_count": groups_created_count,
        "errors": errors
    }

