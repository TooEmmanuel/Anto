
import io
import os
import re
import tempfile
import zipfile
from pathlib import Path

import geopandas as gpd
import matplotlib.pyplot as plt
import pandas as pd
import streamlit as st

st.set_page_config(page_title="Kenya Health Data Analyzer", layout="wide")

DEFAULT_DATA_PATH = "updated_with_function.xlsx"
DEFAULT_BENEFICIARY_PATH = "Book1.xlsx"

PROGRAM_SHORT_NAMES = {
    "Paediatric Cardiology": "Peds Cardiology",
    "Paediatric Endocrinology": "Peds Endo",
    "Paediatric Critical Care Nursing": "Peds Critical Care Nursing",
    "Paediatric Emergency And Critical Care Medicine": "Peds Emergency & Critical Care",
    "Paediatric Emergency and Critical Care Medicine": "Peds Emergency & Critical Care",
    "Paediatric Neurology": "Peds Neurology",
    "Paediatric Haematooncology": "Peds Haematooncology",
    "Paediatric Nephrology": "Peds Nephrology",
    "Paediatric Infectious Diseases": "Peds Infectious Diseases",
    "Paediatric Gastroenterology": "Peds Gastroenterology",
    "Paediatric Nursing": "Peds Nursing",
    "Paediatric Nursing Pnt": "Peds Nursing",
    "Neonatology": "Neonatology",
    "Neonatal Nursing": "Neonatal Nursing",
    "Midwifery": "Midwifery",
}

COUNTY_NORMALIZATION = {
    "Egeyo Marakwet": "Elgeyo Marakwet",
    "Trans Nzoia": "Trans-Nzoia",
    "Tana river": "Tana River",
    "Tharaka Nithi": "Tharaka-Nithi",
    "Muranga": "Murang'a",
    "Homa Bay County": "Homa Bay",
    "Kiambu County": "Kiambu",
    "Nairobi County": "Nairobi",
    "Mombasa County": "Mombasa",
}

FUNCTION_RULES = {
    "Monitoring": [
        "monitor", "bp", "vital", "pulse", "ecg", "spo2", "oximeter", "infusion pump",
        "syringe pump", "temperature", "weight scale", "glucometer", "monitoring",
    ],
    "Screening & Diagnostics": [
        "x-ray", "ultrasound", "scan", "screen", "diagnostic", "laboratory", "lab",
        "microscope", "ct", "mri", "doppler", "echo", "ecg machine", "test", "analyzer",
    ],
    "Management": [
        "bed", "incubator", "couch", "chair", "trolley", "delivery", "resuscitator",
        "oxygen", "ventilator", "theatre", "suction", "cabinet", "sterilizer",
        "refrigerator", "fridge", "autoclave", "management",
    ],
}


def clean_text(x):
    if pd.isna(x):
        return ""
    return str(x).strip()


def title_clean(value: str) -> str:
    value = clean_text(value)
    if not value:
        return ""
    value = re.sub(r"\s+", " ", value)
    return value


def normalize_county_name(name: str) -> str:
    name = title_clean(name)
    if not name:
        return name
    return COUNTY_NORMALIZATION.get(name, name)


def normalize_program_name(name: str) -> str:
    name = title_clean(name)
    if not name:
        return ""
    name = re.sub(r"\([^)]*\)", "", name)
    name = re.sub(r"[/_-]+", " ", name)
    name = re.sub(r"\s+", " ", name).strip()
    return name


def normalize_facility_name(name: str) -> str:
    name = clean_text(name).lower()
    if not name:
        return ""
    replacements = {
        "county referral hospital": "hospital",
        "county referal hospital": "hospital",
        "county refferal hospital": "hospital",
        "county referral": "hospital",
        "county hospital": "hospital",
        "sub county hospital": "subhospital",
        "sub-county hospital": "subhospital",
        "sub county": "subcounty",
        "level 5 hospital": "level 5 hospital",
        "referral hospital": "hospital",
        "teaching and referral hospital": "hospital",
        "teaching & referral hospital": "hospital",
    }
    for old, new in replacements.items():
        name = name.replace(old, new)
    name = re.sub(r"but later moved to.*", "", name)
    name = re.sub(r"in training", "", name)
    name = re.sub(r"[^a-z0-9 ]", " ", name)
    name = re.sub(r"\s+", " ", name).strip()
    return name


