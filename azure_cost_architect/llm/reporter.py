import json
from openai import OpenAI

from ..config import MODEL_REPORTER, MODEL_REPORTER_RESPONSES
from ..prompts import PROMPT_REPORTER_SYSTEM, PROMPT_REPORTER_USER_TEMPLATE


def generate_report_chat(client: OpenAI, arch_text: str, enriched_plan: dict) -> str:
    plan_json = json.dumps(enriched_plan, indent=2, ensure_ascii=False)
    user_prompt = PROMPT_REPORTER_USER_TEMPLATE.format(
        arch_text=arch_text, plan_json=plan_json
    )
    completion = client.chat.completions.create(
        model=MODEL_REPORTER,
        temperature=0.2,
        messages=[
            {"role": "system", "content": PROMPT_REPORTER_SYSTEM},
            {"role": "user", "content": user_prompt},
        ],
    )
    report_md = completion.choices[0].message.content or ""
    with open("debug_report_raw.md", "w", encoding="utf-8") as f:
        f.write(report_md)
    return report_md


def generate_report_responses(client: OpenAI, arch_text: str, enriched_plan: dict) -> str:
    plan_json = json.dumps(enriched_plan, indent=2, ensure_ascii=False)
    user_prompt = PROMPT_REPORTER_USER_TEMPLATE.format(
        arch_text=arch_text, plan_json=plan_json
    )
    response = client.responses.create(
        model=MODEL_REPORTER_RESPONSES,
        input=[
            {"role": "system", "content": PROMPT_REPORTER_SYSTEM},
            {"role": "user", "content": user_prompt},
        ],
        tools=[{"type": "web_search"}],
        tool_choice="auto",
    )
    report_md = response.output[0].content[0].text
    with open("debug_report_raw.md", "w", encoding="utf-8") as f:
        f.write(report_md)
    return report_md
