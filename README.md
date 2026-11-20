# Cast Gap Review

A local Shadow Priest cast-gap report with GCD durations that change with logged haste buffs.

## Run locally

From this directory:

```sh
python3 server.py
```

Open <http://127.0.0.1:8000>.

Paste a Warcraft Logs report URL with `fight` and `source` selected. If the URL has no `source` parameter, the analyzer looks for the player name entered in the form. The local server fetches the report metadata and the fight's parsed events through WoW Analyzer's public report-data route.

## Current analysis model

- Starts from the player's `CombatantInfo` haste rating.
- Applies recognized haste buffs as their logged aura events begin and end.
- Calculates a 1,500 ms GCD divided by current haste, with a 750 ms minimum.
- Treats cast bars and channels as active coverage, then lists positive uncovered time between GCD coverage windows.
- Excludes `Shadowy Apparition` and includes `Void Volley` as an active GCD ability, following the current project rules.

The GCD, haste, and channel model follows WoWAnalyzer's open-source implementation. The local analyzer currently carries a Shadow Priest spell list and the haste effects used by this report; future patch changes may need matching spell or buff updates. `data/gcd-report.json` is the seeded report snapshot for The Lost Explorers Mythic kill, fight 22, player Irohaa.
