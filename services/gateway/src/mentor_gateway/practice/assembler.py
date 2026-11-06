"""Deterministic exam assembly: practice, mock and diagnostic (port of agent-mentor `ExamAssembler.kt` / `DiagnosticPlanner`).

Same inputs and same `seed` give the same set (a started session equals its preview); no LLM, and the quality filter
is never relaxed: too few approved items raise `InsufficientContent`, nothing is padded. Version `assembler-v3`.

What follows the Kotlin code number for number: the topic weight formula per goal, largest-remainder allocation with a
per-topic cap (40 %), targets at P(correct) 0.70 for core items and 0.50 for the 20 % stretch (weak topics get no
stretch and aim at level <= 2), the 40/30/20/10 standard mix for topics without evidence, repeat penalties below one
level gap for practice and above it for mocks, level-slot repair, re-selection with fewer items when over the time
budget, official-format papers filled part by part.

What differs: mastery is Mentor's BKT per topic (`mastery.TopicMastery`), so the 3PL inverse `b_for` takes
theta = logit(topic mastery) and no sd; the diagnostic is a fixed plan (2 items on each of up to 6 topics) instead of
an adaptive one, because BKT needs no probe to be chosen from a running estimate.
"""

import hashlib
import math
from collections import defaultdict
from dataclasses import dataclass, field

from mentor_gateway.practice.bank import (
    LOCATION_PER_LEVEL,
    SHORT,
    SINGLE,
    TRUE_FALSE,
    Bank,
    Item,
    Profile,
    level_for_location,
    location_for_level,
)
from mentor_gateway.practice.mastery import TopicMastery

VERSION = "assembler-v3"
TARGET_P_CORE, TARGET_P_STRETCH = 0.70, 0.50
GUESS = 0.25  # four-option single choice
WEIGHT_BASE, WEIGHT_WEAKNESS, WEIGHT_UNCERTAINTY = 0.3, 3.0, 0.3
CURRICULUM_BLEND = 0.4
STANDARD_LEVEL_MIX = [0.4, 0.3, 0.2, 0.1]
RECENT_PENALTY = {1: 0.8, 2: 0.5, 3: 0.3}
OLDER_PENALTY = 0.15
MOCK_RECENT_PENALTY = {1: 4.0, 2: 3.5, 3: 2.5}
MOCK_OLDER_PENALTY = 1.0
QUALITY_PENALTY, JITTER, LEVEL_GAP_COST = 0.2, 0.15, 1.0
FILTERED_POOL_FRACTION = 0.6
WEAK_TOPIC_FORMAT_COST = 1.0
PART_TOPIC_REPEAT_COST = 0.6
MAX_SLOT_SWAPS, MAX_REFITS, MISSING_ITEM_COST = 64, 6, 100.0
GOALS = ("balanced", "weak", "challenge")


class InsufficientContent(Exception):
    """Not enough approved items for the request (API error `insufficient_content`; never padded)."""

    def __init__(self, available: int, required: int, message: str) -> None:
        super().__init__(message)
        self.available, self.required, self.message = available, required, message


@dataclass
class Constraints:
    time_budget_sec: int
    min_items: int = 5
    max_items: int = 40
    max_topic_fraction: float = 0.4
    stretch_fraction: float = 0.2
    goal: str = "balanced"
    topic_filter: set[str] | None = None
    exclude_ids: set[str] = field(default_factory=set)
    recently_seen: dict[str, int] = field(default_factory=dict)  # question id -> sessions ago (1 = previous)
    time_tolerance: float = 0.15


@dataclass
class Selected:
    item: Item
    level_slot: int | None = None  # level the slot asked for (item.level may differ: LEVEL_FALLBACK)
    part: int | None = None
    points_each: float = 1.0
    reasons: list[str] = field(default_factory=list)


