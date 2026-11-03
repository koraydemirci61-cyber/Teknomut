from __future__ import annotations

import queue
import re
import sys
import threading
import time
import os
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from tkinter import BOTH, END, LEFT, RIGHT, X, Y, StringVar, Text, Tk, filedialog, messagebox
from tkinter import ttk
from typing import Any

from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill


APP_TITLE = "SAP Satınalma Kontrolü"
SAP_TITLE = "Seri Takip Raporu"
SAP_EASY_ACCESS_TITLE = "SAP Easy Access"
SAP_LOGON_TITLE = "SAP Logon"
SAP_TRANSACTION = "/nZSERI1"
SAP_LOGON_SHORTCUT = Path(
    r"C:\ProgramData\Microsoft\Windows\Start Menu\Programs\SAP Front End\SAP Logon.lnk"
)
SAP_SESSION_WAIT_SECONDS = 120
SAP_LAUNCH_WAIT_SECONDS = 10
SAP_RESULT_WAIT_SECONDS = 15
STATUS_FOUND = "Transfer edilebilir"
STATUS_NOT_FOUND = "SAS yok"
STATUS_ERROR = "Kontrol hatası"
STATUS_PENDING = "Bekliyor"
STATUS_NOT_CHECKED = "Kontrol edilmedi"
SINGLE_IMEI_LENGTH = 15
IMEI_PATTERN = re.compile(rf"^[0-9]{{{SINGLE_IMEI_LENGTH}}}$")


class ImeiInputError(ValueError):
    pass


class SapGuiError(RuntimeError):
    pass


class OperationCancelled(RuntimeError):
    pass


@dataclass(frozen=True)
class CheckResult:
    status: str
    details: str


@dataclass
class ResultRecord:
    sequence: int
    imei: str
    status: str
    checked_at: str = ""
    details: str = ""

    @property
    def support_serial(self) -> str:
        return f"{self.imei}v"


def normalize_imei(value: str) -> str:
    imei = value.strip()
    if not IMEI_PATTERN.fullmatch(imei):
        raise ImeiInputError(
            f"IMEI tam olarak {SINGLE_IMEI_LENGTH} rakam olmalı; "
            f"girilen değer {len(imei)} karakter."
        )
    return imei


def parse_imei_list(text: str) -> list[str]:
    tokens = [token for token in re.split(r"[\s,;]+", text.strip()) if token]
    if not tokens:
        raise ImeiInputError("Kontrol edilecek IMEI girilmedi.")

    imeis: list[str] = []
    errors: list[str] = []
    for token in tokens:
        try:
            imeis.append(normalize_imei(token))
        except ImeiInputError:
            errors.append(token)

    if errors:
        preview = ", ".join(repr(value) for value in errors[:5])
        more = f" ve {len(errors) - 5} değer daha" if len(errors) > 5 else ""
        raise ImeiInputError(
            f"Geçersiz IMEI bulundu: {preview}{more}. Her IMEI tam olarak "
            f"{SINGLE_IMEI_LENGTH} rakam olmalı."
        )
    return imeis


def classify_grid_result(header_pixels: int, body_pixels: int) -> CheckResult:
    if header_pixels == 0 and body_pixels == 0:
        return CheckResult(STATUS_NOT_FOUND, "SAP ekranı boş; satınalma kaydı bulunamadı.")
    if header_pixels < 20:
        raise SapGuiError("ZSERI1 sonuç tablosu görünmüyor; SAP ekranı doğrulanamadı.")
    if body_pixels > 10:
        return CheckResult(STATUS_FOUND, "SAP sonuç tablosunda kayıt bulundu.")
    return CheckResult(STATUS_NOT_FOUND, "SAP sonuç tablosunda kayıt bulunamadı.")


def is_sap_session_title(title: str) -> bool:
    normalized_title = title.casefold()
    return SAP_LOGON_TITLE.casefold() not in normalized_title and any(
        candidate.casefold() in normalized_title
        for candidate in (SAP_TITLE, SAP_EASY_ACCESS_TITLE)
    )


def is_sap_logon_title(title: str) -> bool:
    return SAP_LOGON_TITLE.casefold() in title.casefold()


