import requests
import json

url = "https://maps.dnr.state.mn.us/cgi-bin/lakefinder/detail.cgi"

params = {
    "type": "lake_survey",
    "id": "38040400"
}

response = requests.get(url, params=params)

print(response.status_code)

data = response.json()

print(json.dumps(data, indent=2)[:5000])