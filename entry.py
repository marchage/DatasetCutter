import os
import sys
import socket
import threading
import webbrowser
import signal
import time
from pathlib import Path
import uvicorn

def find_free_port(start: int, limit: int = 20) -> int:
    for p in range(start, start + limit):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            try:
                s.bind(('127.0.0.1', p))
                return p
            except OSError:
                continue
    return start


SERVER: uvicorn.Server | None = None


if __name__ == '__main__':
    # Prepare a persistent log file so we can see errors when launched as a .app
    base_dir = Path.home() / "DatasetCutter" / "data"
    base_dir.mkdir(parents=True, exist_ok=True)
    log_file = base_dir / "server.log"
    try:
        sys.stdout = open(log_file, 'a', buffering=1)
        sys.stderr = open(log_file, 'a', buffering=1)
    except Exception:
        pass

    # Make sure our bundled/static ffmpeg is preferred even with limited PATH in GUI apps
    try:
        dc_bin = Path.home() / "DatasetCutter" / "bin"
        ff = dc_bin / "ffmpeg"
        if ff.exists() and os.access(ff, os.X_OK):
            # Prepend to PATH and set explicit override so subprocess calls use it
            os.environ["PATH"] = f"{str(dc_bin)}:{os.environ.get('PATH','')}"
            os.environ["FFMPEG_BINARY"] = str(ff)
    except Exception:
        pass

    # Log basic entry context early (before importing app)
    try:
        in_bundle = bool(getattr(sys, "_MEIPASS", None))
        print(f"ENTRY: IN_BUNDLE={in_bundle} PATH={os.environ.get('PATH','')}")
        if os.environ.get("FFMPEG_BINARY"):
            print(f"ENTRY: FFMPEG_BINARY={os.environ.get('FFMPEG_BINARY')}")
    except Exception:
        pass

    # Import the FastAPI app after environment prep so ffmpeg discovery prefers our static binary
    try:
        from app.main import app  # type: ignore
    except Exception as e:
        print(f"FATAL: Failed to import FastAPI app: {e}")
        try:
            import time
            time.sleep(2)
        except Exception:
            pass
        raise SystemExit(1)

    # Read PORT from env or CLI args (e.g. open ... --args PORT=8014 or --port 8014)
    base_port = int(os.environ.get('PORT', '8000'))
    for i, arg in enumerate(sys.argv[1:]):
        if arg.startswith('PORT='):
            try:
                base_port = int(arg.split('=', 1)[1])
            except ValueError:
                pass
        elif arg in ('--port', '-p'):
            try:
                base_port = int(sys.argv[1:][i+1])
            except Exception:
                pass
        elif arg.startswith('--port='):
            try:
                base_port = int(arg.split('=', 1)[1])
            except ValueError:
                pass

    port = find_free_port(base_port)
    url = f"http://127.0.0.1:{port}"
    print(f"DatasetCutter server starting: {url}")

    # Prepare uvicorn server instance so we can shut it down gracefully
    config = uvicorn.Config(app, host='127.0.0.1', port=port, log_level="info")
    SERVER = uvicorn.Server(config)

    # Open the browser shortly after server starts
    threading.Timer(0.8, lambda: webbrowser.open(url)).start()

    # Graceful shutdown on signals
    def _handle_signal(signum, _frame):
        print(f"Signal {signum} received; requesting shutdown...")
        try:
            if SERVER is not None:
                SERVER.should_exit = True
        except Exception:
            pass

    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            signal.signal(sig, _handle_signal)
        except Exception:
            pass

    try:
        SERVER.run()
    except Exception as e:
        print(f"FATAL: server failed to start: {e}")
        # Keep the process alive briefly so the Dock doesn't swallow errors immediately
        try:
            time.sleep(2)
        except Exception:
            pass
