import requests

BASE_URL = 'http://localhost:8000'

# Ensure user exists (using form-data since it is str = Form(...))
reg_resp = requests.post(f'{BASE_URL}/register', data={'email': 'john@example.com', 'password': 'password123', 'name': 'John Store'})
print(f"Registration: {reg_resp.status_code}")

# Login (OAuth2PasswordRequestForm is also form-data)
auth_resp = requests.post(f'{BASE_URL}/token', data={'username': 'john@example.com', 'password': 'password123'})
if auth_resp.status_code != 200:
    print(f"Login failed: {auth_resp.text}")
    exit(1)
    
token = auth_resp.json()['access_token']
headers = {'Authorization': f'Bearer {token}'}

# Upload Excel
with open('data/supply_chain_dataset.xlsx', 'rb') as f:
    r = requests.post(
        f'{BASE_URL}/upload-data', 
        files={'csv_file': ('data.xlsx', f, 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')}, 
        headers=headers
    )
    print(f"Upload Status: {r.status_code}")

# Check Dashboard Meta
meta_r = requests.get(f'{BASE_URL}/dashboard-meta', headers=headers)
print(f"Dashboard Meta: {meta_r.json()}")
