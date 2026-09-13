"""Run the local-only Seasons motion prototypes: python3 prototypes/scroll-landing/serve.py."""
from http.server import ThreadingHTTPServer, SimpleHTTPRequestHandler
from pathlib import Path
from functools import partial
import argparse
import threading
import time
from refresh_data import refresh

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--port', type=int, default=8765)
args = parser.parse_args()
root = Path(__file__).resolve().parents[2]
def refresh_daily():
    while True:
        try:
            refresh()
        except Exception as error:
            print(f'Artwork refresh unavailable; retaining dated snapshot: {type(error).__name__}', flush=True)
        time.sleep(86400)

threading.Thread(target=refresh_daily, daemon=True).start()
print(f'Five prototypes: http://localhost:{args.port}/prototypes/scroll-landing/?variant=A', flush=True)
ThreadingHTTPServer(('127.0.0.1', args.port), partial(SimpleHTTPRequestHandler, directory=str(root))).serve_forever()
