# Cast Gap Review

A small static website for reviewing raw intervals between Shadow Priest cast events exported from Warcraft Logs.

## Run locally

From this directory, start a local server:

```sh
python3 -m http.server 8000
```

Then open <http://localhost:8000>.

## Current report

The sample report is The Lost Explorers Mythic kill, fight 22, for Irohaa. The source export is represented in `data/events.json`.

The first pass excludes only `Shadowy Apparition`, following the current manual rule. All other exported event rows are kept. The interval is the timestamp difference between consecutive included events; cast and channel durations are not subtracted, so the list is a candidate-gap review rather than confirmed idle time.

Use **Import CSV** to load another Warcraft Logs Events CSV. Imported rows are filtered to source `Irohaa`, sorted by timestamp, and evaluated with the selected minimum interval.
