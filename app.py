
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

st.set_page_config(
    page_title="Kenya Health Data Analyzer",
    page_icon="📊",
    layout="wide",
)

DEFAULT_DATA_PATH = "updated_with_function.xlsx"
DEFAULT_BENEFICIARY_PATH = "Book1.xlsx"
DEFAULT_SHAPEFILE_DIR = "shapefiles"

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
    "Elgeyo-Marakwet": "Elgeyo Marakwet",
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


def inject_styles():
    st.markdown(
        """
        <style>
        .stApp {
            background: linear-gradient(180deg, #f6fbff 0%, #eef7f1 100%);
        }
        .block-container {
            padding-top: 1.2rem;
            padding-bottom: 1.5rem;
        }
        div[data-testid="stMetric"] {
            background: white;
            border: 1px solid #d8e8ef;
            border-left: 6px solid #0f766e;
            padding: 0.8rem 1rem;
            border-radius: 14px;
            box-shadow: 0 4px 14px rgba(15, 118, 110, 0.08);
        }
        div[data-testid="stMetricLabel"] {
            color: #0f172a;
            font-weight: 600;
        }
        div[data-testid="stSidebar"] {
            background: linear-gradient(180deg, #123c69 0%, #0f766e 100%);
        }
        div[data-testid="stSidebar"] * {
            color: white !important;
        }
        .section-card {
            background: white;
            border-radius: 18px;
            padding: 1rem 1.1rem;
            border: 1px solid #d8e8ef;
            box-shadow: 0 4px 14px rgba(15, 118, 110, 0.06);
            margin-bottom: 1rem;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


def clean_text(x):
    if pd.isna(x):
        return ""
    return str(x).strip()


def title_clean(value: str) -> str:
    value = clean_text(value)
    if not value:
        return ""
    value = re.sub(r"\s+", " ", value)
    return value.strip()


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
    return re.sub(r"\s+", " ", name).strip()


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
        "sub county hospital": "subcounty hospital",
        "sub-county hospital": "subcounty hospital",
        "teaching and referral hospital": "hospital",
        "teaching & referral hospital": "hospital",
    }
    for old, new in replacements.items():
        name = name.replace(old, new)
    name = re.sub(r"but later moved to.*", "", name)
    name = re.sub(r"in training", "", name)
    name = re.sub(r"[^a-z0-9 ]", " ", name)
    return re.sub(r"\s+", " ", name).strip()


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
        "County ": "County",
        "Metrics": "Metrics",
        "Metrics ": "Metrics",
        "Total Quantity Annually": "Total Quantity Annually",
        "Total Quantity Annually ": "Total Quantity Annually",
        "Unit cost per metric KES": "Unit cost per metric KES",
        "Unit cost per metric KES ": "Unit cost per metric KES",
        "Unit cost per metric KES  ": "Unit cost per metric KES",
        "Total Cost KES": "Total Cost KES",
        "Total Cost KES ": "Total Cost KES",
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
        df["Program Short"] = df["Program"].replace(PROGRAM_SHORT_NAMES)

    if "Health_Facility" in df.columns:
        df["Facility Display"] = df["Health_Facility"].apply(title_clean)
        df["Facility Normalized"] = df["Health_Facility"].apply(normalize_facility_name)
    else:
        df["Facility Display"] = ""
        df["Facility Normalized"] = ""

    if "Item_Type" in df.columns:
        df["Item_Type"] = (
            df["Item_Type"].str.strip().str.title()
            .replace({"Supplies": "Supply", "Drugs": "Drug", "Equipments": "Equipment"})
        )

    for col in ["Total Quantity Annually", "Unit cost per metric KES", "Total Cost KES", "Total Cost USD"]:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0)

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
    else:
        df["Program Short"] = ""

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
def load_excel_or_csv(file_bytes: bytes, file_name: str) -> pd.DataFrame:
    suffix = Path(file_name).suffix.lower()
    bio = io.BytesIO(file_bytes)
    if suffix in [".xlsx", ".xls"]:
        return pd.read_excel(bio)
    if suffix == ".csv":
        return pd.read_csv(bio)
    raise ValueError("Please upload Excel or CSV files only.")


@st.cache_data(show_spinner=False)
def load_main_data_from_bytes(file_bytes: bytes, file_name: str) -> pd.DataFrame:
    return standardize_main_columns(load_excel_or_csv(file_bytes, file_name))


@st.cache_data(show_spinner=False)
def load_default_main_data() -> pd.DataFrame:
    if not os.path.exists(DEFAULT_DATA_PATH):
        return pd.DataFrame()
    return standardize_main_columns(pd.read_excel(DEFAULT_DATA_PATH))


@st.cache_data(show_spinner=False)
def load_beneficiary_data_from_bytes(file_bytes: bytes, file_name: str, main_df: pd.DataFrame) -> pd.DataFrame:
    return standardize_beneficiary_columns(load_excel_or_csv(file_bytes, file_name), main_df)


@st.cache_data(show_spinner=False)
def load_default_beneficiary_data(main_df: pd.DataFrame) -> pd.DataFrame:
    if not os.path.exists(DEFAULT_BENEFICIARY_PATH):
        return pd.DataFrame()
    return standardize_beneficiary_columns(pd.read_excel(DEFAULT_BENEFICIARY_PATH), main_df)


def get_facilities_for_counties(df: pd.DataFrame, counties: list[str]) -> list[str]:
    temp = df.copy()
    if counties:
        temp = temp[temp["County"].isin(counties)]
    return sorted([x for x in temp["Facility Display"].dropna().unique().tolist() if x])


def apply_filters(main_df: pd.DataFrame, ben_df: pd.DataFrame, counties: list[str], facilities: list[str]):
    filtered_main = main_df.copy()
    if counties:
        filtered_main = filtered_main[filtered_main["County"].isin(counties)]
    if facilities:
        filtered_main = filtered_main[filtered_main["Facility Display"].isin(facilities)]

    filtered_ben = ben_df.copy()
    if not filtered_ben.empty and counties:
        filtered_ben = filtered_ben[filtered_ben["County"].isin(counties)]

    facility_norms = set(filtered_main["Facility Normalized"].dropna().tolist())
    if not filtered_ben.empty and facilities:
        filtered_ben = filtered_ben[
            filtered_ben["Facility Origin Normalized"].isin(facility_norms) |
            filtered_ben["Facility Redeployment Normalized"].isin(facility_norms)
        ]

    return filtered_main, filtered_ben


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
        df.groupby("Area of Specialization")["County"].nunique()
        .reindex(out["Area of Specialization"])
        .fillna(0)
        .astype(int)
        .values
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
    return out[cols].sort_values("Total", ascending=False)


def build_county_summary(df: pd.DataFrame, beneficiaries_df: pd.DataFrame, measure: str) -> pd.DataFrame:
    item_types = ["Equipment", "Drug", "Supply", "Infrastructure"]
    totals = df.groupby("County", dropna=False)[measure].sum().rename("Total").reset_index()
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

    facility_counts = df.groupby("County")["Facility Display"].nunique().rename("Facilities").reset_index()

    merged = totals.merge(item_pivot, on="County", how="left")
    merged = merged.merge(program_pivot, on="County", how="left")
    merged = merged.merge(facility_counts, on="County", how="left")

    if not beneficiaries_df.empty:
        ben_total = beneficiaries_df.groupby("County")["Beneficiary Name"].nunique().rename("Total Beneficiaries").reset_index()
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

        facility_norms = set(df["Facility Normalized"].dropna().tolist())
       # matched_origin = (
         #   beneficiaries_df[beneficiaries_df["Facility Origin Normalized"].isin(facility_norms)]
        #    .groupby("County")["Beneficiary Name"]
         #   .nunique()
         #   .rename("Origin Matches")
        #    .reset_index()
       # )
       # matched_redeploy = (
       #     beneficiaries_df[beneficiaries_df["Facility Redeployment Normalized"].isin(facility_norms)]
       #     .groupby("County")["Beneficiary Name"]
         #   .nunique()
        #   .rename("Redeployment Matches")
        #    .reset_index()
      #  )

        merged = merged.merge(ben_total, on="County", how="left")
        merged = merged.merge(ben_program, on="County", how="left")
        merged = merged.merge(ben_area, on="County", how="left")
       # merged = merged.merge(matched_origin, on="County", how="left")
        #merged = merged.merge(matched_redeploy, on="County", how="left")
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
    ordered_cols = ["Function", "Total"] + [c for c in out.columns if c not in ["Function", "Total"]]
    return out[ordered_cols].sort_values("Total", ascending=False)


def build_beneficiary_link_table(df: pd.DataFrame, beneficiaries_df: pd.DataFrame) -> pd.DataFrame:
    if beneficiaries_df.empty:
        return pd.DataFrame(columns=[
            "County", "Program Short", "Area of Specialization", "Beneficiaries",
            "Origin Facility Matches", "Redeployment Facility Matches"
        ])

    facility_norms = set(df["Facility Normalized"].dropna().tolist())
    temp = beneficiaries_df.copy()
    temp["Origin Match"] = temp["Facility Origin Normalized"].isin(facility_norms).astype(int)
    temp["Redeployment Match"] = temp["Facility Redeployment Normalized"].isin(facility_norms).astype(int)

    summary = (
        temp.groupby(["County", "Program Short", "Area of Specialization"], dropna=False)
        .agg(
            Beneficiaries=("Beneficiary Name", pd.Series.nunique),
            Origin_Facility_Matches=("Origin Match", "sum"),
            Redeployment_Facility_Matches=("Redeployment Match", "sum"),
        )
        .reset_index()
        .sort_values(["County", "Program Short", "Beneficiaries"], ascending=[True, True, False])
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
                "font_color": "#FFFFFF",
                "fg_color": "#0F766E",
                "border": 1,
            })
            number_fmt = workbook.add_format({"num_format": "#,##0.00"})
            integer_fmt = workbook.add_format({"num_format": "#,##0"})

            for col_num, value in enumerate(df_sheet.columns.values):
                worksheet.write(0, col_num, value, header_fmt)

                if not df_sheet.empty:
                    series = df_sheet.iloc[:, col_num]
                    try:
                        content_max = series.fillna("").astype("string").str.len().max()
                    except Exception:
                        content_max = series.astype(str).str.len().max()
                    content_max = int(content_max) if pd.notna(content_max) else 10
                else:
                    series = pd.Series(dtype=object)
                    content_max = 10

                max_len = max(len(str(value)), content_max)
                width = min(max(max_len + 2, 12), 34)
                worksheet.set_column(col_num, col_num, width)

                if pd.api.types.is_numeric_dtype(series):
                    if (series.fillna(0) % 1 == 0).all():
                        worksheet.set_column(col_num, col_num, width, integer_fmt)
                    else:
                        worksheet.set_column(col_num, col_num, width, number_fmt)
    return output.getvalue()


@st.cache_data(show_spinner=False)
def load_shapefile_from_zip_bytes(file_bytes: bytes, file_name: str) -> gpd.GeoDataFrame:
    with tempfile.TemporaryDirectory() as tmpdir:
        zip_path = os.path.join(tmpdir, file_name)
        with open(zip_path, "wb") as f:
            f.write(file_bytes)
        extract_dir = os.path.join(tmpdir, "shape")
        os.makedirs(extract_dir, exist_ok=True)
        with zipfile.ZipFile(zip_path, "r") as zf:
            zf.extractall(extract_dir)

        shp_files = list(Path(extract_dir).rglob("*.shp"))
        if not shp_files:
            raise ValueError("No .shp file found inside the ZIP.")
        return gpd.read_file(shp_files[0])


@st.cache_data(show_spinner=False)
def load_bundled_shapefile() -> gpd.GeoDataFrame | None:
    shape_dir = Path(DEFAULT_SHAPEFILE_DIR)
    if not shape_dir.exists():
        return None

    shp_files = list(shape_dir.rglob("*.shp"))
    if shp_files:
        return gpd.read_file(shp_files[0])

    zip_files = list(shape_dir.rglob("*.zip"))
    if zip_files:
        zip_bytes = zip_files[0].read_bytes()
        return load_shapefile_from_zip_bytes(zip_bytes, zip_files[0].name)

    return None


def find_county_column(gdf: gpd.GeoDataFrame) -> str | None:
    candidates = [c for c in gdf.columns if c.lower() in {"county", "name", "county_nam", "county_name", "adm1_en", "adm2_en"}]
    if candidates:
        return candidates[0]
    obj_cols = [c for c in gdf.columns if gdf[c].dtype == "object"]
    return obj_cols[0] if obj_cols else None


def render_bar_chart(data: pd.DataFrame, category_col: str, value_col: str, title: str, color: str):
    if data.empty:
        st.info("No data available for this chart under the selected filters.")
        return
    fig, ax = plt.subplots(figsize=(8, 4))
    chart = data.sort_values(value_col, ascending=True).tail(10)
    ax.barh(chart[category_col], chart[value_col], color=color)
    ax.set_title(title)
    ax.set_xlabel(value_col)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    st.pyplot(fig, use_container_width=True)


def show_dataframe(df: pd.DataFrame, height=420):
    st.dataframe(df, use_container_width=True, height=height)


def render_map(county_summary: pd.DataFrame, measure: str, uploaded_shape):
    gdf = None
    source = None

    if uploaded_shape is not None:
        gdf = load_shapefile_from_zip_bytes(uploaded_shape.getvalue(), uploaded_shape.name)
        source = "uploaded shapefile"
    else:
        gdf = load_bundled_shapefile()
        source = "bundled shapefile" if gdf is not None else None

    if gdf is None:
        st.warning("No bundled shapefile was found. Upload a ZIP containing .shp, .shx, .dbf, and .prj files, or add your shapefile into the deployment package under the shapefiles folder.")
        return

    county_col = find_county_column(gdf)
    if county_col is None:
        st.error("Could not detect a county-name column in the shapefile.")
        return

    map_df = county_summary[["County", "Total"]].copy()
    gdf = gdf.copy()
    gdf["County_join"] = gdf[county_col].astype(str).apply(normalize_county_name)
    merged = gdf.merge(map_df, left_on="County_join", right_on="County", how="left")
    merged["Total"] = merged["Total"].fillna(0)

    fig, ax = plt.subplots(figsize=(10, 10))
    merged.plot(
        column="Total",
        cmap="viridis",
        linewidth=0.8,
        edgecolor="white",
        legend=True,
        ax=ax,
        missing_kwds={"color": "#d1d5db", "label": "No data"},
    )
    ax.set_title(f"County totals by {measure} ({source})", fontsize=14)
    ax.axis("off")
    st.pyplot(fig, use_container_width=True)

    st.markdown('<div class="section-card">', unsafe_allow_html=True)
    st.subheader("Map join preview")
    show_dataframe(merged[[county_col, "County_join", "Total"]].drop_duplicates(), height=300)
    st.markdown("</div>", unsafe_allow_html=True)


def main():
    inject_styles()
    st.title("Kenya Health Data Analyzer")
    st.caption("Color-coded dashboard with beneficiary integration, county and facility filters, downloads, and optional bundled Kenya county shapefiles.")

    with st.sidebar:
        st.header("Data")
        uploaded_main = st.file_uploader("Upload resource dataset", type=["xlsx", "xls", "csv"])
        uploaded_beneficiaries = st.file_uploader("Upload beneficiary dataset", type=["xlsx", "xls", "csv"])
        uploaded_shape = st.file_uploader("Upload shapefile ZIP (optional)", type=["zip"])

        measure = st.selectbox(
            "Measure",
            options=["Total Cost KES", "Total Cost USD", "Total Quantity Annually"],
            index=0,
        )

    if uploaded_main is not None:
        main_df = load_main_data_from_bytes(uploaded_main.getvalue(), uploaded_main.name)
        main_source = uploaded_main.name
    else:
        main_df = load_default_main_data()
        main_source = DEFAULT_DATA_PATH if not main_df.empty else "No resource file loaded"

    if main_df.empty:
        st.warning("Upload the resource dataset or place updated_with_function.xlsx beside app.py.")
        st.stop()

    if uploaded_beneficiaries is not None:
        ben_df = load_beneficiary_data_from_bytes(uploaded_beneficiaries.getvalue(), uploaded_beneficiaries.name, main_df)
        ben_source = uploaded_beneficiaries.name
    else:
        ben_df = load_default_beneficiary_data(main_df)
        ben_source = DEFAULT_BENEFICIARY_PATH if not ben_df.empty else "No beneficiary file loaded"

    with st.sidebar:
        st.header("Filters")
        county_options = sorted(main_df["County"].dropna().unique().tolist())
        selected_counties = st.multiselect("County", county_options, default=[])

        facility_options = get_facilities_for_counties(main_df, selected_counties)
        selected_facilities = st.multiselect("Facility", facility_options, default=[])

        page = st.radio(
            "Go to",
            [
                "Overview",
                "Area Summary",
                "County Summary",
                "Function Summary",
                "Map",
                "Downloads",
            ],
        )

    filtered_main, filtered_ben = apply_filters(main_df, ben_df, selected_counties, selected_facilities)

    area_summary = build_area_summary(filtered_main, filtered_ben, measure)
    county_summary = build_county_summary(filtered_main, filtered_ben, measure)
    function_summary = build_function_summary(filtered_main, measure)
    beneficiary_link_table = build_beneficiary_link_table(filtered_main, filtered_ben)

    if page == "Overview":
        c1, c2, c3 = st.columns(4)
        c1.metric("Resource Rows", f"{len(filtered_main):,}")
        c2.metric("Counties", f"{filtered_main['County'].nunique():,}")
        c3.metric("Facilities", f"{filtered_main['Facility Display'].nunique():,}")
        c4.metric(f"Total {measure}", f"{filtered_main[measure].sum():,.2f}")
       

        if not filtered_ben.empty:
            b1, b2, b3 = st.columns(4)
            b1.metric("Beneficiaries", f"{filtered_ben['Beneficiary Name'].nunique():,}")
            b2.metric("Beneficiary Counties", f"{filtered_ben['County'].nunique():,}")
            b3.metric("Origin Matches", f"{beneficiary_link_table['Origin_Facility_Matches'].sum():,}" if not beneficiary_link_table.empty else "0")
            b4.metric("Redeployment Matches", f"{beneficiary_link_table['Redeployment_Facility_Matches'].sum():,}" if not beneficiary_link_table.empty else "0")

        left, right = st.columns([1.2, 1])
        with left:
            st.markdown('<div class="section-card">', unsafe_allow_html=True)
            st.subheader("Loaded sources")
            st.write(f"Resource source: **{main_source}**")
            st.write(f"Beneficiary source: **{ben_source}**")
            show_dataframe(filtered_main[["County", "Facility Display", "Program", "Item_Type", "Item_Name", measure]].head(200), height=320)
            st.markdown("</div>", unsafe_allow_html=True)

        with right:
            st.markdown('<div class="section-card">', unsafe_allow_html=True)
            st.subheader("Top counties")
            render_bar_chart(county_summary, "County", "Total", f"Top counties by {measure}", "#0f766e")
            st.markdown("</div>", unsafe_allow_html=True)

            st.markdown('<div class="section-card">', unsafe_allow_html=True)
            st.subheader("Top areas")
            render_bar_chart(area_summary, "Area of Specialization", "Total", f"Top areas by {measure}", "#2563eb")
            st.markdown("</div>", unsafe_allow_html=True)

    elif page == "Area Summary":
        st.markdown('<div class="section-card">', unsafe_allow_html=True)
        st.subheader("Summary by Area of Specialization")
        st.write("Shows total value, split by Equipment, Drug, Supply, and Infrastructure, plus beneficiary counts and county coverage.")
        show_dataframe(area_summary, height=420)
        st.markdown("</div>", unsafe_allow_html=True)

    elif page == "County Summary":
        st.markdown('<div class="section-card">', unsafe_allow_html=True)
        st.subheader("Summary by County")
        st.write("Includes county totals, item-type splits, facility counts, beneficiary totals, program beneficiary counts, and area beneficiary counts.")
        show_dataframe(county_summary, height=520)
        st.markdown("</div>", unsafe_allow_html=True)

        st.markdown('<div class="section-card">', unsafe_allow_html=True)
        st.subheader("Beneficiary linkage table")
        show_dataframe(beneficiary_link_table, height=380)
        st.markdown("</div>", unsafe_allow_html=True)

    elif page == "Function Summary":
        st.markdown('<div class="section-card">', unsafe_allow_html=True)
        st.subheader("Equipment by Function")
        st.write("Functions include Monitoring, Screening & Diagnostics, and Management. Existing function values are used first; blank values fall back to keyword-based categorization.")
        show_dataframe(function_summary, height=320)
        st.markdown("</div>", unsafe_allow_html=True)

        st.markdown('<div class="section-card">', unsafe_allow_html=True)
        st.subheader("Equipment preview")
        equipment_only = filtered_main[filtered_main["Item_Type"].eq("Equipment")][["County", "Facility Display", "Program", "Item_Name", "Function", measure]]
        show_dataframe(equipment_only, height=360)
        st.markdown("</div>", unsafe_allow_html=True)

    elif page == "Map":
        st.markdown('<div class="section-card">', unsafe_allow_html=True)
        st.subheader("Kenya county map")
        st.write("The app will first try to use a bundled shapefile inside the deployment package. If not found, it will use an uploaded ZIP shapefile.")
        render_map(county_summary, measure, uploaded_shape)
        st.markdown("</div>", unsafe_allow_html=True)

    elif page == "Downloads":
        st.markdown('<div class="section-card">', unsafe_allow_html=True)
        st.subheader("Downloadable summaries")
        excel_bytes = to_excel_bytes({
            "Area Summary": area_summary,
            "County Summary": county_summary,
            "Function Summary": function_summary,
            "Beneficiary Links": beneficiary_link_table,
            "Filtered Resources": filtered_main,
            "Filtered Beneficiaries": filtered_ben,
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
        st.markdown("</div>", unsafe_allow_html=True)


if __name__ == "__main__":
    main()
