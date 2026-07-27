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
        self.assertEqual(dsn.mailbox, "INBOX")
        self.assertEqual(dsn.poll_interval, 30)
        self.assertTrue(dsn.use_ssl)

    def test_imaps_default_port_mailbox_and_poll(self):
        dsn = parse_dsn("imaps://user:pass@mail.example.com")
        self.assertEqual(dsn.port, 993)
        self.assertEqual(dsn.mailbox, "INBOX")
        self.assertEqual(dsn.poll_interval, 60)
        self.assertTrue(dsn.use_ssl)

    def test_imap_plaintext_is_not_ssl(self):
        dsn = parse_dsn("imap://user:pass@mail.example.com/Archive")
        self.assertEqual(dsn.port, 143)
        self.assertEqual(dsn.mailbox, "Archive")
        self.assertFalse(dsn.use_ssl)

    def test_percent_in_password_must_be_encoded_as_25(self):
        # A literal '%' in the password is carried as '%25' and decodes back to
        # a single '%', so the server receives the exact original password.
        dsn = parse_dsn("imaps://user:1129ku!GtL-%25lV%2AF@mail.example.com")
        self.assertEqual(dsn.password, "1129ku!GtL-%lV*F")

    def test_login_username_appends_default_domain(self):
        dsn = parse_dsn("imaps://inbox-x:pw@mail.example.com")
        self.assertEqual(dsn.login_username("tasks.test"), "inbox-x@tasks.test")

    def test_login_username_disabled(self):
        dsn = parse_dsn("imaps://inbox-x:pw@mail.example.com?domain_in_username=0")
        self.assertEqual(dsn.login_username("tasks.test"), "inbox-x")

    def test_login_username_override_with_at(self):
        dsn = parse_dsn(
            "imaps://inbox-x:pw@mail.example.com?domain_in_username=@gmail.com"
        )
        self.assertEqual(dsn.login_username("tasks.test"), "inbox-x@gmail.com")

    def test_login_username_override_without_at(self):
        dsn = parse_dsn(
            "imaps://inbox-x:pw@mail.example.com?domain_in_username=gmail.com"
        )
        self.assertEqual(dsn.login_username("tasks.test"), "inbox-x@gmail.com")

    def test_login_username_none_when_no_user(self):
        dsn = parse_dsn("imaps://mail.example.com")
        self.assertIsNone(dsn.login_username("tasks.test"))

    def test_dry_run_defaults_off_and_parses_truthy(self):
        self.assertFalse(parse_dsn("imaps://u:p@mail.example.com").dry_run)
        self.assertTrue(parse_dsn("imaps://u:p@mail.example.com?dry_run=1").dry_run)
        self.assertTrue(parse_dsn("imaps://u:p@mail.example.com?dry_run=true").dry_run)
        self.assertFalse(parse_dsn("imaps://u:p@mail.example.com?dry_run=0").dry_run)

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
