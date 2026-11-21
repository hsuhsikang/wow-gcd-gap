"""WoW Analyzer-style dynamic GCD coverage analysis for Shadow Priest logs."""

from __future__ import annotations

from collections import defaultdict
from typing import Any


# Shadow Priest abilities from WoWAnalyzer's retail spellbook, plus Void Volley,
# which the player confirmed is an active GCD ability in this build.
ON_GCD_SPELLS = {
    17,       # Power Word: Shield
    589,      # Shadow Word: Pain
    8092,     # Mind Blast
    120644,   # Halo
    121536,   # Angelic Feather
    1227280,  # Tentacle Slam
    1242173,  # Void Volley (player-confirmed active cast)
    15407,    # Mind Flay
    228260,   # Voidform
    32379,    # Shadow Word: Death
    335467,   # Shadow Word: Madness
    34914,    # Vampiric Touch
    391403,   # Mind Flay: Insanity
}

CHANNEL_SPELLS = {15407, 391403}
PASSIVE_CAST_NAMES = {"Shadowy Apparition"}

# This mirrors the haste effects relevant to Shadow Priest from WoWAnalyzer's
# current Haste module and its shared Bloodlust map.
HASTE_BUFFS = {
    10060: 0.20,    # Power Infusion
    20572: 0.15,    # Blood Fury
    26297: 0.10,    # Berserking
    2825: 0.30,     # Bloodlust
    32182: 0.30,    # Heroism
    373316: 0.15,   # Idol of Y'Shaarj: Call of the Void
    373317: -0.10,  # Idol of Y'Shaarj: Overburdened Mind
    390386: 0.30,   # Fury of the Aspects
    80353: 0.30,    # Time Warp
    264667: 0.30,   # Primal Rage
    272678: 0.30,   # Primal Rage
    146555: 0.30,   # Ancient Hysteria
}

GCD_BASE_MS = 1500
GCD_MIN_MS = 750
HASTE_RATING_PER_PERCENT = 44  # WoWAnalyzer's current retail conversion


def _add_haste(base: float, bonus: float) -> float:
    if bonus < 0:
        return (base - abs(bonus)) / (1 + abs(bonus))
    return base * (1 + bonus) + bonus


def _remove_haste(base: float, bonus: float) -> float:
    if bonus < 0:
        return base * (1 + abs(bonus)) + abs(bonus)
    return (base - bonus) / (1 + bonus)


def _initial_haste_rating_percent(rating: float) -> float:
    """Convert rating using WoWAnalyzer's current retail secondary-stat DR."""
    percent = max(0.0, rating) / HASTE_RATING_PER_PERCENT / 100
    # Current secondary-stat breakpoints used by WoWAnalyzer.
    thresholds = [
        (0.30, 0.0),
        (0.40, 0.10),
        (0.50, 0.20),
        (0.60, 0.30),
        (0.80, 0.40),
        (1.00, 0.50),
        (2.00, 1.00),
    ]
    previous_base = 0.0
    previous_scaled = 0.0
    for base, penalty in thresholds:
        scaled = previous_scaled + max(0.0, min(percent, base) - previous_base) * (1 - penalty)
        if percent <= base:
            return scaled
        previous_base = base
        previous_scaled = scaled
    return previous_scaled + (percent - previous_base) * 0.0


def _spell(event: dict[str, Any]) -> dict[str, Any]:
    return event.get("ability") or {}