@dataclass
class Assembly:
    items: list[Selected]
    seed: int
    total_seconds: int
    fallbacks: list[str]
    version: str = VERSION

    def level_mix(self) -> list[int]:
        return [sum(1 for s in self.items if s.item.level == lv) for lv in (1, 2, 3, 4)]

    def per_topic(self) -> dict[str, int]:
        out: dict[str, int] = defaultdict(int)
        for s in self.items:
            out[s.item.topic] += 1
        return dict(sorted(out.items()))


# ---- small deterministic helpers -----------------------------------------------------------------


def jitter(seed: int, key: str) -> float:
    """Stable pseudo-random value in [0, 1) from seed and id, independent of iteration order."""
    h = hashlib.sha256(f"{seed}:{key}".encode()).digest()
    return int.from_bytes(h[:8], "big") / 2**64


def level_sequence(count: int, mix: list[float]) -> list[int]:
    """`count` items split into levels 1..4 by `mix` (largest remainder), easy to hard."""
    quotas = [(i + 1, f * count) for i, f in enumerate(mix)]
    base = {lv: math.floor(q) for lv, q in quotas}
    left = count - sum(base.values())
    for lv, _ in sorted(quotas, key=lambda x: -(x[1] - math.floor(x[1]))):
        if left > 0:
            base[lv] += 1
            left -= 1
    return [lv for lv in sorted(base) for _ in range(base[lv])]


def distribute_levels(counts: dict[str, int], mix: list[float], seed: int = 0) -> dict[str, list[int]]:
    """Sorted level list dealt round-robin across topics (largest first), so each topic gets an easy-to-hard spread."""
    levels = level_sequence(sum(counts.values()), mix)
    remaining = {t: n for t, n in counts.items() if n > 0}
    out: dict[str, list[int]] = {t: [] for t in counts}
    order = [t for t, _ in sorted(counts.items(), key=lambda kv: (-kv[1], jitter(seed, kv[0])))]
    i = 0
    while i < len(levels):
        for topic in order:
            if i >= len(levels):
                break
            if remaining.get(topic, 0) == 0:
                continue
            out[topic].append(levels[i])
            i += 1
            remaining[topic] -= 1
    return out


def b_for(theta: float, p: float) -> float:
    """Item location at which a learner with ability theta answers correctly with probability p (3PL, fixed guess)."""
    q = min(1 - 1e-6, max(1e-6, (p - GUESS) / (1 - GUESS)))
    return max(-2.0, min(2.0, theta - math.log(q / (1 - q))))


def repeat_penalty(item: Item, c: Constraints, mock: bool) -> float:
    ago = c.recently_seen.get(item.id)
    if ago is None:
        return 0.0
    return (MOCK_RECENT_PENALTY.get(ago, MOCK_OLDER_PENALTY) if mock else RECENT_PENALTY.get(ago, OLDER_PENALTY))


def pick_best(pool: list[Item], target_loc: float, target_level: int | None, c: Constraints, seed: int,
              mock: bool, format_cost: float = 0.0) -> Item | None:
    def cost(it: Item) -> float:
        gap = abs(it.level - target_level) if target_level is not None else abs(it.location - target_loc) / LOCATION_PER_LEVEL
        fmt = format_cost if it.type != SINGLE else 0.0
        return (LEVEL_GAP_COST * (gap + fmt) + repeat_penalty(it, c, mock) + QUALITY_PENALTY * (1 - it.quality)
                + JITTER * jitter(seed, it.id))

    return min(pool, key=cost, default=None)


def topic_weight(m: TopicMastery | None, goal: str) -> float:
    weakness = 1.0 - (m.estimate if m else 0.5)
    unc = m.uncertainty if m else 1.0
    if goal == "weak":
        return 0.05 + 2 * WEIGHT_WEAKNESS * weakness**2 + WEIGHT_UNCERTAINTY * unc
    if goal == "challenge":
        return WEIGHT_BASE + WEIGHT_WEAKNESS * (1 - weakness) ** 2 + WEIGHT_UNCERTAINTY * unc
    return WEIGHT_BASE + WEIGHT_WEAKNESS * weakness**2 + WEIGHT_UNCERTAINTY * unc


