import json
from openai import OpenAI

from ..config import MODEL_PLANNER, MODEL_PLANNER_RESPONSES
from ..prompts import PROMPT_PLANNER_SYSTEM, PROMPT_PLANNER_USER_TEMPLATE
from ..planner.validation import validate_plan_schema
from ..planner.rules import apply_planner_rules
from .json_repair import extract_json_object, repair_json_with_llm


def plan_architecture_chat(client: OpenAI, arch_text: str, mode: str = "auto") -> dict:
    user_prompt = PROMPT_PLANNER_USER_TEMPLATE.format(arch_text=arch_text, mode=mode)
    completion = client.chat.completions.create(
        model=MODEL_PLANNER,
        response_format={"type": "json_object"},
        temperature=0.0,
        messages=[
            {"role": "system", "content": PROMPT_PLANNER_SYSTEM},
            {"role": "user", "content": user_prompt},
        ],
    )
    raw = completion.choices[0].message.content or ""
    with open("debug_plan_raw.json", "w", encoding="utf-8") as f:
        f.write(raw)

    raw_json = extract_json_object(raw)
    try:
        parsed = json.loads(raw_json)
    except json.JSONDecodeError:
        parsed = repair_json_with_llm(client, PROMPT_PLANNER_SYSTEM, raw_json)

    return apply_planner_rules(validate_plan_schema(parsed))


def plan_architecture_responses(client: OpenAI, arch_text: str, mode: str = "auto") -> dict:
    user_prompt = PROMPT_PLANNER_USER_TEMPLATE.format(arch_text=arch_text, mode=mode)
    response = client.responses.create(
        model=MODEL_PLANNER_RESPONSES,
        input=[
            {"role": "system", "content": PROMPT_PLANNER_SYSTEM},
            {"role": "user", "content": user_prompt},
        ],
        tools=[{"type": "web_search"}],
        tool_choice="auto",
    )
    raw = response.output[0].content[0].text
    with open("debug_plan_raw.json", "w", encoding="utf-8") as f:
        f.write(raw)

    raw_json = extract_json_object(raw)
    try:
        parsed = json.loads(raw_json)
    except json.JSONDecodeError:
        parsed = repair_json_with_llm(client, PROMPT_PLANNER_SYSTEM, raw_json)

    return apply_planner_rules(validate_plan_schema(parsed))
