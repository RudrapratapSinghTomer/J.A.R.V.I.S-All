from .heart import EmotionState, Heart
from .llm_client import LLMClient, LLMResponse, ModelProfile, ModelCapability

__all__ = [
    "Heart",
    "EmotionState",
    "LLMClient",
    "LLMResponse",
    "ModelProfile",
    "ModelCapability",
    "Mind",
    "MindDecision",
    "MindEvent",
]


def __getattr__(name: str):
    if name in {"Mind", "MindDecision", "MindEvent"}:
        from .mind import Mind, MindDecision, MindEvent

        exports = {
            "Mind": Mind,
            "MindDecision": MindDecision,
            "MindEvent": MindEvent,
        }
        return exports[name]
    raise AttributeError(f"module 'core' has no attribute {name!r}")
