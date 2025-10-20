import streamlit as st
import pandas as pd
import datetime
import re
import gspread
from google.oauth2 import service_account
import copy

# ---------- CONFIG ----------
SHEET_ID = "1GCbpfhxqu8G4jYNn_jRKWdAvvw2wal5w0nsnRFUNNfA"
SHEET_NAME = "Sheet1"
ALLOWED_CASE_STATUSES = ["entered", "renewed", "unsatisfied"]

# ---------- UTIL ----------
SCOPE = [
    "https://spreadsheets.google.com/feeds",
    "https://www.googleapis.com/auth/drive"
]

def download_sheet_csv(sheet_id, sheet_name=SHEET_NAME):
    try:
        if "gcp_service_account" in st.secrets:
            # Make a deep copy so we do NOT modify st.secrets directly
            creds_dict = copy.deepcopy(st.secrets["gcp_service_account"])
            # Convert literal \n to actual newlines
            creds_dict = st.secrets["gcp_service_account"]
            creds_dict["private_key"] = creds_dict["private_key"].replace("\\n", "\n")

            creds = service_account.Credentials.from_service_account_info(creds_dict, scopes=SCOPE)
            client = gspread.authorize(creds)
        else:
            st.error("❌ GCP Service Account not found in Streamlit Secrets.")
            st.stop()

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

# ---------- LOAD DATA ----------
df, mapping = load_and_map()

# Normalize case_status column for consistent filtering
if mapping.get("case_status") and mapping["case_status"] in df.columns:
    df[mapping["case_status"]] = df[mapping["case_status"]].astype(str).str.strip().str.lower()

# ---------- STREAMLIT UI ----------
st.set_page_config(page_title="Maryland Case Viewer", layout="wide")
st.title("⚖️ Maryland Case Viewer")

# Sidebar Filters
st.sidebar.header("Filters")

# Case Status
status_values = ["All"] + [s.title() for s in ALLOWED_CASE_STATUSES]
status_select = st.sidebar.selectbox("Case Status", status_values, index=0)

# Court System
court_values = ["All"]
if mapping.get("court_system") and mapping["court_system"] in df.columns:
    vals = sorted(df[mapping["court_system"]].dropna().astype(str).unique())
    court_values += vals
court_select = st.sidebar.selectbox("Court System", court_values, index=0)

# Case Type
type_values = ["All"]
if mapping.get("case_type") and mapping["case_type"] in df.columns:
    vals = sorted(df[mapping["case_type"]].dropna().astype(str).unique())
    type_values += vals
type_select = st.sidebar.selectbox("Case Type", type_values, index=0)

# Judgment Amount
amount_opts = ["All", ">= $10,000", ">= $25,000", ">= $50,000", ">= $100,000"]
amount_select = st.sidebar.selectbox("Judgment Amount", amount_opts, index=1)

# Date Range
st.sidebar.subheader("Entry Date Range")
start_date = st.sidebar.date_input(
    "Start",
    value=datetime.date(2014, 1, 1),
    min_value=datetime.date(2000, 1, 1),
    max_value=datetime.date.today()
)
end_date = st.sidebar.date_input(
    "End",
    value=datetime.date.today(),
    min_value=datetime.date(2014, 1, 1),
    max_value=datetime.date.today()
)

# ---------- FILTER LOGIC ----------
def apply_filters(df):
    d = df.copy()

    # Judgment amount
    if mapping.get("judgment_amount") and mapping["judgment_amount"] in d.columns:
        d["_amount_num"] = d[mapping["judgment_amount"]].apply(parse_amount)
    else:
        d["_amount_num"] = 0.0

    # Entry date parsing
    if mapping.get("entry_date") and mapping["entry_date"] in d.columns:
        d["_entry_date_parsed"] = d[mapping["entry_date"]].apply(parse_date_flexible)
    else:
        d["_entry_date_parsed"] = None

    # Case Status filter
    if status_select != "All" and mapping.get("case_status") and mapping["case_status"] in d.columns:
        d = d[d[mapping["case_status"]] == status_select.strip().lower()]

    # Court System filter
    if court_select != "All" and mapping.get("court_system") and mapping["court_system"] in d.columns:
        d = d[d[mapping["court_system"]].astype(str).str.strip().str.lower() == court_select.strip().lower()]

    # Case Type filter
    if type_select != "All" and mapping.get("case_type") and mapping["case_type"] in d.columns:
        d = d[d[mapping["case_type"]].astype(str).str.strip().str.lower() == type_select.strip().lower()]

    # Judgment amount filter
    if amount_select != "All":
        val = int(re.sub(r"[^\d]", "", amount_select))
        d = d[d["_amount_num"] >= val]

    # Date range filter
    if "_entry_date_parsed" in d.columns and d["_entry_date_parsed"].notnull().any():
        if start_date:
            d = d[d["_entry_date_parsed"].apply(lambda x: x is not None and x >= start_date)]
        if end_date:
            d = d[d["_entry_date_parsed"].apply(lambda x: x is not None and x <= end_date)]

    # Format table
    display_cols = []
    order = ["case_number", "case_status", "judgment_amount", "entry_date", "court_system", "case_type", "address", "case_link"]
    for k in order:
        if mapping.get(k) and mapping[k] in d.columns:
            display_cols.append(mapping[k])

    d_display = d[display_cols].copy()

    # Format judgment amount
    if mapping.get("judgment_amount") in d_display.columns:
        d_display[mapping["judgment_amount"]] = d_display[mapping["judgment_amount"]].apply(lambda x: f"${parse_amount(x):,.2f}")

    # Format entry date
    if mapping.get("entry_date") in d_display.columns:
        def format_date(x):
            dt = parse_date_flexible(x)
            return dt.strftime("%Y-%m-%d") if dt else ""
        d_display[mapping["entry_date"]] = d_display[mapping["entry_date"]].apply(format_date)

    # Format case link
    if mapping.get("case_link") in d_display.columns:
        d_display[mapping["case_link"]] = d_display[mapping["case_link"]].apply(
            lambda x: f"[View Case]({x})" if pd.notna(x) and str(x).strip() != "" else ""
        )

    return d_display

# ---------- APPLY FILTERS ----------
if st.sidebar.button("Apply Filters"):
    filtered_df = apply_filters(df)
    st.write(f"Records Found: {len(filtered_df)}")
    st.dataframe(filtered_df, use_container_width=True)
