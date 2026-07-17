import requests

def test_device_is_reachable(device):
    resp = requests.get(f"{device}/health", timeout=2)
    assert resp.status_code == 200
    assert resp.json()["status"] == "alive"

def test_device_resets_to_default_framework(device):
    resp = requests.get(f"{device}/firmware_version", timeout=2)
    assert resp.status_code == 200
    assert resp.json()["firmware_version"] == "2.3.1"

def test_device_resets_to_default_battery(device):
    resp = requests.get(f"{device}/battery")
    assert resp.status_code == 200
    assert resp.json()["battery_pct"] == 87
