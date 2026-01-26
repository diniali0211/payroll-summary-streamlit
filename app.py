#payroll summary generator 

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
        return True

    st.title("🔐 Sign in")
    with st.form("login"):
        u = st.text_input("Username")
        p = st.text_input("Password", type="password")
        go = st.form_submit_button("Sign in")

    if go:
        if auth_ok(u.strip(), p):
            st.session_state["auth_user"] = u.strip()
            st.success("Signed in!")
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

# =========================
# Upload
# =========================
uploaded_file = st.file_uploader("Upload Customize Report (Excel)", type=["xls", "xlsx", "xlsm"])
if not uploaded_file:
    st.stop()

file_bytes = uploaded_file.getvalue()

# =========================
# Sidebar
# =========================
with st.sidebar:
    st.header("⚙️ Settings")
    header_row = st.number_input("Header row (0-indexed)", value=2, min_value=0)

    sheet = st.selectbox("Sheet", get_sheet_names(file_bytes))

    if st.button("🚪 Log out"):
        st.session_state.pop("auth_user", None)
        st.rerun()

# =========================
# Read Data
# =========================
df = read_sheet(file_bytes, sheet, header_row)

dept_col = first_match(
    ["C/Center", "Cost Center", "Department", "Dept"],
    df.columns
) or df.columns[0]

selected_dept = st.selectbox(
    "Select Department",
    sorted(df[dept_col].dropna().astype(str).unique())
)

df_dept = df[df[dept_col].astype(str) == str(selected_dept)].copy()
df_dept.columns = normalize_columns(df_dept.columns)

# =========================
# Build Summary
# =========================
summary = df_dept.copy()

summary["Gross"] = numcol(df_dept, "Gross")
summary["UPL"] = numcol(df_dept, "UPL")
summary["SNT"] = numcol(df_dept, "SNT")
summary["Overpaid"] = numcol(df_dept, "OAW") + numcol(df_dept, "OVR") + numcol(df_dept, "OVT")
summary["MEC"] = numcol(df_dept, "MEC", ["Medical"])

summary["EPF EE"] = numcol(df_dept, "EPF EE", ["EPF`EE"])
summary["SOC EE"] = numcol(df_dept, "SOC EE", ["SOC`EE"])
summary["EIS EE"] = numcol(df_dept, "EIS EE", ["EIS`EE"])

summary["Total Deduction"] = (
    summary["EPF EE"] +
    summary["SOC EE"] +
    summary["EIS EE"]
)

summary["Net Pay"] = (
    summary["Gross"]
    - summary["UPL"]
    - summary["SNT"]
    - summary["Overpaid"]
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
# Display
# =========================
st.subheader("✅ Active Employees")
st.dataframe(active_df.drop(columns=["_Net"]), use_container_width=True)

st.subheader("🚪 Abscond / Resign")
st.dataframe(abscond_df.drop(columns=["_Net"]), use_container_width=True)

# =========================
# Excel Export
# =========================
out = BytesIO()
with pd.ExcelWriter(out, engine="xlsxwriter") as writer:
    active_df.drop(columns=["_Net"]).to_excel(
        writer, sheet_name="ACTIVE EMPLOYEES", index=False
    )
    abscond_df.drop(columns=["_Net"]).to_excel(
        writer, sheet_name="ABSCOND_RESIGN", index=False
    )

out.seek(0)

st.download_button(
    "📥 Download Payroll Summary (Excel)",
    out.getvalue(),
    file_name=f"{selected_dept}_Payroll_Summary.xlsx",
    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    use_container_width=True,
)
