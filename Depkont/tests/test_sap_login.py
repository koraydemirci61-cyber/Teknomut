import unittest

from depkont.sap_login import (
    _continue_without_ending_other_sessions,
    find_connection_index,
    is_main_screen_title,
    open_sap_session,
    show_sap_main_screen,
    sign_in_sap_destek,
)
from depkont.sap_logon import SapLogonError


class _Field:
    def __init__(self, text: str = "") -> None:
        self.Text = text


class _Window:
    def __init__(self, title: str, handle: int = 42) -> None:
        self.Text = title
        self.Handle = handle
        self.keys: list[int] = []

    def sendVKey(self, key: int) -> None:
        self.keys.append(key)
        self.Text = "DBP - SAP Easy Access"


class _Session:
    def __init__(self, title: str) -> None:
        self.window = _Window(title)
        self.okcd = _Field()

    def findById(self, path: str) -> object:
        if path == "wnd[0]":
            return self.window
        if path == "wnd[0]/tbar[0]/okcd":
            return self.okcd
        raise RuntimeError(path)


class MainScreenTests(unittest.TestCase):
    def test_known_main_screen_titles(self) -> None:
        self.assertTrue(is_main_screen_title("DBP(1)/111 SAP Easy Access"))
        self.assertTrue(is_main_screen_title("SAP Kolay Erişim"))
        self.assertFalse(is_main_screen_title("SAP Logon 740"))

    def test_already_on_main_screen_is_only_focused(self) -> None:
        session = _Session("SAP Easy Access")
        focused: list[int] = []
        message = show_sap_main_screen(
            session_source=lambda: session,
            activate=focused.append,
        )
        self.assertEqual(message, "SAP ana ekrana getirildi.")
        self.assertEqual(session.window.keys, [])
        self.assertEqual(focused, [42])

    def test_transaction_screen_returns_home(self) -> None:
        session = _Session("Seri Takip Raporu")
        focused: list[int] = []
        show_sap_main_screen(
            session_source=lambda: session,
            activate=focused.append,
            clock=lambda: 0.0,
            pause=lambda _seconds: None,
        )
        self.assertEqual(session.okcd.Text, "/n")
        self.assertEqual(session.window.keys, [0])
        self.assertEqual(focused, [42])

    def test_missing_session_raises(self) -> None:
        with self.assertRaises(SapLogonError):
            show_sap_main_screen(
                session_source=lambda: None,
                hwnd_finder=lambda: 0,
                activate=lambda _hwnd: None,
            )


class OpenSapSessionTests(unittest.TestCase):
    def test_open_session_goes_to_main_screen(self) -> None:
        calls: list[str] = []

        message = open_sap_session(
            session_open=lambda: True,
            show_main=lambda: calls.append("home") or "SAP ana ekrana getirildi.",
            ensure_logon=lambda: calls.append("launch"),
            sign_in=lambda: calls.append("login") or "giriş",
        )

        self.assertEqual(calls, ["home"])
        self.assertEqual(message, "SAP ana ekrana getirildi.")

    def test_closed_sap_logs_in_then_shows_main_screen(self) -> None:
        calls: list[str] = []

        message = open_sap_session(
            session_open=lambda: False,
            show_main=lambda: calls.append("home") or "SAP ana ekrana getirildi.",
            ensure_logon=lambda: calls.append("launch"),
            sign_in=lambda: calls.append("login") or "SAP DESTEK oturumu açıldı.",
        )

        self.assertEqual(calls, ["launch", "login", "home"])
        self.assertEqual(message, "SAP DESTEK oturumu açıldı.")


class _Radio:
    def __init__(self) -> None:
        self.selected = False

    def select(self) -> None:
        self.selected = True


class _Popup:
    def __init__(self) -> None:
        self.keys: list[int] = []

    def sendVKey(self, key: int) -> None:
        self.keys.append(key)


class _MultiLogonSession:
    def __init__(self) -> None:
        self.option = _Radio()
        self.popup = _Popup()

    def findById(self, path: str) -> object:
        if path.endswith("radMULTI_LOGON_OPT2"):
            return self.option
        if path == "wnd[1]":
            return self.popup
        raise RuntimeError(path)


class _PopupUi:
    def __init__(self) -> None:
        self.calls: list[str] = []

    def credential_screen_is_open(self) -> bool:
        return True

    def multiple_logon_is_open(self) -> bool:
        return True

    def continue_without_ending_other_sessions(self) -> None:
        self.calls.append("continue")

    def wait_until_logged_in(self) -> None:
        self.calls.append("wait")

    def submit(self, username: str, password: str, language: str) -> None:
        del username, password, language
        raise AssertionError("submit")


class MultipleLogonTests(unittest.TestCase):
    def test_continues_without_ending_other_sessions(self) -> None:
        session = _MultiLogonSession()
        _continue_without_ending_other_sessions(session)
        self.assertTrue(session.option.selected)
        self.assertEqual(session.popup.keys, [0])

    def test_sign_in_does_not_submit_again_when_popup_is_open(self) -> None:
        screen = _PopupUi()
        message = sign_in_sap_destek(screen)  # type: ignore[arg-type]
        self.assertEqual(screen.calls, ["continue", "wait"])
        self.assertEqual(message, "SAP DESTEK oturumu açıldı.")


class ConnectionListTests(unittest.TestCase):
    def test_finds_exact_connection_name(self) -> None:
        rows = [["SAP KOYUNCU"], ["SAP DESTEK", "192.168.0.239"]]
        self.assertEqual(find_connection_index(rows), 1)

    def test_missing_connection_raises(self) -> None:
        with self.assertRaises(SapLogonError):
            find_connection_index([["SAP KOYUNCU"]])


if __name__ == "__main__":
    unittest.main()