def _allocate(n: int, weights: dict[str, float], available: dict[str, int], c: Constraints,
              fallbacks: list[str]) -> dict[str, int]:
    """Largest-remainder apportionment with per-topic caps and a coverage floor for the balanced goal."""
    cap = max(1, math.floor(n * c.max_topic_fraction))
    result = dict.fromkeys(weights, 0)
    if c.goal == "balanced" and n >= len(weights):
        result = dict.fromkeys(weights, 1)
    remaining = n - sum(result.values())
    total = sum(weights.values()) or 1.0
    quotas = {t: w / total * n for t, w in weights.items()}
    while remaining > 0:
        cands = [t for t in weights if result[t] < min(cap, available.get(t, 0))]
        if cands:
            pick = max(cands, key=lambda t: (quotas[t] - result[t], t))
        else:
            relaxed = [t for t in weights if result[t] < available.get(t, 0)]
            if not relaxed:
                break
            pick = max(relaxed, key=lambda t: (quotas[t] - result[t], t))
            fallbacks.append(f"TOPIC_CAP_RELAXED:{pick}")
        result[pick] += 1
        remaining -= 1
    return result


def _topic_supply(sizes: dict[str, int], c: Constraints) -> dict[str, int]:
    """Whole subject: every eligible item. Topic filter: at most 60 % of each pool, raised one item at a time (largest
    pool first) when that would leave fewer than `min_items`, so tiny pools still give a session."""
    if c.topic_filter is None:
        return dict(sizes)
    caps = {t: min(size, max(min(1, size), round(size * FILTERED_POOL_FRACTION))) for t, size in sizes.items()}
    while sum(caps.values()) < c.min_items:
        grow = sorted((t for t in caps if caps[t] < sizes[t]), key=lambda t: (-(sizes[t] - caps[t]), t))
        if not grow:
            break
        caps[grow[0]] += 1
    return caps


def _targets(m: TopicMastery | None, count: int, stretch_fraction: float) -> list[tuple[float, int | None, bool, bool]]:
    """(location, level, stretch, standard_mix) per slot of one topic."""
    if m is None or not m.has_evidence:
        return [(location_for_level(lv), lv, False, True) for lv in level_sequence(count, STANDARD_LEVEL_MIX)]
    weak = m.estimate < 0.45  # weak topics are practised at a comfortable level only
    stretch_n = 0 if weak else max(0, min(count - 1, round(count * stretch_fraction)))
    core, stretch = b_for(m.theta, TARGET_P_CORE), b_for(m.theta, TARGET_P_STRETCH)
    core_level = min(2, level_for_location(core)) if weak else None
    return [(core, core_level, False, False)] * (count - stretch_n) + [(stretch, None, True, False)] * stretch_n


def _slot_cost(levels: list[int], pool: list[Item], c: Constraints, mock: bool) -> float:
    """Least total cost of filling `levels` (sorted) from `pool` (sorted by level), one distinct item per slot; an
    order-preserving matching is optimal in one dimension, so a DP is exact."""
    if not levels:
        return 0.0
    if len(pool) < len(levels):
        return MISSING_ITEM_COST * (len(levels) - len(pool))
    inf = float("inf")
    prev = [0.0] * (len(pool) + 1)
    for i in range(1, len(levels) + 1):
        cur = [inf] * (len(pool) + 1)
        for j in range(1, len(pool) + 1):
            item = pool[j - 1]
            match = prev[j - 1] + LEVEL_GAP_COST * abs(item.level - levels[i - 1]) + repeat_penalty(item, c, mock)
            cur[j] = min(cur[j - 1], match)
        prev = cur
    return prev[-1]


