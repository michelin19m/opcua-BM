"""
Desktop launcher for packaged build.

- Starts FastAPI/OPC bridge with uvicorn.
- Opens the web UI in default browser after startup.
"""

from __future__ import annotations

import threading
import webbrowser

import uvicorn


def _open_ui() -> None:
    webbrowser.open("http://127.0.0.1:8000", new=2)


def main() -> None:
    # Delay browser open so server has time to bind.
    threading.Timer(1.5, _open_ui).start()
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8000,
        reload=False,
        log_level="info",
    )


if __name__ == "__main__":
    main()
