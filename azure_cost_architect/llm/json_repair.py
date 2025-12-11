import json

from openai import OpenAI
try:
    from rich.console import Console
except Exception:  # fallback αν δεν υπάρχει rich
    class Console:
        def print(self, *args, **kwargs):
            print(*args, **kwargs)

from ..config import MODEL_PLANNER

console = Console()


def extract_json_object(text: str) -> str:
    """
    Παίρνει ένα μεγάλο text και κρατάει μόνο το substring
    από το πρώτο '{' μέχρι το τελευταίο '}'.
    Χρήσιμο όταν ο LLM γυρνάει JSON + σχόλια.
    """
    if not text:
        return text
    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end != -1 and end > start:
        return text[start:end + 1]
    return text


def repair_json_with_llm(client: OpenAI, system_prompt: str, raw_text: str) -> dict:
    """
    Ζητάει από τον LLM να "επισκευάσει" ένα JSON που βγήκε λίγο χαλασμένο
    (π.χ. single quotes, trailing commas, κλπ.) και να επιστρέψει
    ΕΓΓΥΗΜΕΝΑ valid JSON.
    """
    fix_prompt = (
        "You MUST output ONLY valid JSON matching the required schema. "
        "Repair the following content into valid JSON. "
        "Do not add commentary.\n\nCONTENT:\n"
        + raw_text
    )
    completion = client.chat.completions.create(
        model=MODEL_PLANNER,
        response_format={"type": "json_object"},
        temperature=0.0,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": fix_prompt},
        ],
    )
    fixed = completion.choices[0].message.content or ""
    fixed = extract_json_object(fixed)
    return json.loads(fixed)
