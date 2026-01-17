from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, Optional, Tuple

from .base import ChargeModel
from .appgw import AppGatewayChargeModel
from .declarative import DeclarativeChargeModel, load_definitions
from .eventhubs import EventHubsChargeModel
from .eventgrid import EventGridChargeModel
from .functions import FunctionsChargeModel
from .azureml import AzureMLChargeModel
from .bandwidth import BandwidthChargeModel
from .compute_vm import VMChargeModel
from .log_analytics import LogAnalyticsChargeModel
from .sql import SqlChargeModel
from .storage_blob import StorageBlobChargeModel


@dataclass
class ChargeModelRegistry:
    """Lookup table for charge models by canonical category."""

    models: Dict[str, ChargeModel] = field(default_factory=dict)          # exact matches
    prefix_models: Dict[str, ChargeModel] = field(default_factory=dict)   # longest-prefix matches

    def register(self, category: str, model: ChargeModel) -> None:
        self.models[category] = model

    def register_prefix(self, prefix: str, model: ChargeModel) -> None:
        self.prefix_models[prefix] = model

    def get(self, category: str) -> Optional[ChargeModel]:
        if category in self.models:
            return self.models[category]

        best: Tuple[int, str] | None = None
        for p in self.prefix_models.keys():
            if category.startswith(p) and (best is None or len(p) > best[0]):
                best = (len(p), p)
        if best is None:
            return None
        return self.prefix_models[best[1]]


def build_default_registry() -> ChargeModelRegistry:
    """Default registry with a first set of models (v1)."""

    reg = ChargeModelRegistry()

    # 1) Declarative definitions (YAML/JSON)
    for d in load_definitions():
        m = DeclarativeChargeModel(d)
        for p in d.category_prefixes:
            reg.register_prefix(p, m)

    reg.register("compute.vm", VMChargeModel())
    reg.register("db.sql", SqlChargeModel())
    reg.register("db.sqlmi", SqlChargeModel())
    reg.register("storage.blob", StorageBlobChargeModel())
    # Planner currently emits "monitoring.loganalytics" in plans; keep compatibility with both keys.
    reg.register("monitor.loganalytics", LogAnalyticsChargeModel())
    reg.register("monitoring.loganalytics", LogAnalyticsChargeModel())
    reg.register("network.bandwidth", BandwidthChargeModel())
    reg.register("network.appgw", AppGatewayChargeModel())
    reg.register("messaging.eventhubs", EventHubsChargeModel())
    reg.register("messaging.eventgrid", EventGridChargeModel())
    reg.register("function", FunctionsChargeModel())
    reg.register("ml.azureml", AzureMLChargeModel())
    return reg
