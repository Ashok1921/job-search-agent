import os
import requests
from dotenv import load_dotenv

load_dotenv()

RAPIDAPI_KEY = os.getenv("RAPIDAPI_KEY")

url = "https://jsearch.p.rapidapi.com/search-v2"

querystring = {
    "query": "Generative AI Developer in Hyderabad",
    "country": "in"
}

headers = {
    "X-RapidAPI-Key": RAPIDAPI_KEY,
    "X-RapidAPI-Host": "jsearch.p.rapidapi.com"
}

response = requests.get(url, headers=headers, params=querystring)

import json

if response.status_code == 200:
    data = response.json()
    jobs = data.get("data", {}).get("jobs", [])
    print(f"Found {len(jobs)} jobs:\n")
    for job in jobs:
        print(f"Title:    {job.get('job_title')}")
        print(f"Company:  {job.get('employer_name')}")
        print(f"Location: {job.get('job_city')}, {job.get('job_country')}")
        print(f"Apply:    {job.get('job_apply_link')}")
        print("-" * 60)
    print("Next cursor:", data.get("data", {}).get("cursor"))
else:
    print(f"Error {response.status_code}: {response.text}")