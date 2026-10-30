#!/usr/bin/env python3
"""Serve one read-only HTTP challenge on a verified Pixel 6 USB host address.

This tests Safari -> Mac local TCP only. It does not enable forwarding, NAT,
DNS or Internet access, and it never changes a network interface.
"""

import argparse
from http.server import BaseHTTPRequestHandler, HTTPServer
import secrets
import subprocess
import time

from preflight_oriole_usb_host import HOST_IP, snapshot


PHONE_IP = '192.168.7.2'


def verify_candidate(state):
    candidates = state.get('host_ip_interfaces')
    if (state.get('distinct_candidate') is not True or
            state.get('usb_1209_0001_count') != 1 or
            state.get('host_ip') != HOST_IP or
            not isinstance(candidates, list) or len(candidates) != 1 or
            candidates[0] == state.get('default_uplink')):
        raise ValueError('Pixel 6 USB network candidate is not unique and active')
    return candidates[0]


def serve(port, seconds, state=None):
    interface = verify_candidate(snapshot() if state is None else state)
    token = secrets.token_hex(8)
    path = '/probe/' + token
    completed = False

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            nonlocal completed
            if self.client_address[0] != PHONE_IP or self.path != path:
                self.send_error(404)
                return
            body = b'Pixel 6 USB local HTTP: OK\n'
            self.send_response(200)
            self.send_header('Content-Type', 'text/plain; charset=utf-8')
            self.send_header('Content-Length', str(len(body)))
            self.send_header('Cache-Control', 'no-store')
            self.end_headers()
            self.wfile.write(body)
            completed = True

        def log_message(self, format, *args):
            pass

    with HTTPServer((HOST_IP, port), Handler) as server:
        server.timeout = 1
        deadline = time.monotonic() + seconds
        print(f'USB candidate {interface}; open http://{HOST_IP}:{server.server_port}{path} in Safari',
              flush=True)
        while not completed and time.monotonic() < deadline:
            server.handle_request()
    print('LOCAL HTTP PASS: phone reached Mac over USB' if completed else
          'LOCAL HTTP INCONCLUSIVE: no matching request before timeout')
    return completed


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--port', type=int, default=18080)
    parser.add_argument('--seconds', type=int, default=180)
    args = parser.parse_args()
    if not 1024 <= args.port <= 65535 or not 1 <= args.seconds <= 3600:
        parser.error('port must be 1024..65535 and seconds must be 1..3600')
    try:
        completed = serve(args.port, args.seconds)
    except (OSError, ValueError, subprocess.SubprocessError) as exc:
        parser.exit(2, f'LOCAL HTTP REFUSED: {exc}\n')
    if not completed:
        parser.exit(1)


if __name__ == '__main__':
    main()
