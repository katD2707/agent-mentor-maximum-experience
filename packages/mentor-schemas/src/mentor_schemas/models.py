from enum import Enum


class ModelAlias(str, Enum):
    """Names callers use for the model router.

    Code never names a real model. The router (LiteLLM) maps each alias to a provider model; the mapping lives in
    services/model-router/config.yaml, so the publisher can switch models without code changes.
    """

    CHAT = "mentor-chat"  # short answers: Q&A, Mực, reminders wording
    VISION = "mentor-vision"  # page OCR and legibility, photo questions, figure checks
    AUDIO = "mentor-audio"  # speech to text (chat completion with input_audio)
    REASONING = "mentor-reasoning"  # course outlines, lesson writing, planning
    EMBED = "mentor-embed"  # course retrieval embeddings
    RERANK = "mentor-rerank"  # optional rerank of retrieved courses
