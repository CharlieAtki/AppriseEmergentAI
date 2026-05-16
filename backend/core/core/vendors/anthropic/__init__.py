from core.intelligence.registry import registry

registry.add_model(
    "anthropic/claude-haiku-4-5-20251001",
    vendor="anthropic",
    vendor_model_id="claude-haiku-4-5-20251001",
    display_name="Claude Haiku 4.5",
)
registry.add_model(
    "anthropic/claude-sonnet-4-5",
    vendor="anthropic",
    vendor_model_id="claude-sonnet-4-5",
    display_name="Claude Sonnet 4.5",
)
registry.add_model(
    "anthropic/claude-opus-4-5",
    vendor="anthropic",
    vendor_model_id="claude-opus-4-5",
    display_name="Claude Opus 4.5",
)
