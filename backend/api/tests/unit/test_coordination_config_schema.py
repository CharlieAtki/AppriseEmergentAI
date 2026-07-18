from __future__ import annotations

import pytest
from api.schemas.coordination_config import UpdateCoordinationConfigRequest
from pydantic import ValidationError


def test_update_request_rejects_out_of_range_overrides() -> None:
    for field, value in (
        ("max_delegation_depth", 0),
        ("max_delegation_depth", -1),
        ("decompose_difficulty_threshold", -0.1),
    ):
        with pytest.raises(ValidationError):
            UpdateCoordinationConfigRequest(**{field: value})


def test_update_request_allows_null_to_clear_overrides() -> None:
    for field in ("max_delegation_depth", "decompose_difficulty_threshold"):
        request = UpdateCoordinationConfigRequest(**{field: None})
        assert getattr(request, field) is None
        assert field in request.model_fields_set
