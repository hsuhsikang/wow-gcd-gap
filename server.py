"""Local web server plus a thin proxy to WoWAnalyzer's public WCL data route."""

from __future__ import annotations

import json
import re
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qs, urlencode, urlparse
from urllib.request import Request, urlopen

from analyzer import analyze_events


ROOT = Path(__file__).resolve().parent
WCL_API = "https://wowanalyzer.com/i/v1"
DEFAULT_REPORT = "https://www.warcraftlogs.com/reports/tKGJ2NCQvfxRwMd3?fight=22&type=casts&source=17&view=events"


def get_json(url: str) -> dict:
    request = Request(url, headers={"User-Agent": "CastGapReview/0.2"})
    try:
        with urlopen(request, timeout=60) as response:
            return json.loads(response.read())
    except HTTPError as error:
        detail = error.read().decode("utf-8", "replace")[:500]
        raise RuntimeError(f"WoW Analyzer data request failed ({error.code}): {detail}") from error
    except URLError as error:
        raise RuntimeError(f"Could not reach WoW Analyzer's public report data route: {error.reason}") from error


def parse_report_url(raw_url: str) -> tuple[str, dict[str, list[str]]]:
    parsed = urlparse(raw_url.strip())
    match = re.search(r"/reports/([A-Za-z0-9]+)", parsed.path)
    if match:
        return match.group(1), parse_qs(parsed.query)
    # Also accept the bare report code.
    if re.fullmatch(r"[A-Za-z0-9]+", raw_url.strip()):
        return raw_url.strip(), {}
    raise ValueError("Paste a Warcraft Logs report URL or report code.")


def first(params: dict[str, list[str]], *keys: str, default: str = "") -> str:
    for key in keys:
        values = params.get(key)
        if values and values[0]:
            return values[0]
    return default


def load_analysis(raw_url: str, player_name_hint: str = "Irohaa") -> dict:
    code, params = parse_report_url(raw_url)
    try:
        fight_id = int(first(params, "fight", "fightID", default="22"))
    except ValueError as error:
        raise ValueError("The report URL needs a numeric fight ID, such as fight=22.") from error

    report = get_json(f"{WCL_API}/report/fights/{code}?translate=true")
    fight = next((item for item in report.get("fights", []) if item.get("id") == fight_id), None)
    if fight is None:
        raise ValueError(f"Fight {fight_id} was not found in this report.")

    source_value = first(params, "source", "sourceID", "actorid")
    friendlies = report.get("friendlies", [])
    player = None
    if source_value:
        try:
            player_id = int(source_value)
        except ValueError as error:
            raise ValueError("The source/player ID in the report URL must be numeric.") from error
        player = next((actor for actor in friendlies if actor.get("id") == player_id), None)
    else:
        player = next((actor for actor in friendlies if actor.get("name", "").casefold() == player_name_hint.casefold()), None)
        if player is None and len(friendlies) == 1:
            player = friendlies[0]
        if player is None:
            names = ", ".join(actor.get("name", "?") for actor in friendlies[:12])
            raise ValueError(f"No source ID is in the URL and player '{player_name_hint}' was not found. Players include: {names}")
        player_id = int(player["id"])

    if player and all(entry.get("id") != player_id for entry in friendlies):
        raise ValueError(f"Player ID {player_id} is not listed in this report.")
    player_name = player.get("name", player_name_hint) if player else player_name_hint

    start = int(fight["start_time"])
    end = int(fight["end_time"])
    event_list: list[dict] = []
    cursor = start
    for _ in range(20):
        query = urlencode({"start": cursor, "end": end, "actorid": player_id, "translate": "true"})
        page = get_json(f"{WCL_API}/report/events/{code}?{query}")
        event_list.extend(page.get("events", []))
        next_cursor = page.get("nextPageTimestamp")
        if not next_cursor or int(next_cursor) <= cursor or int(next_cursor) > end:
            break
        cursor = int(next_cursor)
    else:
        raise RuntimeError("The event stream exceeded the page limit; narrow the report to one fight.")

    result = analyze_events(
        event_list,
        player_id=player_id,
        fight_start=start,
        fight_end=end,
        player_name=player_name,
        report_code=code,
        fight_id=fight_id,
    )
    result["encounter"] = fight.get("name") or "Encounter"
    result["difficulty"] = fight.get("difficulty")
    result["kill"] = bool(fight.get("kill"))
    result["reportTitle"] = report.get("title") or "Warcraft Logs report"
    return result


class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(ROOT), **kwargs)

    def do_GET(self):
        parsed = urlparse(self.path)
        if parsed.path == "/api/analyze":
            params = parse_qs(parsed.query)
            raw_url = first(params, "url", default=DEFAULT_REPORT)
            player_name = first(params, "player", default="Irohaa")
            try:
                result = load_analysis(raw_url, player_name)
                self._json(200, result)
            except (ValueError, RuntimeError) as error:
                self._json(400, {"error": str(error)})
            except Exception as error:
                self._json(500, {"error": f"Could not analyze this report: {error}"})
            return
        return super().do_GET()

    def _json(self, status: int, value: dict):
        body = json.dumps(value, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)


if __name__ == "__main__":
    address = ("127.0.0.1", 8000)
    print(f"Cast Gap Review: http://{address[0]}:{address[1]}")
    ThreadingHTTPServer(address, Handler).serve_forever()
