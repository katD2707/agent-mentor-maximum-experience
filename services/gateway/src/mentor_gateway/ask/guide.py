"""Mực's guide chat (REQUIREMENTS-PLAN 3.9): CHAT alias with the guide map (apps/app/src/lib/guides.ts) as context.

`guide_map.json` is a server copy of GUIDES from guides.ts; tests/test_gw_ask.py fails when the two drift apart
(regenerate the JSON from guides.ts when it does).
"""

import json
import logging
import re
from functools import lru_cache
from pathlib import Path

from mentor_schemas import ModelAlias

from mentor_gateway.ask import prompts
from mentor_gateway.ask.llm import ChatLLM, LLMError
from mentor_gateway.planner.text import clean, unaccent

log = logging.getLogger(__name__)

MAP_FILE = Path(__file__).parent / "guide_map.json"
GENERIC = {"vi": "Em thử nhấn giữ rồi kéo mình tới chỗ em muốn hỏi, mình sẽ giải thích ngay chỗ đó.",
           "en": "Press and hold me, then drag me onto the part you're curious about and I'll explain it."}


@lru_cache(maxsize=1)
def guide_map() -> dict[str, dict[str, str]]:
    return json.loads(MAP_FILE.read_text(encoding="utf-8"))


def fallback_answer(question: str, lang: str, screen: str | None, visible: list[str]) -> str:
    """No model: the visible area that shares the most words with the question, else the current screen, else a hint."""
    gm = guide_map()
    q = set(re.findall(r"[a-z0-9]+", unaccent(question)))
    best, score = None, 0
    for key in [*visible, *([screen] if screen else [])]:
        if key in gm:
            s = len(q & set(re.findall(r"[a-z0-9]+", unaccent(gm[key]["vi"] + " " + gm[key]["en"] + " " + key))))
            if s > score:
                best, score = key, s
    return gm[best][lang] if best else GENERIC[lang]


async def answer(llm: ChatLLM | None, question: str, lang: str, screen: str | None, visible: list[str]) -> str:
    lang = lang if lang in ("vi", "en") else "vi"
    if llm is None:
        return fallback_answer(question, lang, screen, visible)
    payload = {"question": question[:300], "lang": lang, "screen": screen, "visible_keys": visible[:30],
               "guide_map": {k: v[lang] for k, v in guide_map().items()}}
    system = f"{prompts.GUIDE}\n\n{prompts.HUMANIZE_RULES}\nAnswer in `lang`."
    try:
        raw = await llm.complete(ModelAlias.CHAT.value, [{"role": "system", "content": system},
                                                         {"role": "user", "content": json.dumps(payload, ensure_ascii=False)}],
                                 max_tokens=300, temperature=0.3)
    except LLMError as e:
        log.warning("guide model failure: %s", e)
        return fallback_answer(question, lang, screen, visible)
    return clean(re.sub(r"<think>.*?</think>", "", raw, flags=re.DOTALL), 360) or GENERIC[lang]