def infer_function(item_name: str) -> str:
    item = clean_text(item_name).lower()
    if not item:
        return "Unclassified"
    for function_name, keywords in FUNCTION_RULES.items():
        if any(keyword in item for keyword in keywords):
            return function_name
    return "Unclassified"


def standardize_main_columns(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df.columns = [re.sub(r"\s+", " ", str(c)).strip() for c in df.columns]
    rename_map = {
        "County": "County",
        "Metrics": "Metrics",
        "Total Quantity Annually": "Total Quantity Annually",
        "Unit cost per metric KES": "Unit cost per metric KES",
        "Total Cost KES": "Total Cost KES",
        "Total Cost USD": "Total Cost USD",
        "Area of specialization": "Area of Specialization",
    }
    df = df.rename(columns=rename_map)

    text_cols = [
        "County", "Health_Facility", "Program", "Item_Type", "Item_Name",
        "Metrics", "Area of Specialization", "Function"
    ]
    for col in text_cols:
        if col in df.columns:
            df[col] = df[col].apply(clean_text)

    if "County" in df.columns:
        df["County"] = df["County"].apply(normalize_county_name)

    if "Program" in df.columns:
        df["Program"] = df["Program"].apply(normalize_program_name)

    if "Health_Facility" in df.columns:
        df["Facility Normalized"] = df["Health_Facility"].apply(normalize_facility_name)

    if "Item_Type" in df.columns:
        df["Item_Type"] = (
            df["Item_Type"].str.strip().str.title()
            .replace({"Supplies": "Supply", "Drugs": "Drug", "Equipments": "Equipment"})
        )

    for col in ["Total Quantity Annually", "Unit cost per metric KES", "Total Cost KES", "Total Cost USD"]:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0)

    if "Program" in df.columns:
        df["Program Short"] = df["Program"].replace(PROGRAM_SHORT_NAMES)

    if "Function" not in df.columns:
        df["Function"] = ""
    df["Function"] = df.apply(
        lambda row: row["Function"] if clean_text(row["Function"]) else infer_function(row.get("Item_Name", "")),
        axis=1,
    )

    if "Area of Specialization" not in df.columns:
        df["Area of Specialization"] = "Unassigned"

    return df


