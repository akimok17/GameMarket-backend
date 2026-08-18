"""End-to-end smoke test. Run against a local server: python scripts/smoke_test.py"""
import json
import urllib.request
import urllib.error

BASE = "http://127.0.0.1:8000"


def req(path, method="GET", body=None, token=None):
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    data = json.dumps(body).encode() if body is not None else None
    request = urllib.request.Request(BASE + path, data=data, headers=headers, method=method)
    with urllib.request.urlopen(request) as response:
        return json.loads(response.read().decode())


print("health:", req("/health"))
print("Smoke endpoint is reachable. Use /docs for the full API test flow.")
