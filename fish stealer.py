import json
import time
from pathlib import Path

import pandas as pd
import requests


# ============================================================
# PATHS
# ============================================================

LAKES_FILE = Path("bwca_lakes.parquet")

OUTPUT_DIR = Path("fisheries")
RAW_DIR = OUTPUT_DIR / "raw"

OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
RAW_DIR.mkdir(parents=True, exist_ok=True)


# ============================================================
# DNR API
# ============================================================

API_URL = "https://maps.dnr.state.mn.us/cgi-bin/lakefinder/detail.cgi"


# ============================================================
# SETTINGS
# ============================================================

REQUEST_DELAY = 0.25

# True = download lakes that do not already have a raw JSON file
# False = don't download anything; only parse existing JSON
DOWNLOAD_DATA = True


# ============================================================
# GET DOWLKNUMS
# ============================================================

lakes = pd.read_parquet(LAKES_FILE)

dowlknums = (
    lakes["dowlknum"]
    .dropna()
    .astype(str)
    .str.replace(r"\.0$", "", regex=True)
    .unique()
)

print(f"Lakes with DOWLKNUM: {len(dowlknums)}")


# ============================================================
# DOWNLOAD RAW JSON
# ============================================================

def download_lake(dowlknum):
    """
    Download one lake's LakeFinder response and save it locally.
    """

    raw_file = RAW_DIR / f"{dowlknum}.json"

    # Don't download it again if we already have it
    if raw_file.exists():
        return "cached"

    params = {
        "type": "lake_survey",
        "id": dowlknum
    }

    try:
        response = requests.get(
            API_URL,
            params=params,
            timeout=30
        )

        response.raise_for_status()

        data = response.json()

        with open(raw_file, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)

        return "downloaded"

    except Exception as e:
        print(f"ERROR {dowlknum}: {e}")

        error_file = OUTPUT_DIR / "download_errors.txt"

        with open(error_file, "a", encoding="utf-8") as f:
            f.write(f"{dowlknum}\t{e}\n")

        return "error"


# ============================================================
# DOWNLOAD ALL LAKES
# ============================================================

if DOWNLOAD_DATA:

    total = len(dowlknums)

    for i, dowlknum in enumerate(dowlknums, start=1):

        status = download_lake(dowlknum)

        print(f"{i}/{total}  {dowlknum}  {status}")

        if status == "downloaded":
            time.sleep(REQUEST_DELAY)


# ============================================================
# PARSE DATA
# ============================================================

lake_info = []
surveys = []
fish_catches = []
fish_lengths = []
water_clarity = []
accesses = []
plants = []

no_data = []
errors = []


# ============================================================
# HELPER
# ============================================================

def clean_number(value):
    """
    Convert numeric strings to numbers where possible.
    Keep things like 'N/A' as None.
    """

    if value is None:
        return None

    if isinstance(value, (int, float)):
        return value

    try:
        return float(value)
    except (ValueError, TypeError):
        return None


# ============================================================
# READ RAW JSON FILES
# ============================================================

raw_files = sorted(RAW_DIR.glob("*.json"))

print()
print(f"Parsing {len(raw_files)} cached responses...")
print()


