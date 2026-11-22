import argparse
import threading
import time
import webbrowser

from backend.settings import load_environment

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--app", action="store_true", help="Run the main app")
    parser.add_argument("--host", default="127.0.0.1", help="Browser UI host")
    parser.add_argument("--port", default=8000, type=int, help="Browser UI port")
    parser.add_argument(
        "--no-browser",
        action="store_true",
        help="Start the browser UI server without opening a browser tab.",
    )

    args = parser.parse_args()
    load_environment()

    if args.app:
        import uvicorn

        if not args.no_browser:
            threading.Timer(
                0.8,
                lambda: webbrowser.open(f"http://{args.host}:{args.port}/?v={time.time_ns()}"),
            ).start()
        from backend.app import app

        server = uvicorn.Server(uvicorn.Config(app, host=args.host, port=args.port, reload=False))
        app.state.uvicorn_server = server
        server.run()