def save_results_excel(path: Path, records: list[ResultRecord]) -> None:
    workbook = Workbook()
    worksheet = workbook.active
    worksheet.title = "Satınalma Kontrol"
    worksheet.append(
        [
            "Sıra",
            "IMEI",
            "Destek Seri Numarası",
            "Satınalma Durumu",
            "Kontrol Zamanı",
            "Açıklama",
        ]
    )
    header_fill = PatternFill("solid", fgColor="17365D")
    for cell in worksheet[1]:
        cell.font = Font(color="FFFFFF", bold=True)
        cell.fill = header_fill
        cell.alignment = Alignment(horizontal="center")

    for record in records:
        worksheet.append(
            [
                record.sequence,
                record.imei,
                record.support_serial,
                record.status,
                record.checked_at,
                record.details,
            ]
        )
        status_cell = worksheet.cell(worksheet.max_row, 4)
        if record.status == STATUS_FOUND:
            status_cell.fill = PatternFill("solid", fgColor="C6EFCE")
        elif record.status == STATUS_NOT_FOUND:
            status_cell.fill = PatternFill("solid", fgColor="FFC7CE")
        elif record.status == STATUS_ERROR:
            status_cell.fill = PatternFill("solid", fgColor="FFEB9C")

    worksheet.freeze_panes = "A2"
    worksheet.auto_filter.ref = worksheet.dimensions
    for column, width in {
        "A": 9,
        "B": 20,
        "C": 27,
        "D": 24,
        "E": 22,
        "F": 55,
    }.items():
        worksheet.column_dimensions[column].width = width
    workbook.save(path)