def standardize_beneficiary_columns(df: pd.DataFrame, main_df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df.columns = [re.sub(r"\s+", " ", str(c)).strip() for c in df.columns]

    rename_map = {
        "Name of Beneficiary": "Beneficiary Name",
        "Program": "Program",
        "County": "County",
        "Facility of origin": "Facility of Origin",
        "Facility of Redeployment, NA if not applicable": "Facility of Redeployment",
        "Status (Completed, In school, Undergoing Bonding)": "Training Status",
    }
    df = df.rename(columns=rename_map)

    for col in ["Beneficiary Name", "Program", "County", "Facility of Origin", "Facility of Redeployment", "Training Status"]:
        if col in df.columns:
            df[col] = df[col].apply(clean_text)

    if "County" in df.columns:
        df["County"] = df["County"].apply(normalize_county_name)

    if "Program" in df.columns:
        df["Program"] = df["Program"].apply(normalize_program_name)
        df["Program Short"] = df["Program"].replace(PROGRAM_SHORT_NAMES)

    if "Facility of Origin" in df.columns:
        df["Facility Origin Normalized"] = df["Facility of Origin"].apply(normalize_facility_name)
    else:
        df["Facility Origin Normalized"] = ""

    if "Facility of Redeployment" in df.columns:
        df["Facility Redeployment Normalized"] = df["Facility of Redeployment"].apply(normalize_facility_name)
    else:
        df["Facility Redeployment Normalized"] = ""

    program_area_map = (
        main_df[["Program", "Area of Specialization"]]
        .dropna()
        .drop_duplicates()
        .groupby("Program")["Area of Specialization"]
        .agg(lambda x: x.mode().iloc[0] if not x.mode().empty else x.iloc[0])
        .to_dict()
    )
    df["Area of Specialization"] = df["Program"].map(program_area_map).fillna("Unmapped")

    if "Beneficiary Name" not in df.columns:
        df["Beneficiary Name"] = "Unnamed Beneficiary"

    return df


@st.cache_data(show_spinner=False)
def load_main_data_from_bytes(file_bytes: bytes, file_name: str) -> pd.DataFrame:
    suffix = Path(file_name).suffix.lower()
    bio = io.BytesIO(file_bytes)
    if suffix in [".xlsx", ".xls"]:
        df = pd.read_excel(bio)
    elif suffix == ".csv":
        df = pd.read_csv(bio)
    else:
        raise ValueError("Please upload an Excel or CSV file.")
    return standardize_main_columns(df)


@st.cache_data(show_spinner=False)
def load_default_main_data() -> pd.DataFrame:
    if not os.path.exists(DEFAULT_DATA_PATH):
        return pd.DataFrame()
    return standardize_main_columns(pd.read_excel(DEFAULT_DATA_PATH))


@st.cache_data(show_spinner=False)
def load_beneficiary_data_from_bytes(file_bytes: bytes, file_name: str, main_df: pd.DataFrame) -> pd.DataFrame:
    suffix = Path(file_name).suffix.lower()
    bio = io.BytesIO(file_bytes)
    if suffix in [".xlsx", ".xls"]:
        xls = pd.ExcelFile(bio)
        df = pd.read_excel(bio, sheet_name=xls.sheet_names[0])
    elif suffix == ".csv":
        df = pd.read_csv(bio)
    else:
        raise ValueError("Please upload an Excel or CSV file for beneficiaries.")
    return standardize_beneficiary_columns(df, main_df)


@st.cache_data(show_spinner=False)
def load_default_beneficiary_data(main_df: pd.DataFrame) -> pd.DataFrame:
    if not os.path.exists(DEFAULT_BENEFICIARY_PATH):
        return pd.DataFrame()
    xls = pd.ExcelFile(DEFAULT_BENEFICIARY_PATH)
    df = pd.read_excel(DEFAULT_BENEFICIARY_PATH, sheet_name=xls.sheet_names[0])
    return standardize_beneficiary_columns(df, main_df)


def format_currency_cols(df: pd.DataFrame, cols=None):
    if cols is None:
        cols = ["Total Cost KES", "Total Cost USD"]
    df = df.copy()
    for col in cols:
        if col in df.columns:
            df[col] = df[col].round(2)
    return df


def build_area_summary(df: pd.DataFrame, beneficiaries_df: pd.DataFrame, measure: str) -> pd.DataFrame:
    item_types = ["Equipment", "Drug", "Supply", "Infrastructure"]
    base = (
        df.groupby("Area of Specialization", dropna=False)[measure]
        .sum()
        .rename("Total")
        .reset_index()
    )
    pivot = (
        df.pivot_table(
            index="Area of Specialization",
            columns="Item_Type",
            values=measure,
            aggfunc="sum",
            fill_value=0,
        )
        .reset_index()
    )
    for item in item_types:
        if item not in pivot.columns:
            pivot[item] = 0

    out = base.merge(pivot, on="Area of Specialization", how="left")
    out["County Coverage"] = (
        df.groupby("Area of Specialization")["County"].nunique().reindex(out["Area of Specialization"]).fillna(0).astype(int).values
    )

    if not beneficiaries_df.empty:
        ben = (
            beneficiaries_df.groupby("Area of Specialization")["Beneficiary Name"]
            .nunique()
            .rename("Beneficiaries")
            .reset_index()
        )
        out = out.merge(ben, on="Area of Specialization", how="left")
    else:
        out["Beneficiaries"] = 0

    out["Beneficiaries"] = out["Beneficiaries"].fillna(0).astype(int)
    cols = ["Area of Specialization", "Beneficiaries", "County Coverage", "Total"] + item_types
    return out[cols].sort_values("Area of Specialization")


def build_county_summary(df: pd.DataFrame, beneficiaries_df: pd.DataFrame, measure: str) -> pd.DataFrame:
    item_types = ["Equipment", "Drug", "Supply", "Infrastructure"]
    totals = (
        df.groupby("County", dropna=False)[measure]
        .sum()
        .rename("Total")
        .reset_index()
    )
    item_pivot = (
        df.pivot_table(
            index="County",
            columns="Item_Type",
            values=measure,
            aggfunc="sum",
            fill_value=0,
        )
        .reset_index()
    )
    for item in item_types:
        if item not in item_pivot.columns:
            item_pivot[item] = 0

    program_pivot = (
        df.pivot_table(
            index="County",
            columns="Program Short",
            values=measure,
            aggfunc="sum",
            fill_value=0,
        )
        .reset_index()
    )

    facility_counts = df.groupby("County")["Health_Facility"].nunique().rename("Health Facilities").reset_index()

    merged = totals.merge(item_pivot, on="County", how="left")
    merged = merged.merge(program_pivot, on="County", how="left")
    merged = merged.merge(facility_counts, on="County", how="left")

    if not beneficiaries_df.empty:
        ben_total = (
            beneficiaries_df.groupby("County")["Beneficiary Name"]
            .nunique()
            .rename("Total Beneficiaries")
            .reset_index()
        )
        ben_program = (
            beneficiaries_df.pivot_table(
                index="County",
                columns="Program Short",
                values="Beneficiary Name",
                aggfunc=pd.Series.nunique,
                fill_value=0,
            )
            .reset_index()
        )
        ben_program = ben_program.rename(columns=lambda c: f"{c} Beneficiaries" if c != "County" else c)

        ben_area = (
            beneficiaries_df.pivot_table(
                index="County",
                columns="Area of Specialization",
                values="Beneficiary Name",
                aggfunc=pd.Series.nunique,
                fill_value=0,
            )
            .reset_index()
        )
        ben_area = ben_area.rename(columns=lambda c: f"{c} Beneficiaries" if c != "County" else c)

        matched_origin = (
            beneficiaries_df[beneficiaries_df["Facility Origin Normalized"].isin(set(df["Facility Normalized"].dropna()))]
            .groupby("County")["Beneficiary Name"]
            .nunique()
            .rename("Facility-Origin Matches")
            .reset_index()
        )
        matched_redeploy = (
            beneficiaries_df[beneficiaries_df["Facility Redeployment Normalized"].isin(set(df["Facility Normalized"].dropna()))]
            .groupby("County")["Beneficiary Name"]
            .nunique()
            .rename("Facility-Redeployment Matches")
            .reset_index()
        )

        merged = merged.merge(ben_total, on="County", how="left")
        merged = merged.merge(ben_program, on="County", how="left")
        merged = merged.merge(ben_area, on="County", how="left")
        merged = merged.merge(matched_origin, on="County", how="left")
        merged = merged.merge(matched_redeploy, on="County", how="left")
    else:
        merged["Total Beneficiaries"] = 0

    for col in merged.columns:
        if col != "County":
            merged[col] = merged[col].fillna(0)

    return merged.sort_values("Total", ascending=False)


def build_function_summary(df: pd.DataFrame, measure: str) -> pd.DataFrame:
    equipment = df[df["Item_Type"].eq("Equipment")].copy()
    out = (
        equipment.groupby(["Function", "Item_Type"], dropna=False)[measure]
        .sum()
        .reset_index()
        .pivot(index="Function", columns="Item_Type", values=measure)
        .fillna(0)
        .reset_index()
    )
    numeric_cols = [c for c in out.columns if c != "Function"]
    out["Total"] = out[numeric_cols].sum(axis=1)
    first_cols = ["Function", "Total"]
    other_cols = [c for c in out.columns if c not in first_cols]
    return out[first_cols + other_cols].sort_values("Total", ascending=False)


def build_beneficiary_link_table(df: pd.DataFrame, beneficiaries_df: pd.DataFrame) -> pd.DataFrame:
    if beneficiaries_df.empty:
        return pd.DataFrame(columns=[
            "County", "Program Short", "Area of Specialization", "Beneficiaries",
            "Origin Facility Matches", "Redeployment Facility Matches"
        ])

    matched_origin = beneficiaries_df["Facility Origin Normalized"].isin(set(df["Facility Normalized"].dropna()))
    matched_redeploy = beneficiaries_df["Facility Redeployment Normalized"].isin(set(df["Facility Normalized"].dropna()))

    temp = beneficiaries_df.copy()
    temp["Origin Match"] = matched_origin.astype(int)
    temp["Redeployment Match"] = matched_redeploy.astype(int)

    summary = (
        temp.groupby(["County", "Program Short", "Area of Specialization"], dropna=False)
        .agg(
            Beneficiaries=("Beneficiary Name", pd.Series.nunique),
            Origin_Facility_Matches=("Origin Match", "sum"),
            Redeployment_Facility_Matches=("Redeployment Match", "sum"),
        )
        .reset_index()
        .sort_values(["County", "Program Short"])
    )
    return summary


def to_excel_bytes(sheets: dict[str, pd.DataFrame]) -> bytes:
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine="xlsxwriter") as writer:
        for sheet_name, df_sheet in sheets.items():
            safe_name = sheet_name[:31]
            df_sheet.to_excel(writer, index=False, sheet_name=safe_name)
            workbook = writer.book
            worksheet = writer.sheets[safe_name]

            header_fmt = workbook.add_format({
                "bold": True,
                "text_wrap": True,
                "valign": "top",
                "fg_color": "#D9EAF7",
                "border": 1,
            })
            number_fmt = workbook.add_format({"num_format": "#,##0.00"})
            integer_fmt = workbook.add_format({"num_format": "#,##0"})

            for col_num, value in enumerate(df_sheet.columns.values):
                worksheet.write(0, col_num, value, header_fmt)
                max_len = max(
                    len(str(value)),
                    df_sheet.iloc[:, col_num].astype(str).map(len).max() if not df_sheet.empty else 10,
                )
                width = min(max(max_len + 2, 12), 32)
                series = df_sheet.iloc[:, col_num] if not df_sheet.empty else pd.Series(dtype=object)
                if pd.api.types.is_numeric_dtype(series):
                    fmt = integer_fmt if (series.fillna(0) % 1 == 0).all() else number_fmt
                    worksheet.set_column(col_num, col_num, width, fmt)
                else:
                    worksheet.set_column(col_num, col_num, width)
    return output.getvalue()


