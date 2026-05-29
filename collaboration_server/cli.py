from __future__ import annotations

import argparse
from pathlib import Path
from typing import Optional

import uvicorn

from .app import create_app


def serve_forever(argv: Optional[list[str]] = None) -> None:
    parser = argparse.ArgumentParser(description="Run the GuLiCode Collaboration Server")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8787)
    parser.add_argument("--db", type=Path, default=Path("logs/collaboration_server.sqlite3"))
    parser.add_argument("--seed-config", type=Path, default=None)
    parser.add_argument("--secure-cookies", action="store_true")
    parser.add_argument("--log-dir", type=Path, default=Path("logs"))
    parser.add_argument("--log-level", default="INFO")
    args = parser.parse_args(argv)
    app = create_app(
        db_path=args.db,
        seed_config=args.seed_config,
        secure_cookies=bool(args.secure_cookies),
        log_dir=args.log_dir,
        log_level=args.log_level,
    )
    uvicorn.run(app, host=args.host, port=args.port)
