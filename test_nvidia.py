import os
import httpx
from dotenv import load_dotenv

load_dotenv()
nvidia_key = os.getenv("NVIDIA_API_KEY")

if not nvidia_key:
    print("NVIDIA API key missing.")
    exit(1)

headers = {
    "Authorization": f"Bearer {nvidia_key}",
    "Accept": "application/json"
}
url = "https://integrate.api.nvidia.com/v1/models"
resp = httpx.get(url, headers=headers)
print(f"Status: {resp.status_code}")
try:
    models = resp.json().get("data", [])
    for m in models:
        print(f"Model: {m['id']}")
except Exception as e:
    print(f"Error parsing JSON: {resp.text}")
