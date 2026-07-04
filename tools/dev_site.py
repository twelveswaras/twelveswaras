"""Live-reload dev server for the landing page (site/) — edit, save, the browser refreshes.

    python -m tools.dev_site                 # serve site/ at http://localhost:8777
    python -m tools.dev_site --port 9000

Stdlib only, no install. It serves site/ and injects a tiny poller into every .html response
that reloads the page whenever any file under site/ changes on disk.

To test the FULL integrated page against a LOCAL recognizer (so you can iterate on embed mode
without deploying), run the recognizer too:

    <inference-env>/python -m apps.identify         # recognizer on http://localhost:7860

then open:  http://localhost:8777/?recognizer=http://localhost:7860
(the ?recognizer= override points the embedded iframe at your local Space; prod uses the real one.)
"""
from __future__ import annotations

import argparse
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

SITE = Path(__file__).resolve().parent.parent / "site"

_POLLER = """
<script>
// dev live-reload: poll the server's file-mtime signature; reload when it changes
(function () {
  var last = null;
  setInterval(function () {
    fetch('/__mtime').then(function (r) { return r.text(); }).then(function (t) {
      if (last !== null && t !== last) location.reload();
      last = t;
    }).catch(function () {});
  }, 500);
})();
</script>
"""


def _signature() -> str:
    """A cheap change signature: the newest mtime across all files in site/."""
    return str(max((p.stat().st_mtime_ns for p in SITE.rglob("*") if p.is_file()), default=0))


class Handler(SimpleHTTPRequestHandler):
    def do_GET(self):  # noqa: N802
        if self.path.split("?")[0] == "/__mtime":
            body = _signature().encode()
            self.send_response(200)
            self.send_header("Content-Type", "text/plain")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)
            return

        rel = self.path.split("?")[0].lstrip("/") or "index.html"
        target = SITE / rel
        if target.is_dir():
            target = target / "index.html"
        if target.suffix == ".html" and target.is_file():
            html = target.read_text(encoding="utf-8")
            html = html.replace("</body>", _POLLER + "</body>") if "</body>" in html else html + _POLLER
            body = html.encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)
            return
        super().do_GET()

    def log_message(self, *a):  # quieter console
        pass


def main() -> None:
    ap = argparse.ArgumentParser(description="Live-reload dev server for site/.")
    ap.add_argument("--port", type=int, default=8777)
    args = ap.parse_args()
    handler = partial(Handler, directory=str(SITE))
    srv = ThreadingHTTPServer(("127.0.0.1", args.port), handler)
    print(f"serving {SITE} with live-reload at http://localhost:{args.port}", flush=True)
    print(f"  full integrated test:  http://localhost:{args.port}/?recognizer=http://localhost:7860", flush=True)
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        srv.shutdown()


if __name__ == "__main__":
    main()
