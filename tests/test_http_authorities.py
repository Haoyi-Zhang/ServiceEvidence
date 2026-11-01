"""Authority candidates retain explicit ports and reject even empty userinfo."""
import unittest
from cie.http_adapter import authority_handle

class AuthorityCandidates(unittest.TestCase):
    def test_port_zero_is_not_the_default_port(self):
        self.assertEqual(authority_handle('http://example.test:0/path'),'http://example.test:0')
        self.assertEqual(authority_handle('https://[::1]:0/path'),'https://[::1]:0')
        self.assertNotEqual(authority_handle('https://example.test:0'),authority_handle('https://example.test'))

    def test_empty_userinfo_is_still_userinfo(self):
        for value in ('http://@example.test','http://:@example.test','http://:secret@example.test'):
            with self.subTest(value=value),self.assertRaises(ValueError):authority_handle(value)

    def test_only_explicit_default_ports_are_removed(self):
        self.assertEqual(authority_handle('https://EXAMPLE.test:443/p'),'https://example.test')
        self.assertEqual(authority_handle('http://EXAMPLE.test:80/p'),'http://example.test')
        self.assertEqual(authority_handle('https://EXAMPLE.test:80/p'),'https://example.test:80')
        self.assertEqual(authority_handle('http://[::1]:8080/p'),'http://[::1]:8080')

if __name__=='__main__':unittest.main()
