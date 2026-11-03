from __future__ import annotations

import time
from collections.abc import Callable

import win32gui

from depkont.sap_logon import SapLogonError, ensure_sap_open
from depkont.sap_ui import (
    RemoteList,
    button_label,
    child_windows,
    click_button,
    find_button,
    find_top_window,
    select_tab,
    tab_labels,
)

SAP_CONNECTION_NAME = "SAP DESTEK"
SAP_USERNAME = "korayd"
SAP_PASSWORD = "282828"
SAP_LANGUAGE = "TR"
LOGON_BUTTON_LABEL = "Oturum aç"
LOGON_TAB_NAMES = frozenset(
    {"oturum aç", "oturum ac", "connections", "bağlantılar", "baglantilar"}
)
LOGON_SCREEN_TIMEOUT_SECONDS = 20.0
LOGIN_TIMEOUT_SECONDS = 30.0
CLIENT_FIELD = "wnd[0]/usr/txtRSYST-MANDT"
USER_FIELD = "wnd[0]/usr/txtRSYST-BNAME"
PASSWORD_FIELD = "wnd[0]/usr/pwdRSYST-BCODE"
LANGUAGE_FIELDS = (
    "wnd[0]/usr/txtRSYST-LANGU",
    "wnd[0]/usr/cmbRSYST-LANGU",
)
OKCD_FIELD = "wnd[0]/tbar[0]/okcd"
CONTINUE_WITHOUT_ENDING = "wnd[1]/usr/radMULTI_LOGON_OPT2"
MAIN_SCREEN_COMMAND = "/n"
MAIN_SCREEN_TIMEOUT_SECONDS = 15.0
_MAIN_SCREEN_MARKERS = ("easy access", "kolay erişim", "kolay erisim")


def is_main_screen_title(title: str) -> bool:
    folded = title.casefold()
    return any(marker in folded for marker in _MAIN_SCREEN_MARKERS)


def open_sap_session(
    *,
    session_open: Callable[[], bool] | None = None,
    show_main: Callable[[], str] | None = None,
    ensure_logon: Callable[[], object] | None = None,
    sign_in: Callable[[], str] | None = None,
) -> str:
    logged_in = session_open or (lambda: _find_logged_in_session() is not None)
    home = show_main or show_sap_main_screen
    launch = ensure_logon or ensure_sap_open
    login = sign_in or sign_in_sap_destek
    if logged_in():
        return home()
    launch()
    entered = login()
    home()
    return entered


def show_sap_main_screen(
    *,
    session_source: Callable[[], object | None] | None = None,
    activate: Callable[[int], None] | None = None,
    hwnd_finder: Callable[[], int] | None = None,
    clock: Callable[[], float] | None = None,
    pause: Callable[[float], None] | None = None,
) -> str:
    now = clock or time.monotonic
    wait = pause or time.sleep
    focus = activate or _activate_hwnd
    if session_source is None:
        session = _await_logged_in_session(now, wait, MAIN_SCREEN_TIMEOUT_SECONDS)
    else:
        session = session_source()
    if session is None:
        hwnd = (hwnd_finder or _find_visible_main_hwnd)()
        if not hwnd:
            raise SapLogonError("Açık SAP oturumu bulunamadı.")
        focus(hwnd)
        return "SAP ana ekrana getirildi."

    _dismiss_popups(session)
    window = session.findById("wnd[0]")  # type: ignore[attr-defined]
    title = str(getattr(window, "Text", "") or "")
    if not is_main_screen_title(title):
        _set_field(
            session,
            OKCD_FIELD,
            MAIN_SCREEN_COMMAND,
            failure="SAP komut alanı kullanılamadı.",
        )
        try:
            window.sendVKey(0)
        except Exception as exc:
            raise SapLogonError("SAP ana ekranına geçilemedi.") from exc
        _wait_until_main_screen(session, now, wait)
        window = session.findById("wnd[0]")  # type: ignore[attr-defined]
    handle = int(getattr(window, "Handle", 0) or 0)
    if handle:
        focus(handle)
    return "SAP ana ekrana getirildi."


def find_connection_index(rows: list[list[str]], name: str = SAP_CONNECTION_NAME) -> int:
    wanted = name.casefold()
    for index, row in enumerate(rows):
        if row and row[0].strip().casefold() == wanted:
            return index
    raise SapLogonError(f"Oturum aç listesinde {name} bulunamadı.")


