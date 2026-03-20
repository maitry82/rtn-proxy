#!/usr/bin/env python3
"""
╔══════════════════════════════════════════════════════════════╗
║   RTN SMART — CORS Proxy for Render.com                      ║
║   rtn_proxy_render.py                                        ║
╠══════════════════════════════════════════════════════════════╣
║   Deploy to Render.com (free):                               ║
║   1. Upload this file + render.yaml to a GitHub repo         ║
║   2. Connect repo to render.com → auto-deploys               ║
║   3. Use your Render URL in the test app                     ║
╚══════════════════════════════════════════════════════════════╝
"""

import http.server
import urllib.request
import urllib.error
import json
import os
import sys
import time
import traceback
from datetime import datetime

# Render provides PORT env var — must bind to it

PORT = int(os.environ.get('PORT', 5050))

ALLOWED_GATEWAYS = {
    'https://gateway-sb.clearent.net',
    'https://gateway-int.clearent.net',
    'https://gateway.clearent.net',
}

DEFAULT_GATEWAY = 'https://gateway-sb.clearent.net'

CORs_HEADERS = {
    'Access-Control-Allow-Origin':  '*',
    'Access-Control-Allow-Methods': 'GET, POST, PUT, DELETE, PATCH, OPTIONS',
    'Access-Control-Allow-Headers': 'Content-Type, AccessKey, MerchantId, X-Target-Gateway, Authorization',
    'Access-Control-Max-Age':       '86400',
}

PASSTHROUGH_HEADERS = {'accesskey', 'merchantid', 'content-type', 'authorization'}
STRIP_RESPONSE      = {'transfer-encoding', 'connection', 'keep-alive'}

def ts():
    return datetime.now().strftime('%H:%M:%S.%f')[:-3]

def log(tag, msg):
    print(f'[{ts()}] {tag:6} {msg}', flush=True)

class RTNProxyHandler(http.server.BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        pass  # suppress default logs

    def do_OPTIONS(self):
        self.send_response(200)
        self._cors()
        self.end_headers()

    def do_GET(self):    self._proxy('GET')
    def do_POST(self):   self._proxy('POST')
    def do_PUT(self):    self._proxy('PUT')
    def do_DELETE(self): self._proxy('DELETE')
    def do_PATCH(self):  self._proxy('PATCH')

    def _proxy(self, method):
        t0 = time.time()

        # Health check endpoint
        if self.path == '/health':
            body = json.dumps({'status': 'ok', 'service': 'RTN SMART CORS Proxy'}).encode()
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Content-Length', str(len(body)))
            self._cors()
            self.end_headers()
            self.wfile.write(body)
            return

        # Determine gateway
        gateway = self.headers.get('X-Target-Gateway', DEFAULT_GATEWAY).strip().rstrip('/')
        if gateway not in ALLOWED_GATEWAYS:
            log('BLOCK', f'Gateway not allowed: {gateway}')
            self._error(403, f'Gateway not allowed: {gateway}')
            return

        target_url = gateway + self.path
        log('REQ', f'{method} {target_url}')

        # Read body
        body_bytes = b''
        cl = int(self.headers.get('Content-Length', 0))
        if cl > 0:
            body_bytes = self.rfile.read(cl)

        # Forward headers
        fwd = {}
        for k, v in self.headers.items():
            if k.lower() in PASSTHROUGH_HEADERS:
                fwd[k] = v

        # Make request
        try:
            req = urllib.request.Request(
                url=target_url, data=body_bytes or None,
                headers=fwd, method=method
            )
            with urllib.request.urlopen(req, timeout=60) as resp:
                elapsed = round((time.time() - t0) * 1000)
                status   = resp.status
                rbody    = resp.read()
                rheaders = dict(resp.headers)
                log('RES', f'HTTP {status} · {elapsed}ms · {len(rbody)}B')

        except urllib.error.HTTPError as e:
            elapsed = round((time.time() - t0) * 1000)
            status   = e.code
            rbody    = b''
            try: rbody = e.read()
            except: pass
            rheaders = dict(e.headers) if e.headers else {}
            log('ERR', f'HTTP {status} from gateway · {elapsed}ms')

        except urllib.error.URLError as e:
            log('ERR', f'Cannot reach gateway: {e.reason}')
            self._error(502, f'Cannot reach gateway: {e.reason}')
            return

        except Exception as e:
            log('ERR', f'Unexpected: {e}')
            self._error(500, str(e))
            return

        # Send response
        self.send_response(status)
        self._cors()
        for k, v in rheaders.items():
            if k.lower() not in STRIP_RESPONSE and k.lower() != 'access-control-allow-origin':
                try: self.send_header(k, v)
                except: pass
        self.send_header('Content-Length', str(len(rbody)))
        self.end_headers()
        self.wfile.write(rbody)

    def _cors(self):
        for k, v in CORs_HEADERS.items():
            self.send_header(k, v)

    def _error(self, status, msg):
        body = json.dumps({'proxy-error': msg}).encode()
        self.send_response(status)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Content-Length', str(len(body)))
        self._cors()
        self.end_headers()
        self.wfile.write(body)

if __name__ == '__main__':
    print(f'', flush=True)
    print(f'╔══════════════════════════════════════════╗', flush=True)
    print(f'║  RTN SMART CORS Proxy — Render Edition   ║', flush=True)
    print(f'╚══════════════════════════════════════════╝', flush=True)
    print(f'  Listening on port {PORT}', flush=True)
    print(f'  Health check: /health', flush=True)
    print(f'', flush=True)

    server = http.server.ThreadingHTTPServer(('0.0.0.0', PORT), RTNProxyHandler)
    server.daemon_threads = True
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print('\nStopped.', flush=True)
        sys.exit(0)