def _make_actions(events: list[dict[str, Any]], player_id: int) -> list[dict[str, Any]]:
    """Normalize casts/channels into GCD coverage spans, following WA's model."""
    own_cast_events = [
        e for e in events
        if e.get("sourceID") == player_id
        and e.get("type") in ("cast", "begincast")
        and _spell(e).get("name") not in PASSIVE_CAST_NAMES
    ]
    own_cast_events.sort(key=lambda e: e.get("timestamp", 0))

    actions: list[dict[str, Any]] = []
    pending_hardcast: dict[str, Any] | None = None

    for event in own_cast_events:
        spell = _spell(event)
        spell_id = spell.get("guid")
        name = spell.get("name") or "Unknown ability"
        timestamp = int(event["timestamp"])

        if event["type"] == "begincast":
            # A new hardcast cancels the previous unresolved hardcast.
            pending_hardcast = {"id": spell_id, "name": name, "start": timestamp}
            continue

        if spell_id in CHANNEL_SPELLS:
            # ChannelingNormalizer cancels an unresolved hardcast when a
            # special-case channel starts, then delimits this channel by its
            # matching aura removal.
            pending_hardcast = None
            channel_end = timestamp
            for later in events:
                if later.get("timestamp", 0) <= timestamp:
                    continue
                if (
                    later.get("type") in ("removebuff", "removedebuff")
                    and _spell(later).get("guid") == spell_id
                ):
                    channel_end = int(later["timestamp"])
                    break
                if (
                    later.get("sourceID") == player_id
                    and later.get("type") == "cast"
                    and _spell(later).get("guid") == spell_id
                ):
                    channel_end = int(later["timestamp"])
                    break
            if spell_id in ON_GCD_SPELLS:
                actions.append({"start": timestamp, "end": channel_end, "id": spell_id, "name": name})
            continue

        if pending_hardcast and pending_hardcast["id"] == spell_id:
            if spell_id in ON_GCD_SPELLS:
                actions.append({
                    "start": pending_hardcast["start"],
                    "end": timestamp,
                    "id": spell_id,
                    "name": name,
                })
            pending_hardcast = None
        elif spell_id in ON_GCD_SPELLS:
            # Instant casts trigger the GCD at the cast event timestamp.
            actions.append({"start": timestamp, "end": timestamp, "id": spell_id, "name": name})

    return sorted(actions, key=lambda action: action["start"])


