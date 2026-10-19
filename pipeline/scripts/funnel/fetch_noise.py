"""Download every noise/ object from the local site's internal API (GET only) into ./noise/.

Read-only: lists with GET /api/internal/objects?prefix=noise/ (following the cursor) and fetches
each key with GET /api/internal/objects/<key>. Nothing is written to the site or the repository.
"""
import json
import pathlib
import sys
import urllib.parse
import urllib.request

BASE = "http://localhost:5173/api/internal/objects"
HEADERS = {"Authorization": "Bearer dev-local-token"}  # local development token
OUT = pathlib.Path(__file__).resolve().parents[3] / "data" / "funnel" / "noise"


def get(url: str) -> bytes:
    with urllib.request.urlopen(urllib.request.Request(url, headers=HEADERS), timeout=60) as r:
        return r.read()


def main() -> None:
    keys, cursor = [], None
    while True:
        q = {"prefix": "noise/"}
        if cursor:
            q["cursor"] = cursor
        page = json.loads(get(BASE + "?" + urllib.parse.urlencode(q)))
        keys += page["keys"]
        cursor = page.get("cursor")
        if not cursor:
            break
    OUT.mkdir(exist_ok=True)
    for key in keys:
        body = get(BASE + "/" + urllib.parse.quote(key, safe="/"))
        (OUT / key.replace("/", "__")).write_bytes(body)
    print(json.dumps({"keys": len(keys)}))


if __name__ == "__main__":
    sys.exit(main())
