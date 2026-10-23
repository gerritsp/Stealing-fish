import requests
import json

url = "https://maps.dnr.state.mn.us/cgi-bin/lakefinder/detail.cgi"

params = {
    "type": "lake_survey",
    "id": "18003800"
}

response = requests.get(url, params=params)

print(response.status_code)

data = response.json()

with open("test_fish.json", "w") as f:
    json.dump(data, f, indent=4)

print("Saved!")