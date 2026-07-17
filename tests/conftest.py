"""Pytest auto-discovers this file and makes every fixture defined here
available to all tests in this directory without needing to import anything."""


import subprocess
import time
import sys
import os

import pytest
import requests

DEVICE_URL = "http://127.0.0.1:5050"


@pytest.fixture(scope="session")
def device_server():
    server_path = os.path.join(
        os.path.dirname(__file__),"..","device_server", "mock_device.py"
    )
    print(f"DEBUG: launching {sys.executable} {server_path}")
    proc = subprocess.Popen(
        [sys.executable, server_path],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text = True
    )

    # Poll until the server is actually ready instead of a blind sleep 
    # mirrors polling a real device for a "boot complete" signal.

    for _ in range(20):
        try:
            resp = requests.get(f"{DEVICE_URL}/health", timeout=0.5)
            print(f"DEBUG: got status {resp.status_code}")
            if resp.status_code == 200:
                break
        except requests.exceptions.ConnectionError:
            print(f"DEBUG: exception {type(e).__name__}: {e}")
            time.sleep(0.25)
            

    else:
        proc.terminate()
        output, _ = proc.communicate(timeout=5)
        raise RuntimeError(f"Mock device server failed to start in time.\nServer output:\n{output}")
    
    yield DEVICE_URL

    proc.terminate()
    proc.wait(timeout=5)


@pytest.fixture(scope="function")
def device(device_server):
    requests.post(f"{device_server}/reset",timeout=2)
    yield device_server

