"""
FailSense Mock Device Server
------------------------------
Simulates a consumer hardware device (think: smart plug / IoT sensor) exposing
a debug/service REST API, similar to what embedded devices expose for QA/lab
testing.

This is intentionally NOT a clean, well-behaved API. Real hardware in a lab
misbehaves: it's slow sometimes, it has firmware bugs, sensors drift, and
connections drop. We simulate that on purpose because our test suite and
triage engine need real failure signal to classify.

Run with: python mock_device.py
Server starts on http://localhost:5000
"""

import random
import time
from flask import Flask, jsonify, request

app = Flask(__name__)

device_state = {
    "battery_pct" : 87,
    "temp_celsius" : 24.5,
    "firmware_version" : "2.3.1",
    "boot_cout" : 1,
    "is_rebooting" : False 
}

SUPPORTED_FIRMWARE_VERSIONS = ["2.3.1", "2.3.2", "2.4.0-beta"]

# ---------------- INTENTIONAL BUG #1: KNOWN PRODUCT DEFECT ---------------- 
# On firmware 2.4.0-beta, the temperature sensor has a real firmware bug:
# above 45C it reports garbage instead of clamping or erroring consistently.
# This is a genuine, REPRODUCIBLE defect -> deterministic, not random.

BUGGY_FIRMWARE = "2.4.0-beta"

@app.route("/firmware_version", methods=["GET"])
def ger_firmware_version():
    return jsonify({"firmware_version": device_state["firmware_version"]})


@app.route("/set_firmware_version", methods=["POST"])
def set_firrmware_version():
    version = request.json.get("version")
    if version not in SUPPORTED_FIRMWARE_VERSIONS:
        return jsonify({"error": f"unsupported firmware {version}"}), 400
    device_state["firmware_version"] = version
    return jsonify({"firmware_version": device_state["firmware_version"]})


@app.route("/battery", methods=["GET"])
def get_battery():
    # ---------------- INTENTIONAL BUG #2: FLAKY / ENVIRONMENT ISSUE ----------------
    # Randomly slow response (simulates real lab noise: USB hub contention,
    # wifi congestion). Trips a timeout intermittently, not deterministically.
    if random.random() < 0.15:
        time.sleep(2.5)
    return jsonify({"battery_pct": device_state["battery_pct"]})


@app.route("/temp", methods = ["GET"])
def get_temp():
    fw = device_state['firmware_version']
    if fw == BUGGY_FIRMWARE and device_state["temp_celsius"] > 45:
        return jsonify({"temp_celsius": -999.9, "sensor_status": "error"})
    return jsonify({"temp_celsius": device_state["temp_celsius"], "sensor_status": "ok"})


@app.route("/set_temp", methods = ["POST"])
def set_temp():
    device_state["temp_celsius"] = request.json.get("temp_celsius", 24.5)
    return jsonify({"temp_celsius": device_state["temp_celsius"]})


@app.route("/reboot", methods=["POST"])
def reboot():
    device_state["is_rebooting"] = True
    device_state["boot_count"] += 1
    time.sleep(0.3)
    device_state["is_rebooting"] = False
    return jsonify({"status":"rebooted", "boot_count": device_state["boot_count"]})


@app.route("/reset", methods=["POST"])
def reset_device():
    device_state = {
        "battery_pct" : 87,
        "temp_celsius" : 24.5,
        "firmware_version" : "2.3.1",
        "boot_count" : 1,
        "is_rebooting" : False 
    }

    return jsonify({"state": "reset"})


@app.route("/health", methods=["GET"])
def health():
    return jsonify({"status": "alive"})


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5000, debug=False)




