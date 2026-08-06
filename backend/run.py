"""Run the FastAPI MIDI generation server from the backend folder."""

from __future__ import annotations

import logging
import os
import socket
import sys

import uvicorn


def _port_free(host: str, port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            sock.bind((host, port))
            return True
        except OSError:
            return False


def main() -> None:
    os.environ.setdefault("PYTHONUNBUFFERED", "1")
    try:
        sys.stdout.reconfigure(line_buffering=True)  # type: ignore[attr-defined]
        sys.stderr.reconfigure(line_buffering=True)  # type: ignore[attr-defined]
    except Exception:  # noqa: BLE001
        pass

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
        stream=sys.stdout,
        force=True,
    )

    # Use HOST=0.0.0.0 when deploying so the API is reachable outside localhost.
    host = os.getenv("HOST", "127.0.0.1").strip() or "127.0.0.1"
    preferred = int(os.getenv("PORT", "8000"))
    port = preferred
    bind_host = "0.0.0.0" if host == "0.0.0.0" else host
    check_host = "127.0.0.1" if bind_host == "0.0.0.0" else bind_host

    # Fail hard when PORT is busy so frontend NEXT_PUBLIC_API_URL stays in sync.
    # Opt-in: PORT_FALLBACK=1 restores the old "next free port" behaviour.
    if not _port_free(check_host, port):
        if os.getenv("PORT_FALLBACK", "0") == "1":
            for candidate in range(preferred + 1, preferred + 20):
                if _port_free(check_host, candidate):
                    port = candidate
                    print(
                        f"Port {preferred} busy — using {port} instead "
                        f"(PORT_FALLBACK=1). Update frontend "
                        f"NEXT_PUBLIC_API_URL to http://127.0.0.1:{port}",
                        flush=True,
                    )
                    break
            else:
                raise SystemExit(f"No free port found near {preferred}")
        else:
            raise SystemExit(
                f"Port {preferred} is already in use.\n"
                f"  Free that port, or set PORT=… in backend/.env and match\n"
                f"  frontend/.env.local NEXT_PUBLIC_API_URL "
                f"(e.g. http://127.0.0.1:{preferred}).\n"
                f"  Or set PORT_FALLBACK=1 to auto-pick the next free port."
            )

    reload = os.getenv("UVICORN_RELOAD", "0") == "1"
    display_host = "127.0.0.1" if host == "0.0.0.0" else host

    print(f"Starting MIDIgen API on http://{display_host}:{port}", flush=True)
    if host == "0.0.0.0":
        print(f"Listening on all interfaces (0.0.0.0:{port})", flush=True)
    print(f"Swagger UI: http://{display_host}:{port}/docs", flush=True)
    print(
        f"Frontend should use NEXT_PUBLIC_API_URL=http://{display_host}:{port}",
        flush=True,
    )
    print(f"Reload={'ON' if reload else 'OFF'}", flush=True)

    uvicorn.run(
        "app.main:app",
        host=bind_host,
        port=port,
        reload=reload,
        access_log=True,
        log_level="info",
    )


if __name__ == "__main__":
    main()
