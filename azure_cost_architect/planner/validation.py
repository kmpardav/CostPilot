from ..config import HOURS_PROD

def validate_plan_schema(plan: dict) -> dict:
    if not isinstance(plan, dict):
        return {"metadata": {}, "scenarios": []}

    plan.setdefault("metadata", {})
    plan.setdefault("scenarios", [])
    if not isinstance(plan["scenarios"], list):
        plan["scenarios"] = []

    for scen in plan["scenarios"]:
        if not isinstance(scen, dict):
            continue
        scen.setdefault("id", "baseline")
        scen.setdefault("label", scen["id"])
        scen.setdefault("description", "")
        scen.setdefault("resources", [])
        if not isinstance(scen["resources"], list):
            scen["resources"] = []

        for res in scen["resources"]:
            if not isinstance(res, dict):
                continue
            res.setdefault("id", "res")
            res.setdefault("category", "other")
            res.setdefault("service_name", None)
            res.setdefault("arm_sku_name", None)
            res.setdefault("region", None)
            res.setdefault("quantity", 1)
            res.setdefault("hours_per_month", HOURS_PROD)
            res.setdefault("billing_model", "payg")
            res.setdefault("workload_type", "other")
            res.setdefault("criticality", "prod")
            res.setdefault("os_type", "na")
            res.setdefault("metrics", {})
            res.setdefault("notes", "")
            res.setdefault("source", "llm-inferred")

    return plan