def _repair_slots(dealt: dict[str, list[int]], by_topic: dict[str, list[Item]], c: Constraints, mock: bool,
                  fallbacks: list[str]) -> dict[str, list[int]]:
    """After the round-robin deal, swap level slots between topics while that lowers the mismatch between slots and
    what each topic's pool can give. Topic counts and the level mix stay; the result is deterministic."""
    slots = {t: list(v) for t, v in sorted(dealt.items())}
    pools = {t: sorted(by_topic.get(t, []), key=lambda i: (i.level, i.id)) for t in slots}
    costs = {t: _slot_cost(sorted(v), pools[t], c, mock) for t, v in slots.items()}
    topics = list(slots)
    for _ in range(MAX_SLOT_SWAPS):
        best = None
        best_gain = 1e-9
        for i, t in enumerate(topics):
            for u in topics[i + 1:]:
                for a in sorted(set(slots[t]), reverse=True):
                    for b in sorted(set(slots[u]), reverse=True):
                        if a == b:
                            continue
                        new_t, new_u = list(slots[t]), list(slots[u])
                        new_t.remove(a)
                        new_t.append(b)
                        new_u.remove(b)
                        new_u.append(a)
                        ct, cu = _slot_cost(sorted(new_t), pools[t], c, mock), _slot_cost(sorted(new_u), pools[u], c, mock)
                        gain = costs[t] + costs[u] - ct - cu
                        if gain > best_gain:
                            best_gain, best = gain, (t, a, u, b, new_t, new_u, ct, cu)
        if best is None:
            break
        t, a, u, b, new_t, new_u, ct, cu = best
        slots[t], slots[u] = sorted(new_t), sorted(new_u)
        costs[t], costs[u] = ct, cu
        fallbacks.append(f"LEVEL_SLOT_MOVED:{t}:{a}->{b}:{u}:{b}->{a}")
    return slots


def _order(items: list[Selected], seed: int) -> list[Selected]:
    """Warm-up first, then interleave topics so the same topic rarely appears twice in a row."""
    remaining = sorted(items, key=lambda s: (s.item.level, jitter(seed, s.item.id)))
    out: list[Selected] = []
    while remaining:
        last = out[-1].item.topic if out else None
        nxt = next((s for s in remaining if s.item.topic != last), remaining[0])
        remaining.remove(nxt)
        out.append(nxt)
    return out


def _finish(items: list[Selected], seed: int, fallbacks: list[str]) -> Assembly:
    return Assembly(items, seed, sum(s.item.seconds for s in items), fallbacks)


# ---- practice --------------------------------------------------------------------------------------


def eligible(items: list[Item], c: Constraints) -> list[Item]:
    return sorted((i for i in items if i.id not in c.exclude_ids), key=lambda i: i.id)


