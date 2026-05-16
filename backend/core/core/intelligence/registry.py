from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ModelEntry:
    model_id: str
    vendor: str
    vendor_model_id: str
    display_name: str | None = None


class ModelRegistry:
    def __init__(self) -> None:
        self._models: dict[str, ModelEntry] = {}

    def add_moddel(
        self,
        model_id: str,
        *,
        vendor: str,
        vendor_model_id: str,
        display_name: str | None = None,
    ) -> None:
        self._models[model_id] = ModelEntry(
            model_id=model_id,
            vendor=vendor,
            vendor_model_id=vendor_model_id,
            display_name=display_name,
        )

    def available_models(self) -> list[ModelEntry]:
        return list(self._models.values())

    def get_model(self, model_id: str) -> ModelEntry | None:
        return self._models.get(model_id)


registry = ModelRegistry()
