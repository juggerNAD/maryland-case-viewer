from nicegui import ui
import pandas as pd
import datetime
import re
import gspread
from oauth2client.service_account import ServiceAccountCredentials

# ---------- CONFIG ----------
SHEET_ID = "1GCbpfhxqu8G4jYNn_jRKWdAvvw2wal5w0nsnRFUNNfA"
SHEET_NAME = "Sheet1"
SERVICE_ACCOUNT_FILE = "service_account.json"
ALLOWED_CASE_STATUSES = ["Entered", "Renewed", "Unsatisfied"]

# ---------- UTIL ----------
def download_sheet_csv(sheet_id, sheet_name=SHEET_NAME):
    SCOPE = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
    creds = ServiceAccountCredentials.from_json_keyfile_name(SERVICE_ACCOUNT_FILE, SCOPE)
    client = gspread.authorize(creds)
    sheet = client.open_by_key(sheet_id).worksheet(sheet_name)
    data = sheet.get_all_values()
    df = pd.DataFrame(data[1:], columns=data[0])
    return df

def normalize_columns(cols):
    return [c.strip().lower().replace("\n", " ").replace(" ", "_") for c in cols]

def parse_amount(s):
    if pd.isna(s):
        return 0.0
    s = re.sub(r"[^\d.\-]", "", str(s))
    try:
        return float(s)
    except:
        return 0.0

def parse_date_flexible(v):
    if pd.isna(v):
        return None
    s = str(v).strip()
    if s == "":
        return None
    fmts = ["%m/%d/%Y", "%m/%d/%y", "%Y-%m-%d", "%Y/%m/%d", "%m-%d-%Y"]
    for f in fmts:
        try:
            return datetime.datetime.strptime(s, f).date()
        except:
            pass
    try:
        tmp = pd.to_datetime(s, errors="coerce")
        if pd.isna(tmp):
            return None
        return tmp.date()
    except:
        return None

# ---------- LOAD ----------
def load_and_map():
    df = download_sheet_csv(SHEET_ID, SHEET_NAME)
    norm_cols = normalize_columns(df.columns)
    df.columns = norm_cols
    mapping = {}
    for c in norm_cols:
        if "case" in c and ("num" in c or "number" in c):
            mapping["case_number"] = c
        if "status" in c:
            mapping["case_status"] = c
        if "amount" in c or "judgment" in c:
            mapping["judgment_amount"] = c
        if "date" in c:
            mapping["entry_date"] = c
        if "court" in c:
            mapping["court_system"] = c
        if "type" in c:
            mapping["case_type"] = c
        if "link" in c or "url" in c:
            mapping["case_link"] = c
        if "address" in c:
            mapping["address"] = c
    return df, mapping

df, mapping = load_and_map()

# ---------- UI ----------
with ui.header().classes("bg-indigo-700 text-white shadow-md"):
    ui.label("⚖️ Maryland Case Viewer").classes("text-2xl font-semibold pl-4")

