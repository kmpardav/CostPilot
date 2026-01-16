from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Optional

from .base import ChargeModel
from .bandwidth import BandwidthChargeModel
from .compute_vm import VMChargeModel
from .log_analytics import LogAnalyticsChargeModel
from .sql import SqlChargeModel
from .storage_blob import StorageBlobChargeModel


@dataclass
class ChargeModelRegistry:
    """Lookup table for charge models by canonical category."""

    _models: Dict[str, ChargeModel]

    def register(self, category: str, model: ChargeModel) -> None:
        self._models[category] = model

    def get(self, category: str) -> Optional[ChargeModel]:
        return self._models.get(category)


def build_default_registry() -> ChargeModelRegistry:
    """Default registry with a first set of models (v1)."""

    reg = ChargeModelRegistry(_models={})
    reg.register("compute.vm", VMChargeModel())
    reg.register("db.sql", SqlChargeModel())
    reg.register("db.sqlmi", SqlChargeModel())
    reg.register("storage.blob", StorageBlobChargeModel())
    reg.register("monitor.loganalytics", LogAnalyticsChargeModel())
    reg.register("network.bandwidth", BandwidthChargeModel())
    return reg
