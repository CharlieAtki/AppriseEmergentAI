from core.intelligence.registry import registry

registry.add_model(
    "aws/nova-pro",
    vendor="aws",
    vendor_model_id="amazon.nova-pro-v1:0",
    display_name="Amazon Nova Pro",
)
registry.add_model(
    "aws/nova-lite",
    vendor="aws",
    vendor_model_id="amazon.nova-lite-v1:0",
    display_name="Amazon Nova Lite",
)
