import streamlit as st
import pandas as pd
from io import BytesIO
from datetime import datetime
from hashlib import sha256
import io

# =========================
# App Config
# =========================
st.set_page_config(page_title="Payroll Summary", layout="wide")

# =========================
# Simple Login
# =========================
USERS = {"admin": {"hash": sha256("admin123".encode()).hexdigest()}}

def auth_ok(user: str, password: str) -> bool:
    rec = USERS.get(user)
    return bool(rec) and sha256(password.encode()).hexdigest() == rec["hash"]

def login_gate():
    if st.session_state.get("auth_user"):
        return
    st.title("🔐 Sign in")
    with st.form("login"):
        u = st.text_input("Username")
        p = st.text_input("Password", type="password")
        go = st.form_submit_button("Sign in")
    if go:
        if auth_ok(u.strip(), p):
            st.session_state["auth_user"] = u.strip()
            st.rerun()
        else:
            st.error("Invalid username or password.")
    st.stop()

login_gate()

st.caption(f"Signed in as **{st.session_state['auth_user']}**")
st.title("📊 Payroll Summary Generator")

# =========================
# Helpers
# =========================
def normalize_columns(cols):
    return (
        pd.Index(cols).astype(str)
        .str.replace("\u00a0", " ", regex=False)
        .str.replace(r"\s+", " ", regex=True)
        .str.strip()
    )

def first_match(name_or_patterns, columns):
    pats = name_or_patterns if isinstance(name_or_patterns, (list, tuple)) else [name_or_patterns]
    lower = {c.lower(): c for c in columns}
    for p in pats:
        p = p.lower()
        if p in lower:
            return lower[p]
        for k, orig in lower.items():
            if p in k:
                return orig
    return None

def numcol(df, name, alts=None, default=0):
    candidates = [name] + (alts or [])
    for c in candidates:
        if c in df.columns:
            return pd.to_numeric(df[c], errors="coerce").fillna(0)
    return pd.Series(default, index=df.index)

# =========================
# Canonical KITTING Export Layout
# =========================

FINAL_EXPORT_COLUMNS = [

    "Emp No","Name","C/Center","Join Date","Resign Date","Position","Group",

    "Monthly Salary",

    "OT 1.5 (Hour)","OT 1.5 (Amount)",
    "OT 2.0 (Hour)","OT 2.0 (Amount)",
    "P.H 2.0 (Hour)","P.H 2.0 (Amount)",
    "OT 3.0 (Hour)","OT 3.0 (Amount)",

    "Morning Shift","Night Shift",

    "Performance Incentive","Incentive Programme",
    "Recognition Award","Annual Leave",

    "Backpay","Backpay Shift Allowance","Backpay OT","Compensation (CSN)",

    "Gross Pay","EPF ER","Socso ER","EIS ER",

    "HRDF","Medical Fee",

    "Unpaid Leave","Notice in Lieu","Overpaid",

    "EPF EE","Socso EE","EIS EE","PCB",

    "Total Deduction","Net Pay",
]


# =========================
# Upload
# =========================
uploaded_file = st.file_uploader("Upload Customize Report (Excel)", type=["xls","xlsx","xlsm"])
if not uploaded_file:
    st.stop()

file_bytes = uploaded_file.getvalue()

@st.cache_data(show_spinner=False)
def get_sheet_names(file_bytes):
    with io.BytesIO(file_bytes) as bio:
        return tuple(pd.ExcelFile(bio).sheet_names)

@st.cache_data(show_spinner=False)
def read_sheet(file_bytes, sheet_name, header_row):
    with io.BytesIO(file_bytes) as bio:
        df = pd.read_excel(bio, sheet_name=sheet_name, header=header_row)
    df.columns = normalize_columns(df.columns)
    return df

with st.sidebar:
    header_row = st.number_input("Header row (0-indexed)", value=2)
    sheet = st.selectbox("Sheet", get_sheet_names(file_bytes))
    if st.button("🚪 Log out"):
        st.session_state.pop("auth_user", None)
        st.rerun()