def sign_in_sap_destek(ui: SapLoginUi | None = None) -> str:
    screen = ui or Win32SapLoginUi()
    if not screen.credential_screen_is_open():
        screen.activate_logon_page()
        index = find_connection_index(screen.connection_rows())
        screen.select_connection(index)
        screen.press_logon()
    if screen.multiple_logon_is_open():
        screen.continue_without_ending_other_sessions()
    else:
        client = screen.read_client().strip()
        if not client:
            raise SapLogonError(
                "SAP DESTEK giriş ekranında istemci boş. Giriş denenmedi."
            )
        screen.submit(SAP_USERNAME, SAP_PASSWORD, SAP_LANGUAGE)
    screen.wait_until_logged_in()
    return "SAP DESTEK oturumu açıldı."


class SapLoginUi:
    def credential_screen_is_open(self) -> bool:
        raise NotImplementedError

    def activate_logon_page(self) -> None:
        raise NotImplementedError

    def connection_rows(self) -> list[list[str]]:
        raise NotImplementedError

    def select_connection(self, index: int) -> None:
        raise NotImplementedError

    def press_logon(self) -> None:
        raise NotImplementedError

    def read_client(self) -> str:
        raise NotImplementedError

    def submit(self, username: str, password: str, language: str) -> None:
        raise NotImplementedError

    def multiple_logon_is_open(self) -> bool:
        raise NotImplementedError

    def continue_without_ending_other_sessions(self) -> None:
        raise NotImplementedError

    def wait_until_logged_in(self) -> None:
        raise NotImplementedError


class Win32SapLoginUi(SapLoginUi):
    def __init__(
        self,
        clock: Callable[[], float] | None = None,
        pause: Callable[[float], None] | None = None,
    ) -> None:
        self._clock = clock or time.monotonic
        self._pause = pause or time.sleep
        self._list_hwnd = 0

    def credential_screen_is_open(self) -> bool:
        return _find_credential_session() is not None

    def activate_logon_page(self) -> None:
        hwnd = self._wait_logon_hwnd()
        _activate_hwnd(hwnd)
        tabs = child_windows(hwnd, "SysTabControl32")
        lists = [item for item in child_windows(hwnd, "SysListView32") if win32gui.IsWindowVisible(item)]
        if not lists:
            raise SapLogonError("SAP Logon bağlantı listesi bulunamadı.")
        self._list_hwnd = lists[0]
        if not tabs:
            return
        with RemoteList(self._list_hwnd) as remote:
            labels = tab_labels(tabs[0], remote)
        for index, label in enumerate(labels):
            if label.casefold() in LOGON_TAB_NAMES:
                select_tab(tabs[0], index)
                return

    def connection_rows(self) -> list[list[str]]:
        if not self._list_hwnd:
            self.activate_logon_page()
        deadline = self._clock() + LOGON_SCREEN_TIMEOUT_SECONDS
        rows: list[list[str]] = []
        while self._clock() < deadline:
            with RemoteList(self._list_hwnd) as remote:
                rows = remote.rows()
            if any(row and row[0].strip() for row in rows):
                return rows
            self._pause(0.25)
        return rows

    def select_connection(self, index: int) -> None:
        with RemoteList(self._list_hwnd) as remote:
            remote.select(index)
        self._pause(0.2)

    def press_logon(self) -> None:
        hwnd = self._wait_logon_hwnd()
        button = find_button(hwnd, LOGON_BUTTON_LABEL)
        if not button:
            raise SapLogonError("SAP Logon penceresinde Oturum aç düğmesi bulunamadı.")
        click_button(button)

    def read_client(self) -> str:
        session = _wait_for_session(self._clock, self._pause, LOGON_SCREEN_TIMEOUT_SECONDS)
        return _field_text(session, CLIENT_FIELD)

    def submit(self, username: str, password: str, language: str) -> None:
        session = _wait_for_session(self._clock, self._pause, LOGON_SCREEN_TIMEOUT_SECONDS)
        _set_field(session, USER_FIELD, username)
        _set_field(session, PASSWORD_FIELD, password)
        for path in LANGUAGE_FIELDS:
            if _try_set_field(session, path, language):
                break
        try:
            session.findById("wnd[0]").sendVKey(0)
        except Exception as exc:
            raise SapLogonError("SAP giriş ekranı onaylanamadı.") from exc

    def multiple_logon_is_open(self) -> bool:
        session = _find_credential_session()
        return session is not None and _has_id(session, CONTINUE_WITHOUT_ENDING)

    def continue_without_ending_other_sessions(self) -> None:
        session = _find_credential_session()
        if session is None:
            raise SapLogonError("SAP giriş ekranı bulunamadı.")
        _continue_without_ending_other_sessions(session)

    def wait_until_logged_in(self) -> None:
        deadline = self._clock() + LOGIN_TIMEOUT_SECONDS
        while self._clock() < deadline:
            session = _find_credential_session()
            if session is None:
                if _any_gui_session():
                    return
            elif _has_id(session, CONTINUE_WITHOUT_ENDING):
                _continue_without_ending_other_sessions(session)
            else:
                message = _error_message(session)
                if message:
                    raise SapLogonError(message)
            self._pause(0.25)
        raise SapLogonError("SAP DESTEK oturumu açılmadı.")

    def _wait_logon_hwnd(self) -> int:
        deadline = self._clock() + LOGON_SCREEN_TIMEOUT_SECONDS
        while self._clock() < deadline:
            hwnd = find_top_window("SAP Logon")
            if hwnd:
                return hwnd
            self._pause(0.25)
        raise SapLogonError("SAP Logon penceresi bulunamadı.")


