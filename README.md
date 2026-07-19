# FailSense

**Automated failure triage for hardware regression testing.**

FailSense is a Pytest-based test automation framework that simulates hardware-in-the-loop testing for a consumer device, then automatically classifies test failures as **flaky/environment**, **product defect**, or **possible test-infra bug** — the same triage decision a QA/automation engineer makes by hand when reviewing regression results.

```
Mock Device (Flask)  →  Pytest Regression Suite  →  Triage Classifier  →  HTML Report
                                    ↓
                          GitHub Actions CI (parallel + auto-retry)
```

## Why this exists

Most test automation demos stop at "tests pass or fail." In real hardware QA, that's the easy part — the actual job is figuring out *why* something failed: is the test flaky, is the device genuinely broken, or is the test itself wrong? FailSense builds a small, honest version of that triage pipeline end to end, including a mock device with **intentionally injected, realistic failure modes** so the classifier has real signal to work with.

## Architecture

**`device_server/mock_device.py`** — A Flask server simulating a consumer hardware device's debug/service API (`/battery`, `/temp`, `/firmware_version`, `/reboot`, `/reset`). It's deliberately unreliable in specific, designed ways:
- `/battery` randomly delays ~15% of requests, simulating lab environment noise (USB/WiFi contention)
- `/temp` has a genuine deterministic firmware bug: on firmware `2.4.0-beta`, readings above 45°C return garbage instead of a valid value — reproducible every time, on that firmware, under that condition

**`tests/conftest.py`** — Pytest fixtures managing the device lifecycle:
- `device_server` (session-scoped): starts the mock server once per test run — expensive to create, so it's created once
- `device` (function-scoped): resets device state before every test — cheap, and necessary to prevent test pollution between cases

**`tests/test_regression.py`** — A parametrized regression suite covering multiple firmware versions, with three intentional, distinguishable failure types:
| Test | Failure type | Signature |
|---|---|---|
| `test_battery_reading_is_valid` | Flaky / environment | Fails intermittently, passes on retry |
| `test_temp_sensor_under_extreme_heat` | Product defect | Fails identically every run, on specific firmware |
| `test_reboot_increments_boot_count_badly` | Test-infra bug | Device returns correct data; the test's expectation is wrong |

**`triage/classify.py`** — Parses `pytest-json-report` output and classifies each failure:
- Tests marked `@pytest.mark.flaky` → **Flaky/Environment** (high confidence — marker-driven, not guessed)
- Failures comparing device-reported status strings → **Product Defect** (medium confidence, heuristic)
- Failures comparing bare numeric values with no device-status signature → **Possible Test Bug** (low confidence, explicitly flagged for human review)

The classifier is intentionally conservative: only the flaky classification is high-confidence, because it's driven by an explicit human-set marker. Separating a real defect from a wrong test assumption from message text alone is a genuine judgment call — the tool flags that honestly instead of overclaiming certainty.

**`triage/report.py`** — Renders the classification result as a clean HTML report (stat summary, proportional failure breakdown, per-failure detail cards with confidence levels).

**`.github/workflows/ci.yml`** — Runs the full pipeline on every push: pytest (parallel via `pytest-xdist`, auto-retry via `pytest-rerunfailures`) → classify → generate report → upload as a downloadable CI artifact.

## Running it locally

```bash
python -m venv venv && source venv/bin/activate
pip install -r requirements.txt

# Run the regression suite
python -m pytest tests/test_regression.py -v

# Generate a structured report
python -m pytest tests/test_regression.py --json-report --json-report-file=reports/last_run.json
python triage/classify.py reports/last_run.json
python triage/report.py reports/triage_result.json
open reports/triage_report.html   # macOS
```

## Debugging notes worth mentioning

A few real bugs surfaced while building this, each a small lesson in its own right:

- **macOS AirPlay Receiver squats on port 5000 by default.** The mock server originally ran on port 5000; requests were silently intercepted by `AirTunes`, returning `403 Forbidden` instead of reaching Flask. Diagnosed via `curl -v` and the `Server: AirTunes` response header. Fixed by moving the server to port 5050 — a more portable fix than relying on a system setting, since it doesn't depend on the developer's OS config.
- **A `for...else` loop silently masked a startup failure.** The `device_server` fixture polled for server readiness inside a `try/except requests.exceptions.ConnectionError`, but the real failure mode was a `403`, not a connection error — so every poll "succeeded" at the HTTP level while never getting a 200, and the loop ran to completion into its `else` clause with no useful error message. Widening the exception handling and logging the actual response surfaced the real cause immediately.
- **Reassigning a global dict inside a function silently created a local variable instead.** The `/reset` endpoint did `device_state = {...}` inside `reset_device()`, which — per normal Python scoping rules — created a new local variable and left the module-level `device_state` untouched. The endpoint returned a clean `200 OK` every time, but device state never actually reset, causing flaky-looking cross-test contamination. Fixed with `device_state.update({...})` to mutate the existing object in place.

## Tech stack

Python, Pytest, Flask, `pytest-html`, `pytest-xdist`, `pytest-rerunfailures`, `pytest-json-report`, GitHub Actions.