import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from depkont.sap_logon import (
    SAPLOGON_PATH,
    SapLogonError,
    ensure_sap_open,
    find_saplogon_executable,
    is_sap_window,
)


class SapWindowTests(unittest.TestCase):
    def test_known_sap_titles_and_class(self) -> None:
        self.assertTrue(is_sap_window("SAP Logon 770", "ThunderRT6FormDC"))
        self.assertTrue(is_sap_window("SAP Easy Access", ""))
        self.assertTrue(is_sap_window("Oturum", "SAP_FRONTEND_SESSION"))

    def test_unrelated_window_is_not_sap(self) -> None:
        self.assertFalse(is_sap_window("Depkont", "ConsoleWindowClass"))


class FindSapLogonTests(unittest.TestCase):
    def test_returns_first_existing_candidate(self) -> None:
        with TemporaryDirectory() as directory:
            executable = Path(directory) / "saplogon.exe"
            executable.write_bytes(b"")
            found = find_saplogon_executable([executable], search_registry=False)
        self.assertEqual(found, executable)

    def test_missing_candidate_returns_none(self) -> None:
        missing = Path("C:/yok/saplogon.exe")
        self.assertIsNone(find_saplogon_executable([missing], search_registry=False))


class EnsureSapOpenTests(unittest.TestCase):
    def test_does_not_launch_when_sap_is_already_open(self) -> None:
        launched: list[Path] = []

        status = ensure_sap_open(
            finder=lambda: SAPLOGON_PATH,
            is_open=lambda: True,
            starter=launched.append,
        )

        self.assertTrue(status.already_open)
        self.assertEqual(status.message, "SAP zaten açık.")
        self.assertEqual(launched, [])

    def test_launches_saplogon_when_sap_is_closed(self) -> None:
        executable = SAPLOGON_PATH
        launched: list[Path] = []
        checks = iter([False, False, True])

        status = ensure_sap_open(
            finder=lambda: executable,
            is_open=lambda: next(checks),
            starter=launched.append,
            clock=lambda: 0.0,
            pause=lambda _seconds: None,
            timeout_seconds=15,
        )

        self.assertFalse(status.already_open)
        self.assertEqual(launched, [executable])
        self.assertIn(str(executable), status.message)

    def test_raises_when_saplogon_cannot_be_found(self) -> None:
        with self.assertRaises(SapLogonError):
            ensure_sap_open(
                finder=lambda: None,
                is_open=lambda: False,
                starter=lambda _path: None,
            )

    def test_raises_when_window_does_not_appear(self) -> None:
        times = iter([0.0, 0.0, 20.0])
        with self.assertRaises(SapLogonError):
            ensure_sap_open(
                finder=lambda: SAPLOGON_PATH,
                is_open=lambda: False,
                starter=lambda _path: None,
                clock=lambda: next(times),
                pause=lambda _seconds: None,
                timeout_seconds=15,
            )


if __name__ == "__main__":
    unittest.main()
