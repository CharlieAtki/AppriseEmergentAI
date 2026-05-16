from core.intelligence.registry import registry

registry.add_model(
    "azure/gpt-4o",
    vendor="azure",
    vendor_model_id="gpt-4o",
    display_name="GPT-4o",
)
registry.add_model(
    "azure/gpt-4o-mini",
    vendor="azure",
    vendor_model_id="gpt-4o-mini",
    display_name="GPT-4o Mini",
)