# =========================
# Read Data
# =========================
df = read_sheet(file_bytes, sheet, header_row)

dept_col = first_match(["C/Center","Cost Center","Department","Dept"], df.columns) or df.columns[0]

selected_dept = st.selectbox(
    "Select Department",
    sorted(df[dept_col].dropna().astype(str).unique())
)

df_dept = df[df[dept_col].astype(str) == str(selected_dept)].copy()

# =========================
# Build Summary
# =========================
summary = df_dept.copy()

# ---- Identity Columns ----

join_col = first_match(["Join Date", "Joined", "Date Joined"], df_dept.columns)
resign_col = first_match(["Resign Date", "Resign", "Termination Date"], df_dept.columns)
pos_col = first_match(["Pos", "Position"], df_dept.columns)

summary["Join Date"] = (
    pd.to_datetime(df_dept[join_col], errors="coerce")
    if join_col else pd.NaT
)

summary["Resign Date"] = (
    pd.to_datetime(df_dept[resign_col], errors="coerce")
    if resign_col else pd.NaT
)

summary["Position"] = (
    df_dept[pos_col].astype(str)
    if pos_col else ""
)


# ---- Salary / OT / Shift ----
summary["Monthly Salary"] = numcol(df_dept, "M/Basic", ["Monthly Salary", "Basic"])

summary["OT 1.5 (Hour)"]   = numcol(df_dept, "OT HR 1½", ["OT HR 1.5"])
summary["OT 1.5 (Amount)"] = numcol(df_dept, "OT Amt 1½", ["OT Amt 1.5"])

summary["OT 2.0 (Hour)"]   = numcol(df_dept, "OT HR 2")
summary["OT 2.0 (Amount)"] = numcol(df_dept, "OT Amt 2")

summary["P.H 2.0 (Hour)"]   = numcol(df_dept, "PH OT 2", ["PH HR 2"])
summary["P.H 2.0 (Amount)"] = numcol(df_dept, "PH Amt 2")

summary["OT 3.0 (Hour)"]   = numcol(df_dept, "OT HR 3")
summary["OT 3.0 (Amount)"] = numcol(df_dept, "OT Amt 3")

summary["Morning Shift"] = numcol(df_dept, "MS")
summary["Night Shift"]   = numcol(df_dept, "NS")

# ---- Incentives / Leave ----
summary["Performance Incentive"] = numcol(df_dept, "PEI")
summary["Incentive Programme"]   = numcol(df_dept, "ICP")
summary["Recognition Award"]    = numcol(df_dept, "REA")
summary["Annual Leave"]         = numcol(df_dept, "BAL")

# ---- Backpay / CSN ----
summary["Backpay"] = (
    numcol(df_dept, "BAC")
    + numcol(df_dept, "BBB")
    + numcol(df_dept, "BSC")
)

summary["Backpay Shift Allowance"] = numcol(df_dept, "BMS")

summary["Backpay OT"] = (
    numcol(df_dept, "BOT")
    + numcol(df_dept, "BO2")
    + numcol(df_dept, "BO3")
)

summary["Compensation (CSN)"] = numcol(df_dept, "CSN")

# ---- Employer Statutory & HRDF ----
summary["EPF ER"] = numcol(df_dept, "EPF ER", ["EPF`ER"])
summary["Socso ER"] = numcol(
    df_dept,
    "Soc ER",
    [
        "SOC ER",
        "SOCSO ER",
        "Socso ER",
        "SOCSO Employer",
        "Employer Socso",
    ],
)

summary["EIS ER"] = numcol(df_dept, "EIS ER", ["EIS`ER"])

summary["HRDF"] = numcol(df_dept, "HRDF")

summary["PCB"] = numcol(
    df_dept,
    "PCB",
    ["Potongan Cukai", "Income Tax", "Tax"]
)




