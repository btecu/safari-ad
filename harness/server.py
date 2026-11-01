#!/usr/bin/env python3
"""Static file server for the repo root that also accepts result reports from fixture pages.

POST /report?name=<name>  (JSON body) -> saved to out/reports/<name>.json
This lets a page opened in a normal (non-WebDriver) Safari window send its results back.
"""
import json
import re
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

ROOT = Path(__file__).resolve().parent.parent
REPORTS = ROOT / "out" / "reports"


class Handler(SimpleHTTPRequestHandler):
    def do_POST(self):
        u = urlparse(self.path)
        name = re.sub(r"[^\w.-]", "_", parse_qs(u.query).get("name", ["report"])[0])
        if u.path != "/report":
            self.send_error(404)
            return
        body = self.rfile.read(int(self.headers.get("Content-Length", 0)))
        REPORTS.mkdir(parents=True, exist_ok=True)
        (REPORTS / f"{name}.json").write_text(json.dumps(json.loads(body), indent=2))
        self.send_response(204)
        self.end_headers()


if __name__ == "__main__":
    ThreadingHTTPServer(("127.0.0.1", 8000), partial(Handler, directory=str(ROOT))).serve_forever()
