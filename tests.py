import requests
import geopandas as gpd
import json
import time

# Your existing lake dataset
lakes = gpd.read_parquet("bwca_lakes.parquet")
print(lakes[lakes["map_label"] == "Davis"].values.tolist())
# Only lakes that have a DNR LakeFinder ID
dowlknums = (
    lakes["dowlknum"]
    .dropna()
    .astype(str)
    .str.replace(".0", "", regex=False)
    .unique()
)

print("Lakes with DOWLKNUM:", len(dowlknums))

url = "https://maps.dnr.state.mn.us/cgi-bin/lakefinder/detail.cgi"

results = []
dowlknums = dowlknums[10:15]
for i, dowlknum in enumerate(dowlknums, start=1):

    params = {
        "type": "lake_survey",
        "id": dowlknum
    }

    try:
        response = requests.get(url, params=params, timeout=30)

        if response.status_code == 200:

            data = response.json()

            results.append({
                "dowlknum": dowlknum,
                "data": data
            })

            print(f"{i}/{len(dowlknums)}  {dowlknum}  OK")

        else:
            print(f"{i}/{len(dowlknums)}  {dowlknum}  HTTP {response.status_code}")

    except Exception as e:
        print(f"{i}/{len(dowlknums)}  {dowlknum}  ERROR: {e}")

    # Don't hammer the DNR server
    time.sleep(0.2)


print(json.dumps(results, indent=4))
# with open("lake_surveys_raw.json", "w") as f:
#     json.dump(results, f, indent=2)
#
# print("Finished")
# print("Saved:", len(results), "lake responses")