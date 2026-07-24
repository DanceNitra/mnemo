"""Reference witness HTTP server -- stdlib only, no web framework, no new dependency.

Stand up your OWN independent co-signing witness:

    python -m inspeximus.witness_server --port 9700 --state witness.json [--secret <hex>]

Endpoints:
    GET  /pubkey                     -> {"pubkey": <hex>}
    POST /cosign  {store_id, anchor} -> 200 {"pubkey","sig"}   (co-signed)
                                     -> 409 {"refused": reason} (a fork/rollback -- the split-view defense)

This is a REFERENCE you run on an INDEPENDENT host/party, not a hosted service. A client gathers k-of-n
co-signatures (inspeximus.witness_pool.collect_cosignatures with inspeximus.witness_pool.http_witness(url))
and a forked head cannot reach threshold because honest witnesses refuse it. The witness persists its per-store
last-signed head to `--state` so the refusal survives a restart. Bind to 127.0.0.1 by default; put it behind
your own TLS/reverse-proxy for a real deployment.
"""
from __future__ import annotations
import json, argparse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from .witness_pool import Witness


def _make_handler(witness: Witness):
    class Handler(BaseHTTPRequestHandler):
        def _send(self, code: int, obj: dict):
            body = json.dumps(obj).encode()
            self.send_response(code)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):
            if self.path.rstrip("/") == "/pubkey":
                self._send(200, {"pubkey": witness.public})
            else:
                self._send(404, {"error": "not found"})

        def do_POST(self):
            if self.path.rstrip("/") != "/cosign":
                self._send(404, {"error": "not found"}); return
            try:
                n = int(self.headers.get("Content-Length") or 0)
                body = json.loads(self.rfile.read(n) or b"{}")
                store_id, anchor = body.get("store_id"), body.get("anchor")
                if not store_id or not isinstance(anchor, dict):
                    self._send(400, {"error": "need {store_id, anchor}"}); return
                pk, sig = witness.cosign(store_id, anchor)
                self._send(200, {"pubkey": pk, "sig": sig})
            except ValueError as e:                       # witness refused a fork/rollback
                self._send(409, {"refused": str(e)})
            except Exception as e:
                self._send(500, {"error": f"{type(e).__name__}: {e}"})

        def log_message(self, *a):                        # quiet by default
            pass
    return Handler


def serve(port: int = 9700, host: str = "127.0.0.1", state_path: str | None = None,
          secret_hex: str | None = None):
    """Run a witness server (blocking). Returns never; Ctrl-C to stop."""
    w = Witness(secret_hex=secret_hex, state_path=state_path)
    httpd = ThreadingHTTPServer((host, port), _make_handler(w))
    print(f"inspeximus witness on http://{host}:{port}  pubkey={w.public}", flush=True)
    print(f"  add to a client allowlist as: {w.public}", flush=True)
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        httpd.shutdown()


def main():
    ap = argparse.ArgumentParser(description="inspeximus reference witness server")
    ap.add_argument("--port", type=int, default=9700)
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--state", default=None, help="json file persisting the per-store last-signed head")
    ap.add_argument("--secret", default=None, help="Ed25519 secret hex (omit to mint a fresh key)")
    a = ap.parse_args()
    serve(a.port, a.host, a.state, a.secret)


if __name__ == "__main__":
    main()