for i, raw_file in enumerate(raw_files, start=1):

    dowlknum = raw_file.stem

    try:

        with open(raw_file, "r", encoding="utf-8") as f:
            data = json.load(f)

        status = data.get("status")

        # ----------------------------------------------------
        # NO DATA
        # ----------------------------------------------------

        if status != "SUCCESS" or data.get("result") is None:

            no_data.append({
                "dowlknum": dowlknum,
                "status": status,
                "message": data.get("message")
            })

            continue

        result = data["result"]

        # ----------------------------------------------------
        # LAKE INFO
        # ----------------------------------------------------

        lake_info.append({
            "dowlknum": dowlknum,
            "lake_name": result.get("lakeName"),
            "mean_depth_ft": clean_number(
                result.get("meanDepthFeet")
            ),
            "max_depth_ft": clean_number(
                result.get("maxDepthFeet")
            ),
            "area_acres": clean_number(
                result.get("areaAcres")
            ),
            "littoral_acres": clean_number(
                result.get("littoralAcres")
            ),
            "shoreline_miles": clean_number(
                result.get("shoreLengthMiles")
            ),
            "county": result.get("county"),
            "office_code": result.get("officeCode"),
            "average_water_clarity_ft": clean_number(
                result.get("averageWaterClarity")
            )
        })

        # ----------------------------------------------------
        # WATER CLARITY
        # ----------------------------------------------------

        for measurement in result.get("waterClarity", []):

            if len(measurement) < 2:
                continue

            water_clarity.append({
                "dowlknum": dowlknum,
                "date": measurement[0],
                "clarity_ft": clean_number(measurement[1])
            })

        # ----------------------------------------------------
        # ACCESSES
        # ----------------------------------------------------

        for access in result.get("accesses", []):

            accesses.append({
                "dowlknum": dowlknum,
                "location": access.get("location"),
                "access_type": access.get("accessTypeId"),
                "public_use_authorization": access.get(
                    "publicUseAuthCode"
                ),
                "owner_type": access.get("ownerTypeId"),
                "comments": access.get("lakeAccessComments")
            })

        # ----------------------------------------------------
        # PLANTS
        # ----------------------------------------------------

        for plant in result.get("sampledPlants", []):

            plants.append({
                "dowlknum": dowlknum,
                "plant": plant
            })

        # ----------------------------------------------------
        # SURVEYS
        # ----------------------------------------------------

        for survey in result.get("surveys", []):

            header = survey.get("headerInfo", {})

            survey_id = (
                survey.get("surveyID")
                or header.get("survey_id")
            )

            survey_date = (
                survey.get("surveyDate")
                or header.get("id_date")
            )

            survey_type = (
                survey.get("surveyType")
                or header.get("survey_type")
            )

            survey_subtype = survey.get("surveySubType")

            # -----------------------------------------------
            # SURVEY TABLE
            # -----------------------------------------------

            surveys.append({
                "dowlknum": dowlknum,
                "survey_id": survey_id,
                "survey_date": survey_date,
                "survey_type": survey_type,
                "survey_subtype": survey_subtype,
                "lake_name": header.get("wb_name"),
                "county": header.get("county"),
                "narrative": survey.get("narrative")
            })

            # -----------------------------------------------
            # FISH CATCH
            # -----------------------------------------------

            for catch in survey.get(
                "fishCatchSummaries", []
            ):

                fish_catches.append({
                    "dowlknum": dowlknum,
                    "survey_id": survey_id,
                    "survey_date": survey_date,
                    "species": catch.get("species"),
                    "gear": catch.get("gear"),
                    "gear_count": catch.get("gearCount"),
                    "total_catch": catch.get("totalCatch"),
                    "cpue": clean_number(
                        catch.get("CPUE")
                    ),
                    "average_weight": clean_number(
                        catch.get("averageWeight")
                    ),
                    "total_weight": clean_number(
                        catch.get("totalWeight")
                    ),
                    "quartile_weight": catch.get(
                        "quartileWeight"
                    ),
                    "quartile_count": catch.get(
                        "quartileCount"
                    )
                })

            # -----------------------------------------------
            # FISH LENGTHS
            # -----------------------------------------------

            lengths = survey.get("lengths", {})

            for species, species_data in lengths.items():

                for fish_count in species_data.get(
                    "fishCount", []
                ):

                    if len(fish_count) < 2:
                        continue

                    fish_length = fish_count[0]
                    count = fish_count[1]

                    fish_lengths.append({
                        "dowlknum": dowlknum,
                        "survey_id": survey_id,
                        "survey_date": survey_date,
                        "species": species,
                        "length_inches": fish_length,
                        "fish_count": count
                    })

    except Exception as e:

        errors.append({
            "dowlknum": dowlknum,
            "error": str(e)
        })

    print(f"Parsed {i}/{len(raw_files)}  {dowlknum}")


# ============================================================
# SAVE PARQUETS
# ============================================================

print()
print("Writing Parquet files...")
print()


def save_parquet(data, filename):
    """
    Save a list of dictionaries as a Parquet file.
    """

    df = pd.DataFrame(data)

    path = OUTPUT_DIR / filename

    df.to_parquet(path, index=False)

    print(f"{filename}: {len(df):,} rows")


save_parquet(
    lake_info,
    "dnr_lake_info.parquet"
)

save_parquet(
    surveys,
    "dnr_surveys.parquet"
)

save_parquet(
    fish_catches,
    "dnr_fish_catches.parquet"
)

save_parquet(
    fish_lengths,
    "dnr_fish_lengths.parquet"
)

save_parquet(
    water_clarity,
    "dnr_water_clarity.parquet"
)

save_parquet(
    accesses,
    "dnr_accesses.parquet"
)

save_parquet(
    plants,
    "dnr_plants.parquet"
)

save_parquet(
    no_data,
    "dnr_no_data.parquet"
)

save_parquet(
    errors,
    "dnr_errors.parquet"
)


print()
print("Finished.")
print()
print(f"Raw JSON files: {len(raw_files)}")
print(f"Lakes with data: {len(lake_info)}")
print(f"No-data lakes: {len(no_data)}")
print(f"Errors: {len(errors)}")