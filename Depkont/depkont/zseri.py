from __future__ import annotations

import time
from collections.abc import Callable

from depkont.sap_login import (
    CONTINUE_WITHOUT_ENDING,
    OKCD_FIELD,
    _continue_without_ending_other_sessions,
    _has_id,
    _status_error,
    find_logged_in_session,
)
from depkont.sap_logon import SapLogonError
from depkont.serials import SerialQuery

SERIAL_FIELD = "wnd[0]/usr/txtSZSERNR-LOW"
GRID_ID = "wnd[0]/usr/cntlGRID1/shellcont/shell"
WAREHOUSE_COLUMN = "LGORT"
WAREHOUSE_NAME_COLUMN = "LGOBE"
TRANSACTION = "/nZSERI1"
RESULT_TIMEOUT_SECONDS = 20.0


def query_support_serial(
    session: object,
    support_serial: str,
    *,
    clock: Callable[[], float] | None = None,
    pause: Callable[[float], None] | None = None,
) -> SerialQuery:
    now = clock or time.monotonic
    wait = pause or time.sleep
    _clear_blocking_popup(session)
    field = _ensure_selection(session, now, wait)
    field.Text = support_serial
    _window(session).sendVKey(8)
    grid = _wait_for_result_grid(session, now, wait)
    return _warehouse_from_grid(grid)


class ZseriClient:
    def query(self, support_serial: str) -> SerialQuery:
        session = find_logged_in_session()
        if session is None:
            raise SapLogonError("Açık SAP oturumu bulunamadı.")
        return query_support_serial(session, support_serial)


def _ensure_selection(
    session: object,
    clock: Callable[[], float],
    pause: Callable[[float], None],
) -> object:
    field = _try_find(session, SERIAL_FIELD)
    if field is not None:
        return field
    if _try_find(session, GRID_ID) is not None:
        _window(session).sendVKey(3)
    else:
        okcd = session.findById(OKCD_FIELD)  # type: ignore[attr-defined]
        okcd.Text = TRANSACTION
        _window(session).sendVKey(0)
    return _wait_for(session, lambda: _try_find(session, SERIAL_FIELD), clock, pause)


def _wait_for(
    session: object,
    probe: Callable[[], object | None],
    clock: Callable[[], float],
    pause: Callable[[float], None],
) -> object:
    deadline = clock() + RESULT_TIMEOUT_SECONDS
    while clock() < deadline:
        _clear_blocking_popup(session)
        error = _status_error(session)
        if error:
            raise SapLogonError(error)
        found = probe()
        if found is not None:
            return found
        pause(0.25)
    raise SapLogonError("ZSERI1 ekranı açılmadı.")


def _wait_for_result_grid(
    session: object,
    clock: Callable[[], float],
    pause: Callable[[float], None],
) -> object:
    """Wait until the result grid stops changing.

    A filled ZSERI1 list can appear before every row is loaded. Reading too
    early either looks empty or misses the last warehouse row.
    """
    deadline = clock() + RESULT_TIMEOUT_SECONDS
    previous: int | None = None
    repeats = 0
    grid: object | None = None
    while clock() < deadline:
        _clear_blocking_popup(session)
        error = _status_error(session)
        if error:
            raise SapLogonError(error)
        found = _try_find(session, GRID_ID)
        if found is None:
            previous = None
            repeats = 0
            pause(0.25)
            continue
        count = int(getattr(found, "RowCount", 0) or 0)
        repeats = repeats + 1 if count == previous else 1
        previous = count
        grid = found
        if (count > 0 and repeats >= 2) or (count == 0 and repeats >= 3):
            return grid
        pause(0.25)
    if grid is not None and previous == 0:
        return grid
    raise SapLogonError("ZSERI1 sonuç tablosu açılmadı.")


def _warehouse_from_grid(grid: object) -> SerialQuery:
    count = int(getattr(grid, "RowCount", 0) or 0)
    if count <= 0:
        return SerialQuery(False)
    last = count - 1
    try:
        grid.SetCurrentCell(last, WAREHOUSE_COLUMN)  # type: ignore[attr-defined]
    except Exception:
        pass
    try:
        location = grid.GetCellValue(last, WAREHOUSE_COLUMN)  # type: ignore[attr-defined]
        name = grid.GetCellValue(last, WAREHOUSE_NAME_COLUMN)  # type: ignore[attr-defined]
    except Exception as exc:
        raise SapLogonError("Depo yeri okunamadı.") from exc
    return SerialQuery(True, str(location or "").strip(), str(name or "").strip())


def _clear_blocking_popup(session: object) -> None:
    if _has_id(session, CONTINUE_WITHOUT_ENDING):
        _continue_without_ending_other_sessions(session)
        return
    if not _has_id(session, "wnd[1]"):
        return
    popup = session.findById("wnd[1]")  # type: ignore[attr-defined]
    text = str(getattr(popup, "Text", "") or "").strip()
    raise SapLogonError(text or "SAP bir ileti penceresi gösteriyor.")


def _window(session: object) -> object:
    return session.findById("wnd[0]")  # type: ignore[attr-defined]


def _try_find(session: object, path: str) -> object | None:
    try:
        return session.findById(path)  # type: ignore[attr-defined]
    except Exception:
        return None
