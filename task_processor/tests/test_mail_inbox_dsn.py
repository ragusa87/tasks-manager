from django.core.exceptions import ImproperlyConfigured
from django.test import SimpleTestCase

from task_processor.mail_inbox.dsn import DEFAULT_MAX_SIZE, parse_dsn


class ParseDSNTests(SimpleTestCase):
    def test_smtp_with_port_and_max_size(self):
        dsn = parse_dsn("smtp://0.0.0.0:2525?max_size=1024")
        self.assertEqual(dsn.scheme, "smtp")
        self.assertEqual(dsn.host, "0.0.0.0")
        self.assertEqual(dsn.port, 2525)
        self.assertEqual(dsn.max_size, 1024)

    def test_smtp_default_port_and_max_size(self):
        dsn = parse_dsn("smtp://localhost")
        self.assertEqual(dsn.port, 2525)
        self.assertEqual(dsn.max_size, DEFAULT_MAX_SIZE)

    def test_imaps_with_credentials(self):
        dsn = parse_dsn("imaps://user%40host:pa%3Ass@mail.example.com/INBOX?poll=30")
        self.assertEqual(dsn.scheme, "imaps")
        self.assertEqual(dsn.host, "mail.example.com")
        self.assertEqual(dsn.port, 993)
        self.assertEqual(dsn.username, "user@host")
        self.assertEqual(dsn.password, "pa:ss")
        self.assertEqual(dsn.path, "/INBOX")
        self.assertEqual(dsn.poll_interval, 30)

    def test_unknown_scheme_raises(self):
        with self.assertRaises(ImproperlyConfigured):
            parse_dsn("pop3://localhost")

    def test_missing_host_raises(self):
        with self.assertRaises(ImproperlyConfigured):
            parse_dsn("smtp://")

    def test_bad_port_raises(self):
        with self.assertRaises(ImproperlyConfigured):
            parse_dsn("smtp://localhost:notaport")

    def test_bad_max_size_raises(self):
        dsn = parse_dsn("smtp://localhost?max_size=big")
        with self.assertRaises(ImproperlyConfigured):
            dsn.max_size