def analyze_events(
    events: list[dict[str, Any]],
    player_id: int,
    fight_start: int,
    fight_end: int,
    player_name: str,
    report_code: str,
    fight_id: int,
) -> dict[str, Any]:
    events.sort(key=lambda e: e.get("timestamp", 0))
    combatant = next(
        (e for e in events if e.get("type") == "combatantinfo" and e.get("sourceID") == player_id),
        None,
    )
    if combatant is None:
        raise ValueError("The report did not return Combatant Info for this player/fight.")

    rating = max(
        float(combatant.get("hasteSpell") or 0),
        float(combatant.get("hasteMelee") or 0),
        float(combatant.get("hasteRanged") or 0),
    )
    haste = _initial_haste_rating_percent(rating)
    active: dict[tuple[int, int], float] = {}
    for aura in combatant.get("auras", []):
        ability_id = int(aura.get("ability", 0))
        bonus = HASTE_BUFFS.get(ability_id)
        if bonus is not None:
            key = (ability_id, int(aura.get("source", 0)))
            active[key] = bonus
            haste = _add_haste(haste, bonus)

    haste_events = []
    for event in events:
        if event.get("targetID") != player_id:
            continue
        ability_id = _spell(event).get("guid")
        if ability_id not in HASTE_BUFFS:
            continue
        kind = event.get("type")
        if kind in ("applybuff", "applydebuff"):
            haste_events.append((int(event["timestamp"]), 0, "add", (ability_id, int(event.get("sourceID", 0)))))
        elif kind in ("removebuff", "removedebuff"):
            haste_events.append((int(event["timestamp"]), 1, "remove", (ability_id, int(event.get("sourceID", 0)))))
    haste_events.sort()

    actions = _make_actions(events, player_id)
    action_counts: dict[str, int] = defaultdict(int)
    for action in actions:
        action_counts[action["name"]] += 1
    spell_damage: dict[str, int] = defaultdict(int)
    total_player_damage = 0
    for event in events:
        if event.get("type") == "damage" and event.get("sourceID") == player_id:
            amount = int(event.get("amount") or 0)
            spell_damage[_spell(event).get("name") or "Unknown ability"] += amount
            total_player_damage += amount

    # Exclude DoT damage from the broad average: the full fight's tick total
    # cannot be credited to one extra cast without modeling refresh timing.
    dot_spells = {589, 34914}  # Shadow Word: Pain, Vampiric Touch
    direct_action_names = {
        action["name"] for action in actions
        if action["id"] not in dot_spells and spell_damage.get(action["name"], 0) > 0
    }
    direct_action_count = sum(action_counts[name] for name in direct_action_names)
    average_damage_per_action = (
        sum(spell_damage[name] for name in direct_action_names) / direct_action_count
        if direct_action_count else 0
    )
    damage_per_action = {
        name: damage / action_counts[name]
        for name, damage in spell_damage.items()
        if action_counts.get(name, 0)
    }

    dynamic_haste = haste
    buff_index = 0
    gcd_spans = []
    min_gcd = float("inf")
    max_gcd = 0.0
    min_haste = float("inf")
    max_haste = 0.0

    for action in actions:
        while buff_index < len(haste_events) and haste_events[buff_index][0] <= action["start"]:
            _, _, operation, key = haste_events[buff_index]
            buff_index += 1
            bonus = HASTE_BUFFS[key[0]]
            if operation == "add" and key not in active:
                active[key] = bonus
                dynamic_haste = _add_haste(dynamic_haste, bonus)
            elif operation == "remove" and key in active:
                active_bonus = active.pop(key)
                dynamic_haste = _remove_haste(dynamic_haste, active_bonus)

        gcd_duration = max(GCD_MIN_MS, GCD_BASE_MS / (1 + dynamic_haste))
        active_end = max(float(action["end"]), action["start"] + gcd_duration)
        gcd_spans.append({
            **action,
            "haste": dynamic_haste,
            "gcd": gcd_duration,
            "activeEnd": active_end,
        })
        min_gcd = min(min_gcd, gcd_duration)
        max_gcd = max(max_gcd, gcd_duration)
        min_haste = min(min_haste, dynamic_haste)
        max_haste = max(max_haste, dynamic_haste)

    gaps: list[dict[str, Any]] = []
    if gcd_spans:
        coverage_end = gcd_spans[0]["activeEnd"]
        coverage_ability = gcd_spans[0]
        last_action = gcd_spans[0]
        for span in gcd_spans[1:]:
            if span["start"] > coverage_end:
                gaps.append({
                    "fromTime": last_action["start"],
                    "fromAbility": last_action["name"],
                    "coverageEnd": coverage_end,
                    "coverageAbility": coverage_ability["name"],
                    "toTime": span["start"],
                    "toAbility": span["name"],
                    "interval": span["start"] - last_action["start"],
                    "gcd": last_action["gcd"],
                    "idle": span["start"] - coverage_end,
                    "haste": last_action["haste"],
                })
                coverage_end = span["activeEnd"]
                coverage_ability = span
            else:
                if span["activeEnd"] > coverage_end:
                    coverage_end = span["activeEnd"]
                    coverage_ability = span
            last_action = span

    gaps = [gap for gap in gaps if gap["idle"] > 0]
    gaps.sort(key=lambda gap: gap["idle"], reverse=True)
    return {
        "reportCode": report_code,
        "fightId": fight_id,
        "playerId": player_id,
        "playerName": player_name,
        "fightStart": fight_start,
        "fightEnd": fight_end,
        "fightDuration": fight_end - fight_start,
        "eventCount": len(events),
        "gcdActionCount": len(gcd_spans),
        "initialHasteRating": rating,
        "initialHaste": _initial_haste_rating_percent(rating),
        "hasteRange": [min_haste if gcd_spans else 0, max_haste],
        "gcdRange": [min_gcd if gcd_spans else 0, max_gcd],
        "gapCount": len(gaps),
        "gaps": gaps,
        "damagePerAction": damage_per_action,
        "averageDamagePerAction": average_damage_per_action,
        "totalPlayerDamage": total_player_damage,
    }
