import os
import sys
import socket
import threading
import webbrowser
import signal
import time
from pathlib import Path
import platform
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
SERVER_THREAD: threading.Thread | None = None


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

    # Run the server in a background thread so we can show a native window
    def _run_server():
        try:
            SERVER.run()
        except Exception as e:
            print(f"FATAL: server failed to start: {e}")
    SERVER_THREAD = threading.Thread(target=_run_server, name="datasetcutter-server", daemon=True)
    SERVER_THREAD.start()

    def _wait_until_up(timeout=5.0):
        start = time.time()
        import urllib.request
        while time.time() - start < timeout:
            try:
                with urllib.request.urlopen(f"{url}/api/ping", timeout=0.5) as r:
                    if r.status == 200:
                        return True
            except Exception:
                pass
            time.sleep(0.1)
        return False

    _wait_until_up(5.0)

    def _open_browser():
        try:
            webbrowser.open(url)
        except Exception:
            pass

    # If we're bundled on macOS, show a small native window with Quit/Open buttons.
    in_bundle = bool(getattr(sys, "_MEIPASS", None))
    on_macos = platform.system() == 'Darwin'
    show_window = on_macos and (in_bundle or os.environ.get('SHOW_WINDOW') == '1')

    if show_window:
        try:
            from AppKit import (
                NSApplication, NSWindow, NSButton, NSTextField, NSView,
                NSMakeRect, NSBackingStoreBuffered,
                NSWindowStyleMaskTitled, NSWindowStyleMaskClosable, NSWindowStyleMaskMiniaturizable,
                NSApplicationActivationPolicyRegular,
            )
            from AppKit import NSApplicationActivateIgnoringOtherApps
            import objc

            class Controller(objc.lookUpClass('NSObject')):
                def init(self):
                    self = objc.super(Controller, self).init()
                    self._url = url
                    return self

                def open_(self, sender):
                    _open_browser()

                def quit_(self, sender):
                    try:
                        if SERVER is not None:
                            SERVER.should_exit = True
                    except Exception:
                        pass
                    # Give the server a moment to exit, then terminate the app
                    def _delayed_terminate():
                        for _ in range(20):
                            if SERVER is None:
                                break
                            if getattr(SERVER, 'should_exit', False):
                                # best-effort wait for thread to end
                                time.sleep(0.1)
                            time.sleep(0.05)
                        NSApplication.sharedApplication().terminate_(None)
                    threading.Thread(target=_delayed_terminate, daemon=True).start()

            app = NSApplication.sharedApplication()
            app.setActivationPolicy_(NSApplicationActivationPolicyRegular)

            style = (NSWindowStyleMaskTitled | NSWindowStyleMaskClosable | NSWindowStyleMaskMiniaturizable)
            window = NSWindow.alloc().initWithContentRect_styleMask_backing_defer_(
                NSMakeRect(0, 0, 520, 160), style, NSBackingStoreBuffered, False
            )
            window.setTitle_("Dataset Cutter")

            content = window.contentView()
            assert isinstance(content, NSView)

            ctrl = Controller.alloc().init()

            label = NSTextField.alloc().initWithFrame_(NSMakeRect(20, 100, 480, 24))
            label.setStringValue_(f"Server: {url}")
            label.setBezeled_(False)
            label.setDrawsBackground_(False)
            label.setEditable_(False)
            label.setSelectable_(True)
            content.addSubview_(label)

            btn_open = NSButton.alloc().initWithFrame_(NSMakeRect(20, 50, 140, 32))
            btn_open.setTitle_("Open UI")
            btn_open.setTarget_(ctrl)
            btn_open.setAction_("open:")
            content.addSubview_(btn_open)

            btn_quit = NSButton.alloc().initWithFrame_(NSMakeRect(180, 50, 140, 32))
            btn_quit.setTitle_("Quit Server")
            btn_quit.setTarget_(ctrl)
            btn_quit.setAction_("quit:")
            content.addSubview_(btn_quit)

            window.center()
            window.makeKeyAndOrderFront_(None)
            app.activateIgnoringOtherApps_(True)

            # Run the Cocoa app event loop (blocks until Quit)
            app.run()
        except Exception as e:
            print(f"Window failed ({e}); opening browser instead")
            _open_browser()
            # Keep process alive until server thread ends (Ctrl+C or API /api/quit)
            try:
                while SERVER_THREAD and SERVER_THREAD.is_alive():
                    time.sleep(0.2)
            except KeyboardInterrupt:
                _handle_signal(signal.SIGINT, None)
    else:
        # Dev or non-macOS: open browser and keep process alive
        threading.Timer(0.8, _open_browser).start()
        try:
            while SERVER_THREAD and SERVER_THREAD.is_alive():
                time.sleep(0.2)
        except KeyboardInterrupt:
            _handle_signal(signal.SIGINT, None)
