import requests

API_KEY = "BA7BE33B-DA56-4F0A-8DF9-2E7DDDC3D6B7"
BASE_URL = "https://api.neynar.com"

headers = {
    "x-api-key": API_KEY,
    "Content-Type": "application/json"
}

def lookup_user(username: str):
    url = f"{BASE_URL}/v2/farcaster/user/by-username"
    params = {"username": username}
    resp = requests.get(url, headers=headers, params=params)
    resp.raise_for_status()
    return resp.json()

if __name__ == "__main__":
    username = "example.base.eth"  # replace with real
    user_info = lookup_user(username)
    print("User info:", user_info)