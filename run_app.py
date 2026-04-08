"""
Desktop launcher for packaged build.

- Starts FastAPI/OPC bridge with uvicorn.
- Opens the web UI in default browser after startup.
"""

from __future__ import annotations

import os
import threading
import webbrowser

import uvicorn
from main import app


def _open_ui() -> None:
    webbrowser.open("http://127.0.0.1:8000", new=2)


def _should_open_browser() -> bool:
    v = os.getenv("OPEN_BROWSER", "1").strip().lower()
    return v in {"1", "true", "yes", "on"}


def main() -> None:
    # Delay browser open so server has time to bind.
    if _should_open_browser():
        threading.Timer(1.5, _open_ui).start()
    uvicorn.run(
        app,
        host="0.0.0.0",
        port=8000,
        reload=False,
        log_level="info",
    )


if __name__ == "__main__":
    main()
