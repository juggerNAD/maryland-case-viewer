import streamlit as st
import pandas as pd
import datetime
import re
import gspread
from google.oauth2 import service_account

# ---------- CONFIG ----------
SHEET_ID = "1GCbpfhxqu8G4jYNn_jRKWdAvvw2wal5w0nsnRFUNNfA"
SHEET_NAME = "Sheet1"
ALLOWED_CASE_STATUSES = ["Entered", "Renewed", "Unsatisfied"]

# ---------- GOOGLE SHEETS SCOPES ----------
SCOPE = [
    "https://spreadsheets.google.com/feeds",
    "https://www.googleapis.com/auth/drive"
]

CASE_TYPES = [
    "Civil - General", "Civil - Foreclosure", "Civil - Contract", "Judgment - Monetary", "Lien / Judgment",
    "Paternity", "Judgment - District Court Lien", "Domestic Relations (Divorce)",
    "Judgment - State Tax Lien", "Civil - Tort / Contract", "Paternity / Parentage - Private",
    "Criminal", "Judgment - Restitution", "Divorce - Absolute", "Foreclosure - Residential",
    "Contract - Breach", "URESA / UIFSA", "Guardianship - Minor Person and Property",
    "Paternity / Parentage - Agency", "Custody", "Confessed Judgment", "Case Type",
    "Tort - Premises Liability", "Guardianship", "Condemnation / Eminent Domain", "Contract",
    "Tort - Wrongful Death", "Tort - Lead Paint", "Tort - Motor", "Recorded Judgment",
    "Judgment - Federal Lien", "Foreign Judgment", "Employment / Labor", "Other Civil",
    "Tort - Other", "Attorney Grievance", "Tort - Fraud", "Judgment - Other Court"
]

# ---------- UTIL ----------
def download_sheet_csv(sheet_id, sheet_name=SHEET_NAME):
    try:
        # Convert immutable secrets to a normal dict
        creds_dict = dict(st.secrets["gcp_service_account"])
        creds_dict["private_key"] = creds_dict["private_key"].replace("\\n", "\n")
        creds = service_account.Credentials.from_service_account_info(creds_dict, scopes=SCOPE)
        client = gspread.authorize(creds)

        sheet = client.open_by_key(sheet_id).worksheet(sheet_name)
        data = sheet.get_all_values()
        df = pd.DataFrame(data[1:], columns=data[0])
        return df

    except Exception as e:
        st.error(f"❌ Error loading Google Sheet: {e}")
        st.stop()

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
    if pd.isna(v) or str(v).strip() == "":
        return None
    s = str(v).strip()
    fmts = ["%m/%d/%Y", "%m/%d/%y", "%Y-%m-%d", "%Y/%m/%d", "%m-%d-%Y"]
    for f in fmts:
        try:
            return datetime.datetime.strptime(s, f).date()
        except:
            continue
    try:
        tmp = pd.to_datetime(s, errors="coerce")
        if pd.isna(tmp):
            return None
        return tmp.date()
    except:
        return None

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
        if "plaintiff" in c or "name_for" in c:
            mapping["plaintiff"] = c
    return df, mapping

# ---------- LOAD DATA ----------
df, mapping = load_and_map()

# Normalize case_status
if mapping.get("case_status") and mapping["case_status"] in df.columns:
    df[mapping["case_status"]] = df[mapping["case_status"]].astype(str).str.strip().str.lower()

# ---------- STREAMLIT UI ----------
st.set_page_config(page_title="Maryland Case Viewer", layout="wide")
st.title("⚖️ Maryland Case Viewer")

st.sidebar.header("Filters")

# Case Status
status_values = ["All"] + ALLOWED_CASE_STATUSES
status_select = st.sidebar.selectbox("Case Status", status_values, index=0)

# Court System
court_values = ["All", "Circuit Court", "District Court"]
court_select = st.sidebar.selectbox("Court System", court_values, index=0)

# Case Type
type_values = ["All"] + CASE_TYPES
type_select = st.sidebar.selectbox("Case Type", type_values, index=0)

# Judgment Amount
amount_opts = ["All", ">= $10,000", ">= $25,000", ">= $50,000", ">= $100,000"]
amount_select = st.sidebar.selectbox("Judgment Amount", amount_opts, index=1)

# Date Range
st.sidebar.subheader("Entry Date Range")
start_date = st.sidebar.date_input("Start", datetime.date(2014, 1, 1))
end_date = st.sidebar.date_input("End", datetime.date.today())

# ---------- FILTER LOGIC ----------
def apply_filters(df):
    d = df.copy()
    if mapping.get("judgment_amount") and mapping["judgment_amount"] in d.columns:
        d["_amount_num"] = d[mapping["judgment_amount"]].apply(parse_amount)
    else:
        d["_amount_num"] = 0.0
    if mapping.get("entry_date") and mapping["entry_date"] in d.columns:
        d["_entry_date_parsed"] = d[mapping["entry_date"]].apply(parse_date_flexible)
    else:
        d["_entry_date_parsed"] = None

    if status_select != "All" and mapping.get("case_status"):
        d = d[d[mapping["case_status"]] == status_select.lower()]

    if court_select != "All" and mapping.get("court_system"):
        d = d[d[mapping["court_system"]].astype(str).str.strip().str.lower() == court_select.lower()]

    if type_select != "All" and mapping.get("case_type"):
        d = d[d[mapping["case_type"]].astype(str).str.strip().str.lower() == type_select.lower()]

    if amount_select != "All":
        val = int(re.sub(r"[^\d]", "", amount_select))
        d = d[d["_amount_num"] >= val]

    if "_entry_date_parsed" in d.columns:
        if start_date:
            d = d[d["_entry_date_parsed"].apply(lambda x: x is not None and x >= start_date)]
        if end_date:
            d = d[d["_entry_date_parsed"].apply(lambda x: x is not None and x <= end_date)]

    display_cols = []
    order = ["case_number", "plaintiff", "case_status", "judgment_amount", "entry_date",
             "court_system", "case_type", "address", "case_link"]
    for k in order:
        if mapping.get(k) and mapping[k] in d.columns:
            display_cols.append(mapping[k])

    d_display = d[display_cols].copy()

    # Add clickable View Case button
    if mapping.get("case_link") in d_display.columns:
        d_display["View Case"] = d_display[mapping["case_link"]].apply(
            lambda x: f'<a href="{x}" target="_blank"><button style="background-color:#1a73e8;color:white;border:none;padding:5px 10px;border-radius:5px;cursor:pointer;">View Case</button></a>'
            if pd.notna(x) and str(x).strip() != "" else ""
        )
        d_display.drop(columns=[mapping["case_link"]], inplace=True)

    # Format judgment amount
    if mapping.get("judgment_amount") in d_display.columns:
        d_display[mapping["judgment_amount"]] = d_display[mapping["judgment_amount"]].apply(
            lambda x: f"${parse_amount(x):,.2f}"
        )

    # Format entry date
    if mapping.get("entry_date") in d_display.columns:
        d_display[mapping["entry_date"]] = d_display[mapping["entry_date"]].apply(
            lambda x: parse_date_flexible(x).strftime("%Y-%m-%d") if parse_date_flexible(x) else ""
        )

    return d_display

# ---------- APPLY FILTERS ----------
if st.sidebar.button("Apply Filters"):
    filtered_df = apply_filters(df)
    st.write(f"Records Found: {len(filtered_df)}")
    if not filtered_df.empty:
        st.markdown(filtered_df.to_html(escape=False, index=False), unsafe_allow_html=True)
    else:
        st.warning("No records found matching your filters.")
