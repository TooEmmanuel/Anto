# Kenya Health Data Analyzer

## What changed
- Added a color-styled dashboard
- Added County and Facility filters in the sidebar
- Keeps using both:
  - updated_with_function.xlsx
  - Book1.xlsx
- Supports a bundled shapefile in the deployment package so the map can load without re-uploading each time

## Important shapefile note
This package includes a shapefiles folder placeholder, but I could not embed your actual Kenya county shapefiles because they were not uploaded in this chat.

To make the map load automatically on Streamlit Community Cloud, put your shapefile into:
- shapefiles/kenya_counties.zip

Or place the extracted shapefile parts inside the shapefiles folder:
- .shp
- .shx
- .dbf
- .prj
