import pandas as pd

missing = pd.read_parquet(
    "fisheries/dnr_no_data_with_arcgis_surveys.parquet"
)

print("Lake features:", len(missing))
print("Unique DOW lakes:", missing["dowlknum"].nunique())
print("Columns:", missing.columns.tolist())

print(missing.head(10).to_string())