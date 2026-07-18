"""
Core regression suite: runs the same checks across multiple firmware
versions and device conditions, mirroring how consumer hardware QA teams
validate a build across supported configurations before release.

Includes THREE intentional failure types, each with a distinct signature,
so the triage engine has real, distinguishable
failures to classify:

  1. FLAKY / ENVIRONMENT   -> test_battery_reading_is_valid
     Caused by the mock server's random slow-response injection on /battery.
     Fails intermittently. Retrying often passes. This is the signature of
     a flaky/environment issue, not a real product defect.

  2. PRODUCT DEFECT        -> test_temp_sensor_under_extreme_heat
     Caused by the deterministic firmware bug in mock_device.py's /temp
     endpoint (garbage reading above 45C on 2.4.0-beta). Fails the SAME
     way every single time, on that specific firmware. This is a real,
     reproducible defect.

  3. TEST-INFRA BUG        -> test_reboot_increments_boot_count_badly
     A genuinely wrong assertion in the TEST ITSELF (expects the wrong
     value). This fails every run, on every firmware, regardless of
     device behavior - the device is fine, the test is broken. This is
     the "the test itself is wrong" category, distinct from a flaky test
     and distinct from a product defect.
"""


import pytest
import requests

DEVICE_URL = "http://127.0.0.1:5050"

FIRMWARE_VERSIONS = ["2.3.1", "2.3.2", "2.4.0-beta"]



def set_firmware(device, version):
    requests.post(f"{device}/set_firmware_version", json={"version":version}, timeout=2)


# ---------------------------------------------------------------------------
# SMOKE TESTS - fast, run on every commit
# ---------------------------------------------------------------------------

@pytest.mark.smoke
def test_device_health_check(device):
    resp = requests.get(f"{device}/health", timeout=2)
    assert resp.status_code == 200

@pytest.mark.smoke
@pytest.mark.parametrize("version", FIRMWARE_VERSIONS)
def test_firmware_version_can_be_set(device, version):
    resp = requests.post(
        f"{device}/set_firmware_version", 
        json={"version":version},
        timeout = 2
    )

    assert resp.status_code == 200
    assert resp.json()["firmware_version"] == version



# ---------------------------------------------------------------------------
# REGRESSION SUITE - full coverage across firmware variants
# ---------------------------------------------------------------------------


@pytest.mark.regression
@pytest.mark.parametrize("version",FIRMWARE_VERSIONS)
def test_temp_sensor_normal_range_all_firmware(device,version):
    set_firmware(device,version)
    resp = requests.get(f"{device}/temp", timeout=2)
    base = resp.json()
    assert base['sensor_status'] == "ok"
    assert 0<= base['temp_celsius'] <= 45


@pytest.mark.regression
@pytest.mark.flaky
def test_battery_reading_is_valid(device):
    """
    INTENTIONAL FLAKY TEST.
    The mock server randomly delays /battery ~15% of the time past our
    short timeout. This should fail intermittently - a real signature of
    environment/infra flakiness, not a device defect.
    """
    resp = requests.get(f"{device}/battery", timeout=1)
    assert resp.status_code == 200
    assert 0 <= resp.json()["battery_pct"] <= 100


@pytest.mark.regression
def test_temp_sensor_under_extreme_heat(device):
    """
    INTENTIONAL PRODUCT DEFECT.
    Firmware 2.4.0-beta has a real bug: above 45C the sensor reports
    garbage (-999.9) instead of a valid reading or clean error state.
    This SHOULD fail, consistently, every run, on this firmware only -
    that consistency is what makes it a defect, not a flaky test.
    """
    set_firmware(device, "2.4.0-beta")
    requests.post(f"{device}/set_temp", json={"temp_celsius": 50}, timeout=2)
    resp = requests.get(f"{device}/temp", timeout=2)
    body = resp.json()
    assert body["sensor_status"] == "ok"
    assert 0 <= body["temp_celsius"] <= 100


@pytest.mark.regression
def test_reboot_increments_boot_count_badly(device):
    """
    INTENTIONAL TEST-INFRA BUG (the test itself is wrong, not the device).
    Device starts at boot_count=1 after reset. After one reboot it should
    be 2. This test WRONGLY asserts it should be 5 - a bad test author
    assumption, not a device problem. Fails every run, every firmware,
    deterministically - but the fix is to correct the TEST, not the device.
    """
    resp = requests.post(f"{device}/reboot", timeout=3)
    assert resp.json()["boot_count"] == 5  # WRONG on purpose