def assemble_practice(bank: Bank, subject: str, mastery: dict[str, TopicMastery], c: Constraints, seed: int) -> Assembly:
    pool_all = eligible(bank.by_subject.get(subject, []), c)
    if c.topic_filter is not None:
        pool_all = [i for i in pool_all if i.topic in c.topic_filter]
    if len(pool_all) < c.min_items:
        raise InsufficientContent(len(pool_all), c.min_items,
                                  f"Kho hiện chỉ có {len(pool_all)} câu đã duyệt phù hợp; chọn thêm chủ đề hoặc môn khác.")
    by_topic: dict[str, list[Item]] = defaultdict(list)
    for it in pool_all:
        by_topic[it.topic].append(it)
    active = sorted(by_topic, key=lambda t: t)
    timed = [i for i in pool_all if i.type == SINGLE] or pool_all
    avg_sec = sum(i.seconds for i in timed) / len(timed)
    supply = _topic_supply({t: len(v) for t, v in by_topic.items()}, c)
    wanted = min(c.max_items, max(c.min_items, round(c.time_budget_sec / avg_sec)))
    n = min(wanted, sum(supply.values()))
    fallbacks: list[str] = []
    if wanted > n and sum(supply.values()) < len(pool_all):
        for t, cap in sorted(supply.items()):
            if cap < len(by_topic[t]):
                fallbacks.append(f"TOPIC_POOL_CAP:{t}:{cap}/{len(by_topic[t])}")
    cw = {t: bank.topics.get(t).weight for t in active}
    cw_total = sum(cw.values()) or 1.0
    weights = {t: (CURRICULUM_BLEND * cw[t] / cw_total + (1 - CURRICULUM_BLEND) / len(active)) * topic_weight(mastery.get(t), c.goal)
               for t in active}

    def select(count: int) -> tuple[list[Selected], list[str]]:
        sel_fallbacks: list[str] = []
        alloc = _allocate(count, weights, supply, c, sel_fallbacks)
        unknown = {t: alloc[t] for t in active if not (mastery.get(t) and mastery[t].has_evidence)}
        # the 40/30/20/10 mix is applied to all no-evidence topics together and dealt round-robin: rounding it per
        # topic (2-4 items each) would never produce a level-4 item
        unknown_levels = _repair_slots(distribute_levels(unknown, STANDARD_LEVEL_MIX, seed), by_topic, c, False, sel_fallbacks)
        chosen: list[Selected] = []
        for t in active:
            k = alloc[t]
            if k == 0:
                continue
            m = mastery.get(t)
            if t in unknown_levels:
                targets = [(location_for_level(lv), lv, False, True) for lv in unknown_levels[t]]
            else:
                targets = _targets(m, k, c.stretch_fraction)
            pool = list(by_topic[t])
            for loc, level, stretch, standard in targets:
                weak = not standard and m is not None and m.has_evidence and m.estimate < 0.45
                pick = pick_best(pool, loc, level, c, seed, mock=False, format_cost=WEAK_TOPIC_FORMAT_COST if weak else 0.0)
                if pick is None:
                    break
                pool.remove(pick)
                reasons = ["STANDARD_MIX_NO_DATA" if standard else "WEAK_TOPIC_PRACTICE" if m and m.estimate < 0.45
                           else "STRONG_TOPIC_CHALLENGE" if m and m.estimate > 0.65 else "DEVELOPING_TOPIC"]
                if stretch:
                    reasons.append("STRETCH_ITEM")
                if pick.id in c.recently_seen:
                    reasons.append("REPEATED_ITEM")
                chosen.append(Selected(pick, reasons=reasons))
        return chosen, sel_fallbacks

    chosen, sel_fb = select(n)
    upper = c.time_budget_sec * (1 + c.time_tolerance)
    count, refits = n, 0
    # targeted items can be much longer than the pool's mean (a level-4 item ~4 min): re-select with fewer items
    # instead of trimming the longest, so a strong learner keeps the hard items he was targeted with
    while refits < MAX_REFITS and count > c.min_items:
        refits += 1
        total = sum(s.item.seconds for s in chosen)
        if total <= upper:
            break
        count = max(c.min_items, min(count - 1, math.floor(count * c.time_budget_sec / total)))
        chosen, sel_fb = select(count)
    fallbacks += sel_fb
    _fit_time(chosen, pool_all, mastery, c, seed, fallbacks, supply)
    if len(chosen) < c.min_items:
        raise InsufficientContent(len(chosen), c.min_items,
                                  "Không đủ câu thỏa ràng buộc (đã làm gần đây). Hãy tăng thời gian hoặc chọn thêm chủ đề.")
    return _finish(_order(chosen, seed), seed, fallbacks)


