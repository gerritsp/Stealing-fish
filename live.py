import requests

url = "https://enterprise.gisdata.mn.gov/aghost/rest/services/us_mn_state_dnr/env_lakes_surveyed_by_mndnr/MapServer/0/query"

params = {
    "where": "dowlknum = '38040400'",
    "outFields": "*",
    "returnGeometry": "true",
    "f": "json"
}

response = requests.get(url, params=params)
def print_filtered(data, skip_key="features"):
    if isinstance(data, dict):
        # Print everything except the target key
        filtered_dict = {
            k: print_filtered(v, skip_key) for k, v in data.items() if k != skip_key
        }
        return filtered_dict
    elif isinstance(data, list):
        # Recursively handle lists of items
        return [print_filtered(item, skip_key) for item in data]
    else:
        # Return primitive values (strings, numbers, etc.)
        return data
print(response.status_code)
print(list(response.json().keys()))
json_data = response.json()

# Filter and print the result cleanly
filtered_data = print_filtered(json_data)
print(filtered_data)
