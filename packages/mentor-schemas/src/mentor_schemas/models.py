from enum import Enum


class ModelAlias(str, Enum):
    """Names the harness uses when calling the model router.

    The harness never names a real model. The router (LiteLLM) maps each alias
    to a provider model; the mapping lives in services/model-router/config.yaml.
    """

    CHAT = "mentor-chat"  # daily conversation
    VISION = "mentor-vision"  # images: graded tests, slides, figures
    REASONING = "mentor-reasoning"  # nightly reflection, planning, parent reports
    SAFETY_DETECT = "mentor-safety-a"  # crisis detection, step 1
    SAFETY_CONFIRM = "mentor-safety-b"  # crisis confirmation, step 2 (a different model)