class SapGuiClient:
    """Controls the already logged-in SAP GUI and reads the ZSERI1 result grid."""

    def __init__(
        self,
        cancel_event: threading.Event | None = None,
        status_callback: Any = None,
    ) -> None:
        if not sys.platform.startswith("win"):
            raise SapGuiError("SAP GUI kontrolü yalnızca Windows'ta kullanılabilir.")
        try:
            import win32api
            import win32con
            import win32gui
            import win32process
        except ImportError as exc:
            raise SapGuiError("pywin32 kurulu değil; SAP GUI kontrolü başlatılamadı.") from exc

        self.win32api = win32api
        self.win32con = win32con
        self.win32gui = win32gui
        self.win32process = win32process
        self.cancel_event = cancel_event
        self.status_callback = status_callback
        self.hwnd = self._find_sap_window()
        self.at_selection_screen = False
        if not self.hwnd:
            logon_hwnd = self._find_sap_logon_window()
            if not logon_hwnd:
                self._notify_status("SAP kapalı; SAP Logon açılıyor...")
                self._launch_sap_logon()
                logon_hwnd = self._wait_for_sap_logon()
            if logon_hwnd:
                self._activate_window(logon_hwnd)
                self._notify_status(
                    "SAP Logon açık. SAP sistemine giriş yapın; girişten sonra "
                    "ZSERI1 otomatik açılacak."
                )
            self.hwnd = self._wait_for_sap_session()
        if not self.hwnd:
            raise SapGuiError(
                "120 saniye içinde SAP sistem oturumu bulunamadı. SAP Logon'dan "
                "sisteme giriş yapıp IMEI'yi yeniden okutun."
            )

        self._activate_window(self.hwnd)
        self._wait_or_cancel(0.5)
        self.screen_width = self.win32api.GetSystemMetrics(0)
        self.screen_height = self.win32api.GetSystemMetrics(1)
        if self.screen_width < 1000 or self.screen_height < 700:
            raise SapGuiError("SAP ekranı bu uygulama için çok küçük; ekran çözünürlüğünü artırın.")

    def _notify_status(self, message: str) -> None:
        if self.status_callback is not None:
            self.status_callback(message)

    def _activate_window(self, hwnd: int) -> None:
        self.win32gui.ShowWindow(hwnd, self.win32con.SW_RESTORE)
        self.win32gui.ShowWindow(hwnd, self.win32con.SW_MAXIMIZE)
        self.win32gui.SetForegroundWindow(hwnd)

    def _find_sap_window(self) -> int:
        matches: list[tuple[int, int]] = []

        def visit(hwnd: int, _extra: Any) -> bool:
            del _extra
            if not self.win32gui.IsWindowVisible(hwnd):
                return True
            title = self.win32gui.GetWindowText(hwnd)
            if not is_sap_session_title(title):
                return True
            left, top, right, bottom = self.win32gui.GetWindowRect(hwnd)
            area = max(0, right - left) * max(0, bottom - top)
            if area > 20_000:
                matches.append((area, hwnd))
            return True

        self.win32gui.EnumWindows(visit, None)
        return max(matches, default=(0, 0))[1]

    def _find_sap_logon_window(self) -> int:
        matches: list[tuple[int, int]] = []

        def visit(hwnd: int, _extra: Any) -> bool:
            del _extra
            if self.win32gui.IsWindowVisible(hwnd):
                title = self.win32gui.GetWindowText(hwnd)
                if is_sap_logon_title(title):
                    left, top, right, bottom = self.win32gui.GetWindowRect(hwnd)
                    area = max(0, right - left) * max(0, bottom - top)
                    matches.append((area, hwnd))
            return True

        self.win32gui.EnumWindows(visit, None)
        return max(matches, default=(0, 0))[1]

    def _launch_sap_logon(self) -> None:
        if not SAP_LOGON_SHORTCUT.is_file():
            raise SapGuiError(f"SAP Logon kısayolu bulunamadı: {SAP_LOGON_SHORTCUT}")
        try:
            os.startfile(str(SAP_LOGON_SHORTCUT))
        except OSError as exc:
            raise SapGuiError(f"SAP Logon başlatılamadı: {exc}") from exc
        deadline = time.monotonic() + SAP_LAUNCH_WAIT_SECONDS
        while time.monotonic() < deadline:
            self._raise_if_cancelled()
            if self._find_sap_logon_window():
                return
            self._wait_or_cancel(0.25)
        raise SapGuiError(
            "SAP Logon kısayoluyla başlatıldı ancak SAP penceresi açılmadı. "
            "SAP kurulumu/kısayolunu kontrol edip tekrar deneyin."
        )

    def _wait_for_sap_logon(self) -> int:
        deadline = time.monotonic() + SAP_LAUNCH_WAIT_SECONDS
        while time.monotonic() < deadline:
            self._raise_if_cancelled()
            hwnd = self._find_sap_logon_window()
            if hwnd:
                return hwnd
            self._wait_or_cancel(0.25)
        return 0

    def _wait_for_sap_session(self) -> int:
        deadline = time.monotonic() + SAP_SESSION_WAIT_SECONDS
        next_status_update = 0.0
        while time.monotonic() < deadline:
            self._raise_if_cancelled()
            hwnd = self._find_sap_window()
            if hwnd:
                self._notify_status("SAP oturumu bulundu; ZSERI1 açılıyor...")
                return hwnd
            remaining = max(0, round(deadline - time.monotonic()))
            if time.monotonic() >= next_status_update:
                self._notify_status(
                    f"SAP sistemine giriş bekleniyor ({remaining} sn kaldı)..."
                )
                next_status_update = time.monotonic() + 5
            self._wait_or_cancel(0.5)
        return 0

    def _raise_if_cancelled(self) -> None:
        if self.cancel_event is not None and self.cancel_event.is_set():
            raise OperationCancelled("İşlem kullanıcı tarafından kapatıldı.")

    def _wait_or_cancel(self, seconds: float) -> None:
        if self.cancel_event is not None and self.cancel_event.wait(seconds):
            raise OperationCancelled("İşlem kullanıcı tarafından kapatıldı.")
        if self.cancel_event is None:
            time.sleep(seconds)

    def _click(self, x_ratio: float, y_ratio: float) -> None:
        x = round(self.screen_width * x_ratio)
        y = round(self.screen_height * y_ratio)
        self.win32api.SetCursorPos((x, y))
        self.win32api.mouse_event(self.win32con.MOUSEEVENTF_LEFTDOWN, 0, 0, 0, 0)
        self.win32api.mouse_event(self.win32con.MOUSEEVENTF_LEFTUP, 0, 0, 0, 0)

    def _press(self, key: int) -> None:
        self.win32api.keybd_event(key, 0, 0, 0)
        self.win32api.keybd_event(key, 0, self.win32con.KEYEVENTF_KEYUP, 0)

    def _type_text(self, text: str) -> None:
        for character in text:
            codepoint = ord(character)
            self.win32api.keybd_event(
                0, codepoint, self.win32con.KEYEVENTF_UNICODE, 0
            )
            self.win32api.keybd_event(
                0,
                codepoint,
                self.win32con.KEYEVENTF_UNICODE | self.win32con.KEYEVENTF_KEYUP,
                0,
            )

    def _ctrl_a(self) -> None:
        self.win32api.keybd_event(self.win32con.VK_CONTROL, 0, 0, 0)
        self._press(ord("A"))
        self.win32api.keybd_event(
            self.win32con.VK_CONTROL, 0, self.win32con.KEYEVENTF_KEYUP, 0
        )

    def _run_transaction(self) -> None:
        self._raise_if_cancelled()
        self._activate_window(self.hwnd)
        self._notify_status("ZSERI1 ekranı açılıyor...")
        self._wait_or_cancel(0.2)
        self._click(0.065, 0.049)
        self._ctrl_a()
        self._type_text(SAP_TRANSACTION)
        self._press(self.win32con.VK_RETURN)
        self._wait_or_cancel(1.2)
        self._raise_if_cancelled()
        self.at_selection_screen = True

    def _read_grid_pixel_counts(self) -> tuple[int, int]:
        hdc = self.win32gui.GetDC(0)
        if not hdc:
            raise SapGuiError("SAP ekranı okunamadı.")
        try:
            header_count = 0
            body_count = 0
            x_start = round(self.screen_width * 0.009)
            x_end = round(self.screen_width * 0.89)
            header_start = round(self.screen_height * 0.141)
            header_end = round(self.screen_height * 0.163)
            body_start = header_end + 2
            body_end = round(self.screen_height * 0.89)
            for y in range(header_start, header_end, 2):
                for x in range(x_start, x_end, 2):
                    color = self.win32gui.GetPixel(hdc, x, y)
                    if color != -1 and (color & 0xFF) < 110 and ((color >> 8) & 0xFF) < 110 and ((color >> 16) & 0xFF) < 110:
                        header_count += 1
            body_x_start = round(self.screen_width * 0.045)
            body_x_end = round(self.screen_width * 0.34)
            for y in range(body_start, body_end, 2):
                for x in range(body_x_start, body_x_end, 2):
                    color = self.win32gui.GetPixel(hdc, x, y)
                    if color != -1 and (color & 0xFF) < 110 and ((color >> 8) & 0xFF) < 110 and ((color >> 16) & 0xFF) < 110:
                        body_count += 1
            return header_count, body_count
        finally:
            self.win32gui.ReleaseDC(0, hdc)

    def check_imei(self, imei: str) -> CheckResult:
        self._raise_if_cancelled()
        if not self.at_selection_screen:
            self._run_transaction()
        self._raise_if_cancelled()
        self._activate_window(self.hwnd)
        self._notify_status(f"{imei}v SAP'te sorgulanıyor...")
        self._click(0.167, 0.353)
        self._ctrl_a()
        self._type_text(f"{imei}V")
        self._press(self.win32con.VK_F8)
        self.at_selection_screen = False
        self._notify_status("SAP sorgu sonucu bekleniyor...")
        deadline = time.monotonic() + SAP_RESULT_WAIT_SECONDS
        empty_screen_samples = 0
        while time.monotonic() < deadline:
            self._raise_if_cancelled()
            header_count, body_count = self._read_grid_pixel_counts()
            if header_count >= 20:
                return classify_grid_result(header_count, body_count)
            if header_count == 0 and body_count == 0:
                empty_screen_samples += 1
                if empty_screen_samples >= 3:
                    return classify_grid_result(header_count, body_count)
            else:
                empty_screen_samples = 0
            self._wait_or_cancel(0.25)
        raise SapGuiError(
            "ZSERI1 sonuç tablosu 15 saniye içinde görünmedi. "
            "SAP oturumunu ve sonuç ekranını kontrol edip tekrar deneyin."
        )

    def return_to_selection_screen(self) -> None:
        if self.at_selection_screen:
            return
        self._wait_or_cancel(2)
        self._raise_if_cancelled()
        self._activate_window(self.hwnd)
        self._click(0.139, 0.049)
        self.at_selection_screen = True


