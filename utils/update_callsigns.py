import html_to_json
import requests

pages = [
    "/call-signs/A",
    "/call-signs/B",
    "/call-signs/C",
    "/call-signs/D",
    "/call-signs/E",
    "/call-signs/F",
    "/call-signs/G",
    "/call-signs/H",
    "/call-signs/I",
    "/call-signs/J",
    "/call-signs/K",
    "/call-signs/L",
    "/call-signs/M",
    "/call-signs/N",
    "/call-signs/O",
    "/call-signs/P",
    "/call-signs/Q",
    "/call-signs/R",
    "/call-signs/S",
    "/call-signs/T",
    "/call-signs/U",
    "/call-signs/V",
    "/call-signs/W",
    "/call-signs/X",
    "/call-signs/Y",
    "/call-signs/Z"
]
web = "https://123atc.com"

import json

all_data = []
for page in pages:
    url = web + page
    html_string = requests.get(url).text
    tables = html_to_json.convert_tables(html_string)
    
    if tables and isinstance(tables, list):
        print(f"Found {len(tables[0])} tables on page {page}")
        for table in tables[0]:
            if isinstance(table, dict):
                all_data.append(table)

with open('database/callsigns.json', 'w') as f:
    json.dump(all_data, f, indent=4)

callsign_dict = {}

for entry in all_data:
    if isinstance(entry, dict) and '3-Letter ID' in entry:
        three_letter_id = entry['3-Letter ID']
        callsign_dict[three_letter_id] = {
            'Callsign': entry.get('Call Sign', 'null'),
            'Company': entry.get('Company', 'null'),
            'Country': entry.get('Country', 'null')
        }

with open('database/callsigns_dict.json', 'w') as f:
    json.dump(callsign_dict, f, indent=4)