# Main container: filters on left, table on right
with ui.row().classes("w-full h-screen p-4 gap-6 items-start"):

    # LEFT FILTER PANEL
    with ui.card().classes("w-[280px] p-4 shadow-md"):
        ui.label("Filters").classes("text-lg font-semibold mb-2")

        # Case Status
        status_values = ["All"] + ALLOWED_CASE_STATUSES
        status_select = ui.select(status_values, value="All", label="Case Status").classes("w-full")

        # Court System
        court_values = ["All"]
        if mapping.get("court_system"):
            vals = sorted(df[mapping["court_system"]].dropna().astype(str).unique().tolist())
            court_values += vals
        court_select = ui.select(court_values, value="All", label="Court System").classes("w-full")

        # Case Type
        type_values = ["All"]
        if mapping.get("case_type"):
            vals = sorted(df[mapping["case_type"]].dropna().astype(str).unique().tolist())
            type_values += vals
        type_select = ui.select(type_values, value="All", label="Case Type").classes("w-full")

        # Judgment Amount
        amount_opts = ["All", ">= $10,000", ">= $25,000", ">= $50,000", ">= $100,000"]
        amount_select = ui.select(amount_opts, value=">= $10,000", label="Judgment Amount").classes("w-full")

        # Date Pickers
        ui.label("Entry Date Range").classes("mt-2 mb-1")
        with ui.row().classes("gap-2 w-full"):
            with ui.column().classes("w-1/2"):
                ui.label("Start").classes("text-xs text-gray-600")
                start_picker = ui.date(value=datetime.date(2014, 1, 1)).classes("w-full text-xs")
            with ui.column().classes("w-1/2"):
                ui.label("End").classes("text-xs text-gray-600")
                end_picker = ui.date(value=datetime.date.today()).classes("w-full text-xs")

        apply_btn = ui.button("Apply Filters").classes("w-full mt-4 bg-indigo-600 text-white")

    # RIGHT TABLE PANEL
    with ui.column().classes("flex-1 overflow-auto"):
        result_label = ui.label("Records Found: 0").classes("text-sm text-gray-700 mb-2")
        table_cols = []
        order = ["case_number", "case_status", "judgment_amount", "entry_date", "court_system", "case_type", "address", "case_link"]
        for k in order:
            if mapping.get(k):
                label = k.replace("_", " ").title()
                table_cols.append({"name": k, "label": label, "field": k, "sortable": True})
        table = ui.table(columns=table_cols, rows=[], row_key="case_number").props("html-columns").classes("w-full text-sm")

# ---------- FILTER HANDLER ----------
def apply_filters_handler():
    d = df.copy()

    if mapping.get("judgment_amount"):
        d["_amount_num"] = d[mapping["judgment_amount"]].apply(parse_amount)
    else:
        d["_amount_num"] = 0.0

    if mapping.get("entry_date"):
        d["_entry_date_parsed"] = d[mapping["entry_date"]].apply(parse_date_flexible)
    else:
        d["_entry_date_parsed"] = pd.NaT

    st = status_select.value
    if mapping.get("case_status") and st and st != "All":
        d = d[d[mapping["case_status"]].astype(str).str.strip().str.title() == st]

    cs = court_select.value
    if mapping.get("court_system") and cs and cs != "All":
        d = d[d[mapping["court_system"]].astype(str).str.strip().str.lower() == str(cs).strip().lower()]

    ct = type_select.value
    if mapping.get("case_type") and ct and ct != "All":
        d = d[d[mapping["case_type"]].astype(str).str.strip().str.lower() == str(ct).strip().lower()]

    amt_label = amount_select.value
    if amt_label and amt_label != "All":
        val = int(re.sub(r"[^\d]", "", amt_label))
        d = d[d["_amount_num"] >= val]

    s = start_picker.value
    e = end_picker.value
    if s:
        sdate = s if isinstance(s, datetime.date) else datetime.datetime.fromisoformat(s).date()
        d = d[d["_entry_date_parsed"].apply(lambda x: x is not None and x >= sdate)]
    if e:
        edate = e if isinstance(e, datetime.date) else datetime.datetime.fromisoformat(e).date()
        d = d[d["_entry_date_parsed"].apply(lambda x: x is not None and x <= edate)]

    rows = []
    for _, row in d.iterrows():
        r = {}
        for key, col in mapping.items():
            if not col:
                continue
            val = row.get(col, "")
            if key == "judgment_amount":
                val = f"${parse_amount(val):,.2f}"
            if key == "entry_date":
                parsed = parse_date_flexible(val)
                val = parsed.strftime("%Y-%m-%d") if parsed else ""
            if key == "case_link":
                if pd.isna(val) or str(val).strip() == "":
                    val = ""
                else:
                    val = f"<a href='{val}' target='_blank' class='text-indigo-600 underline'>View Case</a>"
            r[key] = val
        if "case_number" not in r or r.get("case_number") in (None, ""):
            r["case_number"] = str(row.tolist()[0])[:30]
        rows.append(r)

    result_label.text = f"Records Found: {len(rows)}"
    table.rows = rows
    table.update()

apply_btn.on("click", lambda _: apply_filters_handler())

# ---------- RUN ----------
ui.run(title="Maryland Case Viewer (Google Sheets)")