def load_shapefile_from_upload(uploaded_zip):
    with tempfile.TemporaryDirectory() as tmpdir:
        zip_path = os.path.join(tmpdir, uploaded_zip.name)
        with open(zip_path, "wb") as f:
            f.write(uploaded_zip.getbuffer())
        extract_dir = os.path.join(tmpdir, "shape")
        os.makedirs(extract_dir, exist_ok=True)
        with zipfile.ZipFile(zip_path, "r") as zf:
            zf.extractall(extract_dir)

        shp_files = list(Path(extract_dir).rglob("*.shp"))
        if not shp_files:
            raise ValueError("No .shp file found inside the ZIP.")
        return gpd.read_file(shp_files[0])


def find_county_column(gdf: gpd.GeoDataFrame) -> str | None:
    candidates = [c for c in gdf.columns if c.lower() in {"county", "name", "county_nam", "county_name", "adm1_en", "adm2_en"}]
    if candidates:
        return candidates[0]
    obj_cols = [c for c in gdf.columns if gdf[c].dtype == "object"]
    return obj_cols[0] if obj_cols else None


def show_dataframe(df: pd.DataFrame, height=480):
    st.dataframe(format_currency_cols(df), use_container_width=True, height=height)


def main():
    st.title("Kenya Health Data Analyzer")
    st.caption("Uses the resource dataset plus the beneficiary dataset to generate totals, county summaries, beneficiary counts, downloadable files, and an optional county map.")

    with st.sidebar:
        st.header("Upload files")
        uploaded_main = st.file_uploader("Upload resource dataset", type=["xlsx", "xls", "csv"])
        uploaded_beneficiaries = st.file_uploader("Upload beneficiary dataset", type=["xlsx", "xls", "csv"])
        measure = st.selectbox(
            "Measure for summaries",
            options=["Total Cost KES", "Total Cost USD", "Total Quantity Annually"],
            index=0,
        )
        page = st.radio(
            "Go to",
            [
                "Overview",
                "Summary 1: Area of Specialization",
                "Summary 2: County + Beneficiaries",
                "Summary 3: Equipment Function",
                "Map",
                "Downloads",
            ],
        )

    if uploaded_main is not None:
        main_df = load_main_data_from_bytes(uploaded_main.getvalue(), uploaded_main.name)
        main_source = uploaded_main.name
    else:
        main_df = load_default_main_data()
        main_source = DEFAULT_DATA_PATH if not main_df.empty else "No resource file loaded"

    if main_df.empty:
        st.warning("Upload the resource dataset to begin.")
        st.stop()

    if uploaded_beneficiaries is not None:
        beneficiaries_df = load_beneficiary_data_from_bytes(uploaded_beneficiaries.getvalue(), uploaded_beneficiaries.name, main_df)
        ben_source = uploaded_beneficiaries.name
    else:
        beneficiaries_df = load_default_beneficiary_data(main_df)
        ben_source = DEFAULT_BENEFICIARY_PATH if not beneficiaries_df.empty else "No beneficiary file loaded"

    area_summary = build_area_summary(main_df, beneficiaries_df, measure)
    county_summary = build_county_summary(main_df, beneficiaries_df, measure)
    function_summary = build_function_summary(main_df, measure)
    beneficiary_link_table = build_beneficiary_link_table(main_df, beneficiaries_df)

    if page == "Overview":
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Resource Rows", f"{len(main_df):,}")
        c2.metric("Counties in Resources", f"{main_df['County'].nunique():,}")
        c3.metric("Programs in Resources", f"{main_df['Program'].nunique():,}")
        c4.metric(f"Total {measure}", f"{main_df[measure].sum():,.2f}")

        if not beneficiaries_df.empty:
            b1, b2, b3, b4 = st.columns(4)
            b1.metric("Beneficiaries", f"{beneficiaries_df['Beneficiary Name'].nunique():,}")
            b2.metric("Beneficiary Counties", f"{beneficiaries_df['County'].nunique():,}")
            b3.metric("Origin Facility Matches", f"{beneficiary_link_table['Origin_Facility_Matches'].sum():,}" if not beneficiary_link_table.empty else "0")
            b4.metric("Redeployment Matches", f"{beneficiary_link_table['Redeployment_Facility_Matches'].sum():,}" if not beneficiary_link_table.empty else "0")

        st.subheader("Loaded sources")
        st.write(f"Resource source: **{main_source}**")
        st.write(f"Beneficiary source: **{ben_source}**")

        st.subheader("Resource data")
        show_dataframe(main_df, height=320)

        if not beneficiaries_df.empty:
            st.subheader("Beneficiary data")
            show_dataframe(beneficiaries_df, height=320)

    elif page == "Summary 1: Area of Specialization":
        st.subheader("Summary by Area of Specialization")
        st.write("This combines total resource values with beneficiary counts for Maternal Health, Newborn Health, Blood, and any other mapped areas present in the data.")
        show_dataframe(area_summary)

    elif page == "Summary 2: County + Beneficiaries":
        st.subheader("Summary by County")
        st.write("County totals, item-type splits, program totals, total beneficiaries, beneficiary counts by program, and beneficiary counts by area are shown in one downloadable table.")
        show_dataframe(county_summary, height=520)

        st.subheader("Beneficiary linkage table")
        st.write("This table shows beneficiary counts by county, program, and area, plus how many matched facilities from the resource dataset.")
        show_dataframe(beneficiary_link_table, height=380)

    elif page == "Summary 3: Equipment Function":
        st.subheader("Categorization of equipment by function")
        st.write("Functions include Monitoring, Screening & Diagnostics, and Management. Existing Function values are used first; blank values fall back to keyword-based categorization.")
        show_dataframe(function_summary)

        st.subheader("Equipment record preview")
        equipment_only = main_df[main_df["Item_Type"].eq("Equipment")][["County", "Program", "Health_Facility", "Item_Name", "Function", measure]]
        show_dataframe(equipment_only, height=360)

    elif page == "Map":
        st.subheader("Kenya counties map")
        st.write("Upload a ZIP containing shapefile components (.shp, .shx, .dbf, .prj). The app joins county totals from the summary table to the map.")
        shape_zip = st.file_uploader("Upload county shapefile ZIP", type=["zip"], key="shape_zip")
        if shape_zip is not None:
            try:
                gdf = load_shapefile_from_upload(shape_zip)
                county_col = find_county_column(gdf)
                if county_col is None:
                    st.error("Could not detect a county-name column in the shapefile.")
                else:
                    map_df = county_summary[["County", "Total"]].copy()
                    gdf = gdf.copy()
                    gdf["County_join"] = gdf[county_col].astype(str).apply(normalize_county_name)
                    merged = gdf.merge(map_df, left_on="County_join", right_on="County", how="left")
                    merged["Total"] = merged["Total"].fillna(0)

                    fig, ax = plt.subplots(figsize=(10, 10))
                    merged.plot(column="Total", cmap="Blues", linewidth=0.8, edgecolor="black", legend=True, ax=ax)
                    ax.set_title(f"County totals by {measure}", fontsize=14)
                    ax.axis("off")
                    st.pyplot(fig, use_container_width=True)

                    show_dataframe(merged[[county_col, "County_join", "Total"]].drop_duplicates(), height=300)
            except Exception as e:
                st.error(f"Could not process shapefile: {e}")
        else:
            st.info("Upload the Kenya county shapefile ZIP to display the map.")

    elif page == "Downloads":
        st.subheader("Downloadable files")

        excel_bytes = to_excel_bytes({
            "Area Summary": area_summary,
            "County Summary": county_summary,
            "Function Summary": function_summary,
            "Beneficiary Links": beneficiary_link_table,
            "Cleaned Resources": main_df,
            "Cleaned Beneficiaries": beneficiaries_df,
        })

        st.download_button(
            label="Download all summaries as Excel",
            data=excel_bytes,
            file_name="kenya_health_summaries.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )

        st.download_button(
            label="Download county summary CSV",
            data=county_summary.to_csv(index=False).encode("utf-8"),
            file_name="county_summary.csv",
            mime="text/csv",
        )

        st.download_button(
            label="Download beneficiary linkage CSV",
            data=beneficiary_link_table.to_csv(index=False).encode("utf-8"),
            file_name="beneficiary_linkage.csv",
            mime="text/csv",
        )

        st.info("For deployment, use the ZIP package I generated outside the app. It includes app.py, requirements.txt, README, and both default Excel files.")


if __name__ == "__main__":
    main()
