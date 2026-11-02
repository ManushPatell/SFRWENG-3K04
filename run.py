#!/usr/bin/env python3
"""Start the Automated Dispensing Cabinet and open it in a browser.

    python3 run.py                  # http://127.0.0.1:8000
    python3 run.py --port 8080
    python3 run.py --store adc.json # records survive a restart

Standard library only. Nothing to install.
"""
import argparse
import webbrowser

from demo_server import serve

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--store", default=None)
    parser.add_argument("--no-browser", action="store_true")
    args = parser.parse_args()

    demo, server = serve(args.port, args.store)
    url = "http://127.0.0.1:%s/" % args.port
    print("Automated Dispensing Cabinet running at", url)
    print("Mode:", demo.cabinet.modes.mode().value,
          "  Link:", demo.cabinet.link.state().value)
    print("Sign in as N001/1111 (nurse). Ctrl-C to stop.")

    if not args.no_browser:
        try:
            webbrowser.open(url)
        except Exception:
            pass
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nstopping")
    finally:
        demo.stop()
        demo.cabinet.shutdown()
        server.server_close()