# ---- Unpaid Leave ----
summary["Unpaid Leave"] = numcol(
    df_dept,
    "UPL",
    ["Unpaid Leave", "UPAID LEAVE", "UL"]

)

summary["SNT"] = numcol(df_dept,"SNT")
summary["Notice in Lieu"] = summary["SNT"]

summary["Overpaid"] = numcol(df_dept,"OAW")+numcol(df_dept,"OVR")+numcol(df_dept,"OVT")

# ---- Recalculate Gross Pay (KITTING style) ----
summary["Gross Pay"] = (
    summary["Monthly Salary"]
    + summary["OT 1.5 (Amount)"]
    + summary["OT 2.0 (Amount)"]
    + summary["P.H 2.0 (Amount)"]
    + summary["OT 3.0 (Amount)"]
    + summary["Morning Shift"]
    + summary["Night Shift"]
    + summary["Performance Incentive"]
    + summary["Incentive Programme"]
    + summary["Recognition Award"]
    + summary["Annual Leave"]
    + summary["Backpay"]
    + summary["Backpay Shift Allowance"]
    + summary["Backpay OT"]
    + summary["Compensation (CSN)"]
    - summary["Unpaid Leave"]
    - summary["SNT"]
    - summary["Overpaid"]
).round(2)



summary["MEC"] = numcol(df_dept,"MEC",["Medical"])



summary["EPF EE"] = numcol(df_dept,"EPF EE",["EPF`EE"])
summary["Socso EE"] = numcol(
    df_dept,
    "Soc EE",
    ["SOC EE", "SOCSO EE", "SOC`EE"]
)

summary["EIS EE"] = numcol(df_dept,"EIS EE",["EIS`EE"])

summary["Total Deduction"] = (
    summary["EPF EE"]
    + summary["Socso EE"]
    + summary["EIS EE"]
    + summary ["PCB"]
)


summary["Net Pay"] = (
    summary["Gross Pay"]
    - summary["Total Deduction"]
    + summary["MEC"]
).round(2)


# =========================
# Active vs Abscond
# =========================
summary["_Net"] = pd.to_numeric(summary["Net Pay"], errors="coerce")

active_df = summary[summary["_Net"] >= 0]
abscond_df = summary[summary["_Net"] < 0]

# =========================
# Force KITTING Export Format
# =========================
def build_export_block(df_block):

    df_out = df_block.copy()

    df_out.rename(columns={
        "MEC": "Medical Fee",
    }, inplace=True)

    df_out = df_out[[c for c in FINAL_EXPORT_COLUMNS if c in df_out.columns]]

    return df_out



active_clean = build_export_block(active_df.drop(columns=["_Net"]))
abscond_clean = build_export_block(abscond_df.drop(columns=["_Net"]))

# =========================
# Display
# =========================
st.subheader("✅ Active Employees")
st.dataframe(active_clean, use_container_width=True)

st.subheader("🚪 Abscond / Resign")
st.dataframe(abscond_clean, use_container_width=True)

# =========================
# Excel Export
# =========================
out = BytesIO()

with pd.ExcelWriter(out, engine="xlsxwriter") as writer:

    sheet_name = f"{selected_dept}_Summary"
    title_fmt = writer.book.add_format({"bold": True, "font_size": 12})

    row = 0

    active_clean.to_excel(writer, sheet_name=sheet_name, startrow=row+1, index=False)
    ws = writer.sheets[sheet_name]
    ws.write(row,0,"ACTIVE EMPLOYEES", title_fmt)

    row += len(active_clean) + 3

    abscond_clean.to_excel(writer, sheet_name=sheet_name, startrow=row+1, index=False)
    ws.write(row,0,"ABSCOND / RESIGN", title_fmt)

out.seek(0)

st.download_button(
    "📥 Download Payroll Summary (Excel)",
    out.getvalue(),
    file_name=f"{selected_dept}_Payroll_Summary.xlsx",
    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    use_container_width=True,
)