def _scripting_application() -> object | None:
    try:
        import win32com.client
    except ImportError:
        return None
    try:
        return win32com.client.GetObject("SAPGUI").GetScriptingEngine
    except Exception:
        return None


def _iter_sessions(application: object) -> list[object]:
    sessions: list[object] = []
    try:
        connection_count = int(application.Children.Count)  # type: ignore[attr-defined]
    except Exception:
        return sessions
    for connection_index in range(connection_count):
        connection = application.Children(connection_index)  # type: ignore[attr-defined]
        try:
            session_count = int(connection.Children.Count)
        except Exception:
            continue
        for session_index in range(session_count):
            sessions.append(connection.Children(session_index))
    return sessions


def _find_credential_session() -> object | None:
    application = _scripting_application()
    if application is None:
        return None
    for session in _iter_sessions(application):
        try:
            session.findById(USER_FIELD)  # type: ignore[attr-defined]
        except Exception:
            continue
        return session
    return None


def _any_gui_session() -> bool:
    application = _scripting_application()
    if application is None:
        return False
    return bool(_iter_sessions(application))


def _wait_for_session(
    clock: Callable[[], float],
    pause: Callable[[float], None],
    timeout_seconds: float,
) -> object:
    deadline = clock() + timeout_seconds
    while clock() < deadline:
        session = _find_credential_session()
        if session is not None:
            return session
        pause(0.25)
    raise SapLogonError("SAP giriş ekranı açılmadı.")


def _field_text(session: object, path: str) -> str:
    try:
        field = session.findById(path)  # type: ignore[attr-defined]
        return str(getattr(field, "Text", "") or "")
    except Exception as exc:
        raise SapLogonError("SAP giriş ekranındaki istemci okunamadı.") from exc


def _set_field(
    session: object,
    path: str,
    value: str,
    failure: str = "SAP giriş alanları kullanılamadı.",
) -> None:
    if not _try_set_field(session, path, value):
        raise SapLogonError(failure)


def _try_set_field(session: object, path: str, value: str) -> bool:
    try:
        field = session.findById(path)  # type: ignore[attr-defined]
        field.Text = value
    except Exception:
        return False
    return True


def _status_error(session: object) -> str:
    try:
        status = session.findById("wnd[0]/sbar")  # type: ignore[attr-defined]
        if str(getattr(status, "MessageType", "") or "").upper() == "E":
            text = str(getattr(status, "Text", "") or "").strip()
            if text:
                return text
    except Exception:
        return ""
    return ""


def _error_message(session: object) -> str:
    error = _status_error(session)
    if error:
        return error
    try:
        popup = session.findById("wnd[1]")  # type: ignore[attr-defined]
    except Exception:
        return ""
    text = str(getattr(popup, "Text", "") or "").strip()
    return text or "SAP giriş penceresi hata verdi."


