import json
import logging
from typing import Any, Dict, List

from openai import OpenAI

from ..config import MODEL_ADJUDICATOR
from ..prompts import PROMPT_ADJUDICATOR_SYSTEM

_LOGGER = logging.getLogger(__name__)


def _build_schema(max_index: int) -> Dict[str, Any]:
    return {
        "name": "adjudication_response",
        "schema": {
            "type": "object",
            "additionalProperties": False,
            "required": ["resource_id", "decision"],
            "properties": {
                "resource_id": {"type": "string"},
                "decision": {
                    "type": "object",
                    "additionalProperties": False,
                    "required": ["status"],
                    "properties": {
                        "status": {
                            "type": "string",
                            "enum": ["selected", "unresolvable"],
                        },
                        "selected_index": {
                            "type": "integer",
                            "minimum": 0,
                            "maximum": max_index,
                        },
                        "selected_candidate_id": {"type": "string"},
                        "reason": {"type": "string"},
                    },
                },
            },
        },
    }


def adjudicate_candidates(
    client: OpenAI,
    *,
    resource: Dict[str, Any],
    candidates: List[Dict[str, Any]],
    model: str = MODEL_ADJUDICATOR,
    trace=None,
) -> Dict[str, Any]:
    """Ask the LLM to pick among provided candidates.

    Returns the parsed JSON response. Validation is handled by the caller.
    """

    user_payload = {
        "resource": resource,
        "candidates": candidates,
        "instructions": "Select the best candidate index or mark unresolvable.",
    }

    schema = _build_schema(max_index=len(candidates) - 1 if candidates else 0)

    completion = client.chat.completions.create(
        model=model,
        temperature=0.0,
        response_format={"type": "json_schema", "json_schema": schema},
        messages=[
            {"role": "system", "content": PROMPT_ADJUDICATOR_SYSTEM},
            {"role": "user", "content": json.dumps(user_payload)},
        ],
    )

    raw = completion.choices[0].message.content or "{}"
    if trace:
        trace.log(
            "phase5_adjudication",
            {
                "resource_id": resource.get("id"),
                "model": model,
                "prompt": user_payload,
                "raw_response": raw,
            },
        )
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        _LOGGER.warning("Adjudicator returned invalid JSON: %s", raw)
        return {}
