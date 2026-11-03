import unittest
from contextlib import redirect_stderr, redirect_stdout
from io import StringIO

from depkont import __version__
from depkont.cli import main
from depkont.sap_logon import SapLogonError


class DepkontTests(unittest.TestCase):
    def test_version(self) -> None:
        self.assertEqual(__version__, "0.1.0")

    def test_check_does_not_open_the_panel(self) -> None:
        self.assertEqual(main(["--check"]), 0)

    def test_main_reports_runner_message(self) -> None:
        with redirect_stdout(StringIO()) as stdout:
            code = main([], runner=lambda: "SAP ana ekrana getirildi.")
        self.assertEqual(code, 0)
        self.assertIn("SAP ana ekrana getirildi.", stdout.getvalue())

    def test_main_returns_error_when_saplogon_is_missing(self) -> None:
        def runner() -> str:
            raise SapLogonError("SAP Logon bulunamadı.")

        with redirect_stderr(StringIO()) as stderr:
            code = main([], runner=runner)
        self.assertEqual(code, 1)
        self.assertIn("SAP Logon bulunamadı.", stderr.getvalue())


if __name__ == "__main__":
    unittest.main()