def _fit_time(chosen: list[Selected], pool: list[Item], mastery: dict[str, TopicMastery], c: Constraints, seed: int,
              fallbacks: list[str], supply: dict[str, int]) -> None:
    """Over budget: drop the longest. Clearly under: add the best-fitting unused single-choice item (padding is filler;
    a 4-5 minute group would decide the session's shape on its own)."""
    upper, lower = c.time_budget_sec * (1 + c.time_tolerance), c.time_budget_sec * (1 - c.time_tolerance)
    total = lambda: sum(s.item.seconds for s in chosen)
    while total() > upper and len(chosen) > c.min_items:
        worst = max(chosen, key=lambda s: s.item.seconds + 10 * jitter(seed, s.item.id))
        chosen.remove(worst)
        fallbacks.append(f"TRIMMED_FOR_TIME:{worst.item.id}")
    cap = max(1, math.floor(max(len(chosen), c.min_items) * c.max_topic_fraction) + 1)
    while total() < lower and len(chosen) < c.max_items:
        used = {s.item.id for s in chosen}
        per_topic: dict[str, int] = defaultdict(int)
        for s in chosen:
            per_topic[s.item.topic] += 1
        room = upper - total()

        def cost(it: Item) -> float:
            m = mastery.get(it.topic)
            target = b_for(m.theta, TARGET_P_CORE) if m and m.has_evidence else 0.0
            return abs(it.location - target) + (1.0 if it.id in c.recently_seen else 0.0) + JITTER * jitter(seed, it.id)

        cands = [i for i in pool if i.id not in used and i.seconds <= room and i.type == SINGLE
                 and per_topic[i.topic] < min(cap, supply.get(i.topic, 0))]
        if not cands:
            break
        pick = min(cands, key=cost)
        m = mastery.get(pick.topic)
        chosen.append(Selected(pick, reasons=["COVERAGE"] + ([] if m and m.has_evidence else ["STANDARD_MIX_NO_DATA"])))
        fallbacks.append(f"PADDED_FOR_TIME:{pick.id}")


# ---- mock ------------------------------------------------------------------------------------------


def _type_label(t: str) -> str:
    return {SINGLE: "trắc nghiệm", TRUE_FALSE: "Đúng/Sai", SHORT: "trả lời ngắn"}.get(t, t)


def assemble_mock(bank: Bank, profile: Profile, c: Constraints, seed: int) -> Assembly:
    """Follows the profile: topic matrix + level mix, or the 3-part official-format paper. A mock keeps to its profile's
    formats (the MCQ practice mock never gets a true/false group)."""
    pool = [i for i in eligible(bank.by_subject.get(profile.subject, []), c) if i.type in profile.question_types]
    fallbacks: list[str] = []
    chosen: list[Selected] = []
    if profile.parts:
        used: set[str] = set()
        for part in sorted(profile.parts, key=lambda p: p.part):
            ppool = [i for i in pool if i.type == part.type and i.id not in used]
            if len(ppool) < part.item_count:
                raise InsufficientContent(len(ppool), part.item_count,
                                          f"{part.label}: kho có {len(ppool)} câu {_type_label(part.type)} đã duyệt, đề cần {part.item_count} câu.")
            mix = part.level_mix or profile.level_mix
            picked: list[Selected] = []
            if part.topic_matrix:
                by_topic = _group(ppool)
                _check_matrix(part.topic_matrix, by_topic, part.label)
                levels = _repair_slots(distribute_levels(dict(sorted(part.topic_matrix.items())), mix, seed),
                                       by_topic, c, True, fallbacks)
                for topic in sorted(part.topic_matrix):
                    tpool = list(by_topic.get(topic, []))
                    for lv in levels[topic]:
                        pick = pick_best(tpool, location_for_level(lv), lv, c, seed, mock=True)
                        if pick is None:
                            break
                        tpool.remove(pick)
                        picked.append(_slot(pick, lv, part.points_per_item, part.part, c, fallbacks))
            else:
                left = list(ppool)
                per_topic: dict[str, int] = defaultdict(int)
                for lv in sorted(level_sequence(part.item_count, mix), reverse=True):  # scarce hard slots first
                    pick = min(left, key=lambda it: (LEVEL_GAP_COST * abs(it.level - lv) + repeat_penalty(it, c, True)
                                                     + PART_TOPIC_REPEAT_COST * per_topic[it.topic]
                                                     + QUALITY_PENALTY * (1 - it.quality) + JITTER * jitter(seed, it.id)),
                               default=None)
                    if pick is None:
                        break
                    left.remove(pick)
                    per_topic[pick.topic] += 1
                    picked.append(_slot(pick, lv, part.points_per_item, part.part, c, fallbacks))
            if len(picked) < part.item_count:
                raise InsufficientContent(len(picked), part.item_count, f"{part.label}: không đủ câu để lập đề.")
            used |= {s.item.id for s in picked}
            chosen += sorted(picked, key=lambda s: (s.item.level, jitter(seed, s.item.id)))
        return _finish(chosen, seed, fallbacks)

    by_topic = _group(pool)
    _check_matrix(profile.topic_matrix, by_topic, "Đề")
    levels = _repair_slots(distribute_levels(dict(sorted(profile.topic_matrix.items())), profile.level_mix, seed),
                           by_topic, c, True, fallbacks)
    for topic in sorted(profile.topic_matrix):
        tpool = list(by_topic.get(topic, []))
        for lv in levels[topic]:
            pick = pick_best(tpool, location_for_level(lv), lv, c, seed, mock=True)
            if pick is None:
                break
            tpool.remove(pick)
            chosen.append(_slot(pick, lv, 1.0, None, c, fallbacks, topic))
    if len(chosen) < profile.item_count:
        raise InsufficientContent(len(chosen), profile.item_count, "Ngân hàng câu hỏi chưa đủ cho ma trận đề thi thử.")
    # easier first inside the paper (typical exam layout)
    return _finish(sorted(chosen, key=lambda s: (s.item.level, jitter(seed, s.item.id))), seed, fallbacks)


