"""
llm_classify.py
-----------------
LLM-based fallback classifier for test failures the rule-based classifier
in classify.py couldn't confidently categorize.

Design principle: the rule-based classifier stays the primary path because
it's fast, free, and deterministic - same input always gives the same
output, which matters a lot for CI reproducibility. This module is only
invoked for the subset of failures classify.py already flagged as
low-confidence (POSSIBLE_TEST_BUG, UNCLASSIFIED). We're not sending every
failure to an LLM - only the ones the cheap deterministic path couldn't
resolve. That's a deliberate cost/latency/determinism tradeoff, not an
oversight.

Uses GPT-4o Mini specifically: this is a short structured-classification
task on a small text snippet, not a task that benefits from a frontier
model's extra reasoning - Mini is faster and cheaper for identical output
quality on this kind of task.

If no API key is configured, this module degrades gracefully - callers
get back the original rule-based classification unchanged rather than
a crash. A triage tool that hard-fails when an LLM call isn't available
is worse than one that just skips the enhancement.

Usage (as a library, called from classify.py):
    from triage.llm_classify import maybe_escalate_to_llm
    enriched = maybe_escalate_to_llm(classification)
"""

import json
import os

from dotenv import load_dotenv

load_dotenv()  # reads .env into environment variables, if present

try:
    from openai import OpenAI
    _SDK_AVAILABLE = True
except ImportError:
    _SDK_AVAILABLE = False

# Only these low-confidence categories get escalated. High-confidence
# rule-based results (FLAKY_ENVIRONMENT, PRODUCT_DEFECT) are trusted as-is.
ESCALATE_CATEGORIES = {"POSSIBLE_TEST_BUG", "UNCLASSIFIED"}

MODEL = "gpt-4o-mini"

SYSTEM_PROMPT = """You are a QA triage assistant for a hardware test automation team.
Given a pytest failure message and test name, classify the failure into exactly
one of these three categories:

- FLAKY_ENVIRONMENT: likely caused by test environment instability (timing,
  network, resource contention), not a real device or test defect.
- PRODUCT_DEFECT: the failure indicates the device/product under test is
  behaving incorrectly - a real bug in the thing being tested.
- TEST_INFRA_BUG: the test itself has an incorrect assertion or setup issue;
  the device behavior shown in the failure is actually reasonable.

Respond with ONLY valid JSON, in exactly this shape:
{"category": "ONE_OF_THE_THREE_ABOVE", "confidence": "high|medium|low", "reasoning": "one or two sentence explanation"}
"""


def maybe_escalate_to_llm(classification: dict) -> dict:
    """
    Takes a single classification dict from classify.py's classify_test().
    If it's a low-confidence category and an API key is available, asks
    the LLM to weigh in and merges that into the result. Otherwise returns
    the original classification unchanged.
    """
    if classification["category"] not in ESCALATE_CATEGORIES:
        return classification

    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key or not _SDK_AVAILABLE:
        classification["llm_escalated"] = False
        classification["llm_note"] = "No API key configured - skipped LLM escalation."
        return classification

    try:
        client = OpenAI(api_key=api_key)
        response = client.chat.completions.create(
            model=MODEL,
            response_format={"type": "json_object"},
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": (
                    f"Test: {classification['nodeid']}\n"
                    f"Failure message:\n{classification['message']}"
                )},
            ],
            max_tokens=300,
        )
        raw_text = response.choices[0].message.content
        llm_result = json.loads(raw_text)

        # Merge: keep the original rule-based result for audit, add the LLM's view
        classification["llm_escalated"] = True
        classification["llm_category"] = llm_result.get("category", "UNCLASSIFIED")
        classification["llm_confidence"] = llm_result.get("confidence", "low")
        classification["llm_reasoning"] = llm_result.get("reasoning", "")

    except (json.JSONDecodeError, KeyError, IndexError) as e:
        classification["llm_escalated"] = False
        classification["llm_note"] = f"LLM response could not be parsed: {e}"
    except Exception as e:
        classification["llm_escalated"] = False
        classification["llm_note"] = f"LLM call failed: {e}"

    return classification