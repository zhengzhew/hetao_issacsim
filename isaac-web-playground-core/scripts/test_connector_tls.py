"""The supplied internal CA must not become general-purpose application trust."""
from pathlib import Path
import ssl
import sys
import unittest

sys.path.insert(0, str(Path(__file__).parents[1] / 'tools'))
from connector_tls import ssl_context, websocket_ssl_options

ROOT_CA = ssl.PEM_cert_to_DER_cert((Path(__file__).parents[1] /
    'tools/certificates/10.72.255.16-root.crt').read_text(encoding='ascii'))


class TLSContextTests(unittest.TestCase):
    def test_https_and_wss_trust_the_supplied_ca_and_require_verification(self):
        for url in ('https://10.72.255.16', 'https://10.72.255.16:443/platform/pair',
                    'wss://10.72.255.16/platform/teleop'):
            with self.subTest(url=url):
                context = ssl_context(url)
                self.assertIn(ROOT_CA, context.get_ca_certs(binary_form=True))
                self.assertEqual(context.verify_mode, ssl.CERT_REQUIRED)
                self.assertTrue(context.check_hostname)
        context = websocket_ssl_options('wss://10.72.255.16/platform/teleop')['context']
        self.assertIn(ROOT_CA, context.get_ca_certs(binary_form=True))
        self.assertEqual(context.verify_mode, ssl.CERT_REQUIRED)
        self.assertTrue(context.check_hostname)

    def test_other_origins_do_not_trust_the_internal_ca(self):
        for url in ('https://example.invalid', 'https://10.72.255.160',
                    'https://10.72.255.16.example.invalid',
                    'https://10.72.255.16:8443', 'http://10.72.255.16:8080'):
            with self.subTest(url=url):
                context = ssl_context(url)
                self.assertNotIn(ROOT_CA, context.get_ca_certs(binary_form=True))
                self.assertEqual(context.verify_mode, ssl.CERT_REQUIRED)
                self.assertTrue(context.check_hostname)
        self.assertEqual(websocket_ssl_options('ws://localhost:8080/platform/teleop'), {})


if __name__ == '__main__':
    unittest.main()
