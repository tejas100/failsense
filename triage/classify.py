"""
FailSense Triage Engine.

Reads a pytest-json-report output file and classifies every failed test
into one of three categories:

  - FLAKY_ENVIRONMENT     : test is marked @pytest.mark.flaky. High confidence -
                             this is a known, intentionally-tagged environment
                             sensitivity, not something we're guessing at.

  - PRODUCT_DEFECT        : failure message pattern suggests the DEVICE
                             returned bad/unexpected data (a real defect).
                             Medium confidence - heuristic based on message
                             shape, not certainty.

  - POSSIBLE_TEST_BUG     : failure message pattern suggests a hardcoded/
                             magic-number expectation with no clear device-data
                             signature. Medium confidence, explicitly flagged
                             for human review rather than auto-trusted.

Design principle: only the flaky classification is "confident" because it's
driven by an explicit marker a human QA engineer set. The defect vs
test-bug split is inherently a judgment call from message text alone, so
that tier is intentionally conservative and flagged for review rather than
asserted as fact. This mirrors how real triage works - some signal is
strong (rerun/marker-based), some requires human judgment.

Usage:
    python triage/classify.py reports/last_run.json
"""

import json
import re
import sys
from pathlib import Path
from collections import Counter


ANSI_ESCAPE = re.compile(r"\x1b\[[0-9;]*m")

def strip_ansi(text):
    return ANSI_ESCAPE.sub("", text)


def load_report(path):
    with open(path) as f:
        return json.load(f)


def classify_test(test):
    """Returns a dictionary with classification + reasoning for one failed test."""

    nodeid = test["nodeid"]
    keywords = test.get("keywords",[])
    crash_message = strip_ansi(test.get("call", {}).get("crash", {}).get("message", ""))


    # Tier 1: marker-driven, high confidence
    if "flaky" in keywords:
        return {
            "nodeid": nodeid,
            "category": "FLAKY_ENVIRONMENT",
            "confidence": "high",
            "reason": "Test is tagged @pytest.mark.flaky - known environment-sensitive test.",
            "message": crash_message,
        }
    

    # Tier 2: heuristic on the assertion message shape
    # Pattern: comparing two quoted strings, e.g. assert 'error' == 'ok'
    # This shape usually means we compared a DEVICE-REPORTED STATUS field
    # against an expected string - a real behavioral defect signature.

    quoted_string_compare = re.search(r"assert\s+'[^']*'\s*==\s*'[^']*'", crash_message)

    # Pattern: comparing two bare numbers, e.g. assert 2 == 5
    # This shape often means a hardcoded expected value was compared against
    # a plausible device-returned number - could be either a real defect
    # OR a wrong test assumption. We can't be certain from text alone, so
    # we flag it for review rather than guessing confidently.

    bare_number_compare = re.search(r"assert\s+\d+(\.\d+)?\s*==\s*\d+(\.\d+)?", crash_message)


    if quoted_string_compare:
        return {
            "nodeid": nodeid,
            "category": "PRODUCT_DEFECT",
            "confidence": "medium",
            "reason": "Failure compares device-reported status strings - "
                      "suggests the device returned an unexpected state.",
            "message": crash_message,
        }
    
    if bare_number_compare:
        return {
            "nodeid": nodeid,
            "category": "POSSIBLE_TEST_BUG",
            "confidence": "low",
            "reason": "Failure compares bare numeric values with no clear "
                      "device-status signature - could be a real defect or "
                      "an incorrect test expectation. Needs human review.",
            "message": crash_message,
        }
    
    # Fallback: couldn't confidently pattern match
    return {
        "nodeid": nodeid,
        "category": "UNCLASSIFIED",
        "confidence": "low",
        "reason": "Failure message did not match any known pattern. Needs manual triage.",
        "message": crash_message,
    }


def triage_report(report_path):
    report = load_report(report_path)
    tests = report.get("tests", [])

    failed_tests = [t for t in tests if t["outcome"] == "failed"]
    classifications = [classify_test(t) for t in failed_tests]

    summary = Counter(c["category"] for c in classifications)
    total = report["summary"].get("total", len(tests))
    total_failed = len(failed_tests)

    return {
        "total_tests": total,
        "total_failed": total_failed,
        "pass_rate": round((total - total_failed) / total * 100, 1) if total else 0,
        "category_counts": dict(summary),
        "classifications": classifications,
    }    



if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python triage/classify.py <path_to_json_report>")
        sys.exit(1)

    result = triage_report(sys.argv[1])

    print(f"\n{'='*60}")
    print(f"FailSense Triage Report")
    print(f"{'='*60}")
    print(f"Total tests: {result['total_tests']}")
    print(f"Failed: {result['total_failed']}")
    print(f"Pass rate: {result['pass_rate']}%\n")

    print("Failure breakdown by category:")
    for category, count in result["category_counts"].items():
        pct = round(count / result["total_failed"] * 100, 1) if result["total_failed"] else 0
        print(f"  {category}: {count} ({pct}% of failures)")

    print(f"\n{'-'*60}")
    print("Details:\n")
    for c in result["classifications"]:
        print(f"[{c['category']}] ({c['confidence']} confidence) {c['nodeid']}")
        print(f"  Reason: {c['reason']}")
        print(f"  Message: {c['message'][:100]}")
        print()

    # Also write a machine-readable copy for the HTML report step next
    output_path = Path("reports/triage_result.json")
    output_path.write_text(json.dumps(result, indent=2))
    print(f"Machine-readable result written to {output_path}")