import requests

BASE_URL = "http://127.0.0.1:5000"

def test_flow():
    session = requests.Session()
    
    print("1. Testing health endpoint...")
    resp = session.get(f"{BASE_URL}/health")
    print(f"Health status: {resp.status_code}, data: {resp.json()}")
    
    print("\n2. Generating random email...")
    resp = session.post(f"{BASE_URL}/generate/random", json={"length": 10})
    if resp.status_code == 200:
        email = resp.json().get("email")
        print(f"Generated email: {email}")
    else:
        print(f"Failed to generate email: {resp.status_code}, {resp.text}")
        return

    print("\n3. Checking inbox (should be empty but work)...")
    resp = session.get(f"{BASE_URL}/inbox")
    if resp.status_code == 200:
        data = resp.json()
        print(f"Inbox for {data.get('email')}: {len(data.get('messages', []))} messages")
    else:
        print(f"Failed to check inbox: {resp.status_code}, {resp.text}")

    print("\n4. Testing multi-session isolation (simulated)...")
    session2 = requests.Session()
    resp2 = session2.post(f"{BASE_URL}/generate/random", json={"length": 12})
    email2 = resp2.json().get("email")
    print(f"Session 2 email: {email2}")
    
    if email == email2:
        print("CRITICAL: Sessions are sharing the same email! (Wait, 1secmail might gen same? unlikely with random 10 vs 12 chars)")
    else:
        print("Success: Sessions have different emails.")

if __name__ == "__main__":
    try:
        test_flow()
    except Exception as e:
        print(f"An error occurred: {e}")
