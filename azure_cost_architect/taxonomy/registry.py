from dataclasses import dataclass
from typing import Dict, List, Optional


@dataclass
class CanonicalService:
    canonical_key: str
    taxonomy_path: List[str]
    category: str
    retail_service_name: str
    region_mode: str
    pricing_strategy: str
    preferred_meter_keywords: List[str]
    disallowed_meter_keywords: List[str]
    fallback_strategy: str


class TaxonomyRegistry:
    """
    Runtime registry derived from taxonomy.json.
    This is the authoritative source of:
      - allowed services
      - pricing strategies
      - scoring guardrails
    """

    def __init__(self):
        self._by_category: Dict[str, CanonicalService] = {}

    def register(self, svc: CanonicalService):
        self._by_category[svc.category] = svc

    def get(self, category: str) -> Optional[CanonicalService]:
        return self._by_category.get(category)

    def require(self, category: str) -> CanonicalService:
        svc = self.get(category)
        if not svc:
            raise ValueError(f"Unknown category not in taxonomy registry: {category}")
        return svc