class PurchaseCheckApp:
    def __init__(self, root: Tk) -> None:
        self.root = root
        self.root.title(APP_TITLE)
        self.root.geometry("1020x780")
        self.root.minsize(850, 650)
        self.root.protocol("WM_DELETE_WINDOW", self.close)

        self.events: queue.Queue[tuple[str, Any]] = queue.Queue()
        self.cancel_event = threading.Event()
        self.busy = False
        self.close_requested = False
        self.records: list[ResultRecord] = []
        self.single_imei = StringVar()
        self._single_after_id: str | None = None
        self._last_warned_value = ""
        self.status_text = StringVar(value="SAP oturumunu açıp ZSERI1'i hazır edin.")
        self.current_text = StringVar(value="Henüz kontrol yok")
        self.progress_text = StringVar(value="0 / 0")

        self._build_ui()
        self.root.after_idle(self.single_entry.focus_set)
        self.root.after(100, self._poll_events)

    def _build_ui(self) -> None:
        outer = ttk.Frame(self.root, padding=16)
        outer.pack(fill=BOTH, expand=True)
        ttk.Label(outer, text="SAP Satınalma Kontrolü", font=("Segoe UI", 18, "bold")).pack(
            anchor="w"
        )
        ttk.Label(
            outer,
            text="Tek IMEI'yi barkodla okutun veya toplu listeyi yapıştırın. IMEI'ye V eklenip ZSERI1'de kontrol edilir.",
            wraplength=950,
        ).pack(anchor="w", pady=(4, 12))

        single_frame = ttk.LabelFrame(outer, text="Tek IMEI / Barkod", padding=12)
        single_frame.pack(fill=X, pady=(0, 10))
        self.single_entry = ttk.Entry(single_frame, textvariable=self.single_imei, font=("Segoe UI", 12))
        self.single_entry.pack(side=LEFT, fill=X, expand=True, padx=(0, 8))
        self.single_entry.bind("<Return>", self._single_submit)
        self.single_imei.trace_add("write", self._single_input_changed)
        self.single_result = ttk.Label(single_frame, textvariable=self.current_text, font=("Segoe UI", 10, "bold"))
        self.single_result.pack(anchor="w", pady=(8, 0))
        ttk.Label(
            single_frame,
            text=f"Tam {SINGLE_IMEI_LENGTH} rakam okutulduğunda/yapıştırıldığında kontrol otomatik başlar.",
        ).pack(anchor="w", pady=(4, 0))

        bulk_frame = ttk.LabelFrame(outer, text="Toplu IMEI", padding=12)
        bulk_frame.pack(fill=X, pady=(0, 10))
        ttk.Label(
            bulk_frame,
            text="Her satıra bir IMEI yapıştırın. Satır sonu, boşluk, virgül ve noktalı virgül ayraç olarak kabul edilir.",
        ).pack(anchor="w", pady=(0, 6))
        text_frame = ttk.Frame(bulk_frame)
        text_frame.pack(fill=X)
        self.bulk_text = Text(text_frame, height=5, wrap="none", font=("Consolas", 10))
        y_scroll = ttk.Scrollbar(text_frame, orient="vertical", command=self.bulk_text.yview)
        self.bulk_text.configure(yscrollcommand=y_scroll.set)
        self.bulk_text.pack(side=LEFT, fill=X, expand=True)
        y_scroll.pack(side=RIGHT, fill=Y)
        self.bulk_button = ttk.Button(
            bulk_frame, text="Toplu Kontrol Et ve Excel Oluştur", command=self.check_bulk
        )
        self.bulk_button.pack(anchor="e", pady=(8, 0))

        run_frame = ttk.Frame(outer)
        run_frame.pack(fill=X, pady=(0, 8))
        ttk.Label(run_frame, textvariable=self.status_text).pack(side=LEFT)
        ttk.Label(run_frame, textvariable=self.progress_text, font=("Segoe UI", 10, "bold")).pack(
            side=RIGHT
        )

        results_frame = ttk.LabelFrame(outer, text="Kontrol Sırası ve Sonuçlar", padding=8)
        results_frame.pack(fill=BOTH, expand=True)
        columns = ("sequence", "imei", "support_serial", "status", "checked_at", "details")
        self.results = ttk.Treeview(results_frame, columns=columns, show="headings", height=12)
        headings = {
            "sequence": ("Sıra", 55),
            "imei": ("IMEI", 145),
            "support_serial": ("Destek Seri Numarası", 185),
            "status": ("Sonuç", 145),
            "checked_at": ("Kontrol Zamanı", 150),
            "details": ("Açıklama", 260),
        }
        for column, (title, width) in headings.items():
            self.results.heading(column, text=title)
            self.results.column(column, width=width, minwidth=45, stretch=column == "details")
        self.results.tag_configure("found", foreground="#146c2e")
        self.results.tag_configure("not_found", foreground="#b42318")
        self.results.tag_configure("error", foreground="#9a6700")
        y_scroll_results = ttk.Scrollbar(results_frame, orient="vertical", command=self.results.yview)
        x_scroll_results = ttk.Scrollbar(results_frame, orient="horizontal", command=self.results.xview)
        self.results.configure(yscrollcommand=y_scroll_results.set, xscrollcommand=x_scroll_results.set)
        self.results.pack(side=LEFT, fill=BOTH, expand=True)
        y_scroll_results.pack(side=RIGHT, fill=Y)
        x_scroll_results.pack(side="bottom", fill=X)

    def _single_input_changed(self, *_args: str) -> None:
        del _args
        if self._single_after_id is not None:
            self.root.after_cancel(self._single_after_id)
            self._single_after_id = None

        value = self.single_imei.get().strip()
        if not value:
            self.current_text.set("Henüz kontrol yok")
            return

        if value != self._last_warned_value:
            self._last_warned_value = ""
        if len(value) == SINGLE_IMEI_LENGTH and value.isdigit():
            self.current_text.set(f"{len(value)} / {SINGLE_IMEI_LENGTH} rakam")
            self._single_after_id = self.root.after(200, self._auto_check_single, value)
        else:
            self.current_text.set(f"{len(value)} / {SINGLE_IMEI_LENGTH} rakam")
            self._single_after_id = self.root.after(900, self._validate_single_length, value)

    def _validate_single_length(self, expected_value: str) -> None:
        self._single_after_id = None
        if self.busy or self.single_imei.get().strip() != expected_value:
            return
        if expected_value == self._last_warned_value:
            return
        self._last_warned_value = expected_value
        try:
            normalize_imei(expected_value)
        except ImeiInputError as exc:
            messagebox.showwarning("IMEI uzunluğu hatalı", str(exc))
            self.single_entry.focus_set()
            self.single_entry.selection_range(0, END)

    def _auto_check_single(self, expected_value: str) -> None:
        self._single_after_id = None
        if self.busy or self.single_imei.get().strip() != expected_value:
            return
        self.check_single()

    def _single_submit(self, _event: Any) -> str:
        del _event
        if self._single_after_id is not None:
            self.root.after_cancel(self._single_after_id)
            self._single_after_id = None
        self.check_single()
        return "break"

    def _set_controls(self, enabled: bool) -> None:
        state = "normal" if enabled else "disabled"
        self.single_entry.configure(state=state)
        self.bulk_text.configure(state=state)
        self.bulk_button.configure(state=state)

    def _begin_job(self, worker: Any, status: str) -> None:
        if self.busy:
            return
        self.cancel_event.clear()
        self.busy = True
        self._set_controls(False)
        self.status_text.set(status)
        threading.Thread(target=worker, daemon=True).start()

    def check_single(self) -> None:
        if self.busy:
            return
        try:
            imei = normalize_imei(self.single_imei.get())
        except ImeiInputError as exc:
            messagebox.showwarning("IMEI uzunluğu hatalı", str(exc))
            self.single_entry.focus_set()
            self.single_entry.selection_range(0, END)
            return

        if self._single_after_id is not None:
            self.root.after_cancel(self._single_after_id)
            self._single_after_id = None
        self._last_warned_value = ""
        self.single_imei.set("")
        self.current_text.set(f"{imei}V kontrol ediliyor...")
        self._begin_job(lambda: self._single_worker(imei), "SAP'te tek IMEI kontrol ediliyor...")

    def _single_worker(self, imei: str) -> None:
        sap: SapGuiClient | None = None
        try:
            sap = SapGuiClient(
                self.cancel_event,
                lambda message: self.events.put(("status", message)),
            )
            result = sap.check_imei(imei)
            self.events.put(("single_result", (imei, result)))
            try:
                sap.return_to_selection_screen()
            except OperationCancelled:
                pass
            except Exception as exc:
                self.events.put(
                    ("status", f"{result.status}; ancak ZSERI1 ekranına dönülemedi: {exc}")
                )
        except OperationCancelled:
            pass
        except Exception as exc:
            self.events.put(("single_error", (imei, str(exc))))
            if sap is not None:
                try:
                    sap.return_to_selection_screen()
                except Exception:
                    pass
        finally:
            self.events.put(("finished", None))

    def check_bulk(self) -> None:
        if self.busy:
            return
        try:
            imeis = parse_imei_list(self.bulk_text.get("1.0", END))
        except ImeiInputError as exc:
            messagebox.showerror("IMEI listesi hatalı", str(exc))
            return

        default_name = f"SatinAlma_Kontrol_{datetime.now():%Y%m%d_%H%M%S}.xlsx"
        output_name = filedialog.asksaveasfilename(
            title="Kontrol sonuçları Excel dosyası",
            initialdir=str(Path.home() / "Desktop"),
            initialfile=default_name,
            defaultextension=".xlsx",
            filetypes=[("Excel çalışma kitabı", "*.xlsx")],
        )
        if not output_name:
            return

        self._clear_results()
        records = [
            ResultRecord(sequence=index, imei=imei, status=STATUS_PENDING)
            for index, imei in enumerate(imeis, start=1)
        ]
        for record in records:
            self._add_row(record)
        output_path = Path(output_name)
        self.progress_text.set(f"0 / {len(records)}")
        self._begin_job(
            lambda: self._bulk_worker(records, output_path),
            f"{len(records)} IMEI sırayla kontrol edilecek...",
        )

    def _bulk_worker(self, records: list[ResultRecord], output_path: Path) -> None:
        try:
            save_results_excel(output_path, records)
            sap = SapGuiClient(
                self.cancel_event,
                lambda message: self.events.put(("status", message)),
            )
            for index, record in enumerate(records):
                if self.cancel_event.is_set():
                    self._mark_bulk_not_checked(records[index:])
                    save_results_excel(output_path, records)
                    return
                self.events.put(("progress", (index + 1, len(records), record.support_serial)))
                try:
                    result = sap.check_imei(record.imei)
                except OperationCancelled:
                    self._mark_bulk_not_checked(records[index:])
                    save_results_excel(output_path, records)
                    return
                except Exception as exc:
                    record.status = STATUS_ERROR
                    record.checked_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    record.details = str(exc)
                    for remaining in records[index + 1 :]:
                        remaining.status = STATUS_NOT_CHECKED
                    save_results_excel(output_path, records)
                    self.events.put(("bulk_row", record))
                    self.events.put(("bulk_failed", (str(output_path), str(exc))))
                    return

                record.status = result.status
                record.checked_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                record.details = result.details
                save_results_excel(output_path, records)
                self.events.put(("bulk_row", record))
                sap.return_to_selection_screen()
            self.events.put(("bulk_done", str(output_path)))
        except OperationCancelled:
            self._mark_bulk_not_checked(records)
            save_results_excel(output_path, records)
        except Exception as exc:
            pending_records = [record for record in records if record.status == STATUS_PENDING]
            if pending_records:
                pending_records[0].status = STATUS_ERROR
                pending_records[0].checked_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                pending_records[0].details = str(exc)
                for record in pending_records[1:]:
                    record.status = STATUS_NOT_CHECKED
                try:
                    save_results_excel(output_path, records)
                except Exception as save_exc:
                    self.events.put(
                        ("bulk_error", f"{exc}\nExcel dosyasına yazılamadı: {save_exc}")
                    )
                else:
                    self.events.put(("bulk_failed", (str(output_path), str(exc))))
            else:
                self.events.put(("bulk_error", str(exc)))
        finally:
            self.events.put(("finished", None))

    @staticmethod
    def _mark_bulk_not_checked(records: list[ResultRecord]) -> None:
        for record in records:
            if record.status == STATUS_PENDING:
                record.status = STATUS_NOT_CHECKED
                record.details = "İşlem kullanıcı tarafından durduruldu."

    def _clear_results(self) -> None:
        self.records.clear()
        for item in self.results.get_children():
            self.results.delete(item)

    def _add_row(self, record: ResultRecord) -> None:
        self.records.append(record)
        tag = self._tag_for(record.status)
        self.results.insert(
            "",
            END,
            iid=str(record.sequence),
            values=(
                record.sequence,
                record.imei,
                record.support_serial,
                record.status,
                record.checked_at,
                record.details,
            ),
            tags=(tag,),
        )

    def _update_row(self, record: ResultRecord) -> None:
        item = str(record.sequence)
        values = (
            record.sequence,
            record.imei,
            record.support_serial,
            record.status,
            record.checked_at,
            record.details,
        )
        if self.results.exists(item):
            self.results.item(item, values=values, tags=(self._tag_for(record.status),))
        else:
            self.results.insert("", END, iid=item, values=values, tags=(self._tag_for(record.status),))
        self.results.see(item)

    @staticmethod
    def _tag_for(status: str) -> str:
        if status == STATUS_FOUND:
            return "found"
        if status == STATUS_NOT_FOUND:
            return "not_found"
        if status == STATUS_ERROR:
            return "error"
        return ""

    def _poll_events(self) -> None:
        while True:
            try:
                event, payload = self.events.get_nowait()
            except queue.Empty:
                break

            if event == "single_result":
                imei, result = payload
                record = ResultRecord(
                    sequence=len(self.records) + 1,
                    imei=imei,
                    status=result.status,
                    checked_at=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    details=result.details,
                )
                self._add_row(record)
                self.current_text.set(f"{record.support_serial}: {record.status}")
                self.status_text.set("Tek IMEI kontrolü tamamlandı.")
            elif event == "single_error":
                imei, error = payload
                record = ResultRecord(
                    sequence=len(self.records) + 1,
                    imei=imei,
                    status=STATUS_ERROR,
                    checked_at=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    details=error,
                )
                self._add_row(record)
                self.current_text.set(f"{record.support_serial}: kontrol edilemedi.")
                self.status_text.set(error)
            elif event == "progress":
                current, total, serial = payload
                self.progress_text.set(f"{current} / {total}")
                self.current_text.set(f"Sıradaki: {serial}")
            elif event == "status":
                self.status_text.set(str(payload))
            elif event == "bulk_row":
                record = payload
                self._update_row(record)
                self.status_text.set(f"{record.sequence}. IMEI: {record.status}")
            elif event == "bulk_done":
                self.status_text.set(f"Tamamlandı. Excel kaydedildi: {payload}")
                messagebox.showinfo("Kontrol tamamlandı", f"Sonuç Excel'i kaydedildi:\n{payload}")
            elif event == "bulk_failed":
                path, error = payload
                self.status_text.set(f"Kontrol durdu; sonuçlar kaydedildi: {path}")
                messagebox.showerror(
                    "SAP kontrolü durdu",
                    f"Sonuçlar ve kalan satırlar Excel'e kaydedildi:\n{path}\n\n{error}",
                )
            elif event == "bulk_error":
                self.status_text.set(f"Toplu kontrol başlatılamadı: {payload}")
                messagebox.showerror("Toplu kontrol hatası", str(payload))
            elif event == "finished":
                self.busy = False
                self._set_controls(True)
                if self.close_requested:
                    self.root.destroy()
                    return

        self.root.after(100, self._poll_events)

    def close(self) -> None:
        if self.busy:
            self.cancel_event.set()
        self.root.destroy()


def main() -> None:
    root = Tk()
    PurchaseCheckApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
