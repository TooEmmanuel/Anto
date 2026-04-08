# Kenya Health Data Analyzer (Streamlit)

## Included files
- `app.py` — main Streamlit app
- `requirements.txt` — Python dependencies
- `updated_with_function.xlsx` — default resource dataset
- `Book1.xlsx` — default beneficiary dataset
- `README_streamlit_app.md` — usage notes

## Run locally
```bash
pip install -r requirements.txt
streamlit run app.py
```

## What changed
This version fixes the beneficiary issue by using **Book1.xlsx** together with **updated_with_function.xlsx**.

### Beneficiary logic
- Uses **County** as the main join field
- Also normalizes and compares facilities between:
  - `Health_Facility` in the resource file
  - `Facility of origin` in the beneficiary file
  - `Facility of Redeployment` in the beneficiary file
- Maps beneficiary programs into **Area of Specialization** using the program-to-area relationships found in the resource dataset

## App pages
1. **Summary 1: Area of Specialization**
   - total amount
   - equipment
   - drugs
   - supplies
   - infrastructure
   - beneficiaries
   - county coverage

2. **Summary 2: County + Beneficiaries**
   - county total
   - equipment / drugs / supplies / infrastructure
   - program totals such as Peds Cardiology and Peds Endo
   - total beneficiaries
   - beneficiaries by area
   - beneficiaries by program
   - facility-origin and redeployment matches

3. **Summary 3: Equipment Function**
   - monitoring
   - screening & diagnostics
   - management

4. **Map**
   - upload Kenya county shapefile ZIP and plot county totals

5. **Downloads**
   - export Excel and CSV summary files

## Shapefile upload
Upload a `.zip` containing:
- `.shp`
- `.shx`
- `.dbf`
- `.prj`
