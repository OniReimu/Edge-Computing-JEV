#!/usr/bin/env python3
"""Entrypoint for Dockerised OCR worker service binding to 0.0.0.0 and supporting /upload."""
import argparse
from http.server import ThreadingHTTPServer
import json
from pathlib import Path
import sys
from urllib.parse import urlsplit

from src.ocr_service import Worker, server


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--node", required=True)
    p.add_argument("--port", type=int, default=18764)
    p.add_argument("--binary", default="tesseract")
    p.add_argument("--weights", default="/app/weights")
    p.add_argument("--log", default="/app/worker.log")
    args = p.parse_args()

    weights = {
        tier: str(Path(args.weights) / name)
        for tier, name in [("standard", "tessdata_fast"), ("high", "tessdata_best")]
    }

    worker = Worker(args.node, args.binary, weights, args.log)
    dummy_srv = server(worker, 0)
    BaseHandler = dummy_srv.RequestHandlerClass
    dummy_srv.server_close()

    class WorkerHandler(BaseHandler):
        def do_POST(self):
            parts = urlsplit(self.path)
            if parts.path == "/upload":
                length = int(self.headers.get("Content-Length", "0"))
                data = self.rfile.read(length)
                return self.reply(200, {"status": "ok", "bytes_received": len(data)})
            return super().do_POST()

    service = ThreadingHTTPServer(("0.0.0.0", args.port), WorkerHandler)
    ready_msg = dict(
        ready=True,
        node=args.node,
        port=service.server_port,
        engine=worker.version,
        weights=worker.hashes,
    )
    print(json.dumps(ready_msg), flush=True)
    service.serve_forever()


if __name__ == "__main__":
    main()
