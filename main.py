from fastapi import FastAPI
from pydantic import BaseModel
from typing import Any, List
import re

app = FastAPI()


class Step(BaseModel):
    step_number: int
    tool: str
    args: Any
    tokens_used: int


class RequestBody(BaseModel):
    budget_tokens: int
    steps: List[Step]


def normalize_string(s: str):
    return re.sub(r"\s+", " ", s).strip()


def canonicalize(obj):
    if isinstance(obj, dict):
        return {
            k: canonicalize(v)
            for k, v in sorted(obj.items())
            if k != "trace_id"
        }

    if isinstance(obj, list):
        return [canonicalize(x) for x in obj]

    if isinstance(obj, str):
        return normalize_string(obj)

    return obj


def same_call(a: Step, b: Step):
    return (
        a.tool == b.tool
        and canonicalize(a.args) == canonicalize(b.args)
    )


@app.post("/check")
def check(body: RequestBody):

    total = sum(step.tokens_used for step in body.steps)

    if total >= body.budget_tokens:
        return {
            "decision": "halt",
            "reason": f"Cumulative tokens_used ({total}) has reached the budget ({body.budget_tokens})."
        }

    steps = body.steps

    # ---- 3 identical consecutive calls ----
    count = 1
    for i in range(1, len(steps)):
        if same_call(steps[i], steps[i - 1]):
            count += 1
            if count >= 3:
                return {
                    "decision": "halt",
                    "reason": "Detected 3 or more identical consecutive tool calls."
                }
        else:
            count = 1

    # ---- ABABAB trailing cycle ----
    if len(steps) >= 6:
        tail = steps[-6:]

        A = tail[0]
        B = tail[1]

        pattern = (
            same_call(tail[0], A)
            and same_call(tail[2], A)
            and same_call(tail[4], A)
            and same_call(tail[1], B)
            and same_call(tail[3], B)
            and same_call(tail[5], B)
        )

        if pattern and not same_call(A, B):
            return {
                "decision": "halt",
                "reason": "Detected repeating two-step tool-call cycle."
            }

    return {
        "decision": "continue",
        "reason": "Budget remaining and no loop detected."
    }
