from core.intelligence.registry import registry

registry.add_model(
    "ollama/llama3",
    vendor="ollama",
    vendor_model_id="llama3",
    display_name="Llama 3",
)
registry.add_model(
    "ollama/mistral",
    vendor="ollama",
    vendor_model_id="mistral",
    display_name="Mistral",
)