def _continue_without_ending_other_sessions(session: object) -> None:
    """Keep sessions already open on other screens; do not end them."""
    if not _has_id(session, CONTINUE_WITHOUT_ENDING):
        return
    option = session.findById(CONTINUE_WITHOUT_ENDING)  # type: ignore[attr-defined]
    select = getattr(option, "select", None)
    if callable(select):
        select()
    else:
        option.Selected = True
    try:
        session.findById("wnd[1]").sendVKey(0)  # type: ignore[attr-defined]
    except Exception as exc:
        raise SapLogonError("Birden çok oturum penceresi onaylanamadı.") from exc


def _has_id(session: object, path: str) -> bool:
    try:
        session.findById(path)  # type: ignore[attr-defined]
    except Exception:
        return False
    return True


def _find_logged_in_session() -> object | None:
    application = _scripting_application()
    if application is None:
        return None
    for session in _iter_sessions(application):
        if _has_id(session, OKCD_FIELD) and not _has_id(session, USER_FIELD):
            return session
    return None


def find_logged_in_session() -> object | None:
    return _find_logged_in_session()


def _await_logged_in_session(
    clock: Callable[[], float],
    pause: Callable[[float], None],
    timeout_seconds: float,
) -> object | None:
    deadline = clock() + timeout_seconds
    while True:
        session = _find_logged_in_session()
        if session is not None:
            return session
        if clock() >= deadline:
            return None
        pause(0.25)


def _dismiss_popups(session: object, limit: int = 3) -> None:
    for _ in range(limit):
        try:
            popup = session.findById("wnd[1]")  # type: ignore[attr-defined]
        except Exception:
            return
        try:
            popup.sendVKey(12)
        except Exception:
            return


def _okcd_text(session: object) -> str:
    try:
        field = session.findById(OKCD_FIELD)  # type: ignore[attr-defined]
    except Exception:
        return ""
    return str(getattr(field, "Text", "") or "").strip()


def _wait_until_main_screen(
    session: object,
    clock: Callable[[], float],
    pause: Callable[[float], None],
) -> None:
    deadline = clock() + MAIN_SCREEN_TIMEOUT_SECONDS
    while clock() < deadline:
        error = _status_error(session)
        if error:
            raise SapLogonError(error)
        _dismiss_popups(session)
        try:
            window = session.findById("wnd[0]")  # type: ignore[attr-defined]
            title = str(getattr(window, "Text", "") or "")
        except Exception:
            title = ""
        if is_main_screen_title(title) or (
            _okcd_text(session) == "" and not _has_id(session, "wnd[1]")
        ):
            return
        pause(0.25)
    raise SapLogonError("SAP ana ekranı açılmadı.")


def _find_visible_main_hwnd() -> int:
    found = 0

    def visit(hwnd: int, _extra: object) -> bool:
        nonlocal found
        if found or not win32gui.IsWindowVisible(hwnd):
            return True
        if is_main_screen_title(win32gui.GetWindowText(hwnd)):
            found = hwnd
        return True

    win32gui.EnumWindows(visit, None)
    return found


def _activate_hwnd(hwnd: int) -> None:
    if not hwnd:
        return
    import win32api
    import win32con
    import win32process

    try:
        win32gui.ShowWindow(hwnd, win32con.SW_RESTORE)
        foreground = win32gui.GetForegroundWindow()
        current = win32api.GetCurrentThreadId()
        remote_thread = win32process.GetWindowThreadProcessId(foreground)[0]
        target_thread = win32process.GetWindowThreadProcessId(hwnd)[0]
        attached_remote = False
        attached_target = False
        if remote_thread and remote_thread != current:
            attached_remote = bool(win32process.AttachThreadInput(current, remote_thread, True))
        if target_thread and target_thread != current:
            attached_target = bool(win32process.AttachThreadInput(current, target_thread, True))
        try:
            win32gui.SetForegroundWindow(hwnd)
            win32gui.BringWindowToTop(hwnd)
        finally:
            if attached_target:
                win32process.AttachThreadInput(current, target_thread, False)
            if attached_remote:
                win32process.AttachThreadInput(current, remote_thread, False)
    except Exception:
        return


def logon_button_is_exact(text: str) -> bool:
    return button_label(text) == button_label(LOGON_BUTTON_LABEL)
