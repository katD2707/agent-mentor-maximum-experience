"""mentor-harness: the agent loop (tools, skills, model client) as an importable library.

Server-side workers build a `Harness` and call `turn` / `stream_turn` / `run_job`.
"""

from mentor_harness.agent import Harness
from mentor_harness.config import Settings
from mentor_harness.model import DevScriptedModel, ModelError, ModelResponse, RouterModel, ScriptedModel, ToolCall

__all__ = [
    "DevScriptedModel",
    "Harness",
    "ModelError",
    "ModelResponse",
    "RouterModel",
    "ScriptedModel",
    "Settings",
    "ToolCall",
]
