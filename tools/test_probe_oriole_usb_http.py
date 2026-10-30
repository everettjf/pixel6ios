"""The local Safari probe must reject ambiguous targets and false HTTP hits."""

from http.client import HTTPConnection
from http.server import HTTPServer
from threading import Event, Thread
import unittest
from unittest.mock import patch

import probe_oriole_usb_http as probe


class LocalHttpProbeTests(unittest.TestCase):
    def setUp(self):
        self.state = {
            'distinct_candidate': True,
            'usb_1209_0001_count': 1,
            'host_ip': '192.168.7.1',
            'host_ip_interfaces': ['en9'],
            'default_uplink': 'en1',
        }

    def test_unique_usb_candidate(self):
        self.assertEqual(probe.verify_candidate(self.state), 'en9')

    def test_ambiguous_or_absent_candidate_is_refused(self):
        cases = [
            ('distinct_candidate', False),
            ('usb_1209_0001_count', 0),
            ('usb_1209_0001_count', 2),
            ('host_ip', '192.168.1.1'),
            ('host_ip_interfaces', []),
            ('host_ip_interfaces', ['en8', 'en9']),
            ('default_uplink', 'en9'),
        ]
        for field, value in cases:
            with self.subTest(field=field, value=value):
                with self.assertRaises(ValueError):
                    probe.verify_candidate(dict(self.state, **{field: value}))

    def test_http_challenge_requires_phone_source_and_exact_path(self):
        ready = Event()
        listening_port = []
        result = []

        class LoopbackServer(HTTPServer):
            def __init__(self, address, handler):
                super().__init__(address, handler)
                listening_port.append(self.server_port)
                ready.set()

        def request(path):
            connection = HTTPConnection('127.0.0.1', listening_port[0], timeout=2)
            try:
                connection.request('GET', path)
                response = connection.getresponse()
                return response.status, response.read()
            finally:
                connection.close()

        loopback_state = dict(self.state, host_ip='127.0.0.1')
        with (patch.object(probe, 'HOST_IP', '127.0.0.1'),
              patch.object(probe, 'PHONE_IP', '127.0.0.2'),
              patch.object(probe, 'HTTPServer', LoopbackServer),
              patch.object(probe.secrets, 'token_hex', return_value='feedcafe12345678')):
            worker = Thread(target=lambda: result.append(probe.serve(0, 4, loopback_state)),
                            daemon=True)
            worker.start()
            self.assertTrue(ready.wait(2))
            path = '/probe/feedcafe12345678'
            self.assertEqual(request(path)[0], 404)  # wrong client IP
            with patch.object(probe, 'PHONE_IP', '127.0.0.1'):
                self.assertEqual(request('/probe/other')[0], 404)
                status, body = request(path)
                self.assertEqual(status, 200)
                self.assertEqual(body, b'Pixel 6 USB local HTTP: OK\n')
            worker.join(3)
            self.assertFalse(worker.is_alive())
            self.assertEqual(result, [True])


if __name__ == '__main__':
    unittest.main()