def _group(items: list[Item]) -> dict[str, list[Item]]:
    out: dict[str, list[Item]] = defaultdict(list)
    for i in items:
        out[i.topic].append(i)
    return out


def _check_matrix(matrix: dict[str, int], by_topic: dict[str, list[Item]], label: str) -> None:
    for topic, need in sorted(matrix.items()):
        have = len(by_topic.get(topic, []))
        if have < need:
            raise InsufficientContent(have, need, f"{label}: chủ đề {topic} chỉ có {have} câu đã duyệt, đề cần {need} câu.")


def _slot(pick: Item, level: int, points: float, part: int | None, c: Constraints, fallbacks: list[str],
          topic: str | None = None) -> Selected:
    reasons = ["BLUEPRINT"] + ([f"PART:{part}"] if part is not None else [])
    if pick.level != level:
        reasons.append("LEVEL_FALLBACK")
        fallbacks.append(f"LEVEL_FALLBACK:{pick.topic}:{level}->{pick.level}")
    if pick.id in c.recently_seen:
        reasons.append("REPEATED_ITEM")
    return Selected(pick, level_slot=level, part=part, points_each=points, reasons=reasons)


# ---- diagnostic ------------------------------------------------------------------------------------


def assemble_diagnostic(bank: Bank, subject: str, seed: int, max_items: int = 12, max_topics: int = 6,
                        per_topic: int = 2,
                        exclude_topics: set[str] | None = None) -> Assembly:
    """Single-choice only (one binary answer per probe). The probed topics are the `max_topics` with the largest
    curriculum weight that have content; each gets `per_topic` items, one near level 2 and one near level 3, dealt
    round-robin so the learner meets every topic early. Fixed by the bank and the seed, so a resumed diagnostic is the
    same one."""
    pool = [i for i in bank.by_subject.get(subject, []) if i.type == SINGLE and i.topic not in (exclude_topics or ())]
    by_topic = _group(pool)
    topics = sorted(by_topic, key=lambda t: (-bank.topics.get(t).weight, t))[:max_topics]
    if not topics:
        raise InsufficientContent(0, 1, "Môn này chưa có câu trắc nghiệm đã duyệt để đánh giá nhanh.")
    c = Constraints(time_budget_sec=15 * 60)
    picks: dict[str, list[Item]] = {}
    for t in topics:
        left = list(by_topic[t])
        got: list[Item] = []
        for target in (location_for_level(2), location_for_level(3))[:per_topic]:
            pick = pick_best(left, target, None, c, seed, mock=False)
            if pick is not None:
                left.remove(pick)
                got.append(pick)
        picks[t] = got
    chosen: list[Selected] = []
    for rnd in range(per_topic):
        for t in topics:
            if rnd < len(picks[t]) and len(chosen) < max_items:
                chosen.append(Selected(picks[t][rnd], reasons=["DIAGNOSTIC_PROBE"]))
    return _finish(chosen, seed, [])
