from __future__ import annotations

import queue
import threading
import tkinter as tk
from tkinter import filedialog, font as tkfont

from depkont.sap_logon import SapLogonError
from depkont.sap_login import find_logged_in_session, open_sap_session
from depkont.serials import (
    NO_PURCHASE,
    REPORT_HEADER,
    SerialInputError,
    SerialQuery,
    parse_serial_list,
    report_text,
    split_serial,
    write_report_xlsx,
)
from depkont.zseri import ZseriClient

INK = "#12211c"
PAPER = "#e7efeb"
CARD = "#ffffff"
LINE = "#d5e2dc"
PINE = "#0f6e56"
PINE_DARK = "#0b5344"
CLAY = "#9f2d2d"
CLAY_DARK = "#7a2222"
MUTED = "#5d6f68"
FIELD = "#f7fbf9"


class DepkontPanel:
    def __init__(self, root: tk.Tk, *, start_sap: bool = True) -> None:
        self.root = root
        self.root.title("Depkont")
        self.root.geometry("980x760")
        self.root.minsize(860, 640)
        self.root.configure(bg=PAPER)
        self.rows: list[tuple[str, str, str]] = []
        self.jobs: queue.Queue[tuple[str, str, str]] = queue.Queue()
        self._worker: threading.Thread | None = None
        self._worker_lock = threading.Lock()
        self._stop = threading.Event()
        self._dropped = 0
        self._client: ZseriClient | None = None
        self._start_worker = True
        self._single_after: str | None = None
        self.status = tk.StringVar(value="Seri okutunca sorgulama başlar.")
        self._build()
        self.scan.focus_set()
        if start_sap:
            self.enqueue_prepare()

    def _build(self) -> None:
        header = tk.Frame(self.root, bg=INK, height=78)
        header.pack(fill="x")
        header.pack_propagate(False)
        tk.Label(
            header,
            text="Depkont",
            bg=INK,
            fg="#f4fbf7",
            font=("Segoe UI", 22, "bold"),
        ).pack(anchor="w", padx=28, pady=(16, 0))
        tk.Label(
            header,
            text="ZSERI1 destek seri sorgusu",
            bg=INK,
            fg="#b7cbc3",
            font=("Segoe UI", 10),
        ).pack(anchor="w", padx=28)

        body = tk.Frame(self.root, bg=PAPER)
        body.pack(fill="both", expand=True, padx=22, pady=18)

        scan_card = self._card(body)
        scan_card.pack(fill="x")
        tk.Label(
            scan_card,
            text="Seri barkod",
            bg=CARD,
            fg=INK,
            font=("Segoe UI", 13, "bold"),
        ).pack(anchor="w")
        tk.Label(
            scan_card,
            text="15 rakam okutulduğunda veya yapıştırıldığında hemen sorgulanır. Sonda V varsa yeniden eklenmez.",
            bg=CARD,
            fg=MUTED,
            font=("Segoe UI", 10),
            wraplength=860,
            justify="left",
        ).pack(anchor="w", pady=(2, 10))
        self.scan = tk.Entry(
            scan_card,
            font=("Segoe UI", 20),
            bg=FIELD,
            fg=INK,
            insertbackground=INK,
            relief="flat",
            highlightthickness=1,
            highlightbackground=LINE,
            highlightcolor=PINE,
        )
        self.scan.pack(fill="x", ipady=8, ipadx=8)
        self.scan.bind("<Return>", self._on_scan_return)
        self.scan.bind("<KeyRelease>", self._on_scan_key)

        report_card = self._card(body)
        report_card.pack(fill="both", expand=True, pady=14)
        report_head = tk.Frame(report_card, bg=CARD)
        report_head.pack(fill="x")
        tk.Label(
            report_head,
            text="Rapor",
            bg=CARD,
            fg=INK,
            font=("Segoe UI", 13, "bold"),
        ).pack(side="left")
        self.copy_button = self._button(report_head, "Kopyala", self.copy_report)
        self.copy_button.pack(side="right")
        self.excel_button = self._button(report_head, "Excel", self.export_excel)
        self.excel_button.pack(side="right", padx=(0, 8))
        self.clear_button = self._button(report_head, "Temizle", self.clear_report, role="quiet")
        self.clear_button.pack(side="right", padx=(0, 8))
        self.report = tk.Text(
            report_card,
            height=12,
            font=("Consolas", 12),
            bg=FIELD,
            fg=INK,
            relief="flat",
            highlightthickness=1,
            highlightbackground=LINE,
            highlightcolor=PINE,
            wrap="none",
            padx=12,
            pady=10,
            tabs=("56", "250", "420"),
        )
        self.report.pack(fill="both", expand=True, pady=(10, 0))
        self.report.tag_configure("head", foreground=MUTED, font=("Consolas", 11, "bold"))
        self.report.tag_configure("found", foreground=PINE_DARK)
        self.report.tag_configure("missing", foreground=CLAY)
        self.report.insert("1.0", f"{REPORT_HEADER}\n", "head")
        self.report.bind("<Key>", self._keep_report_read_only)
        self._bind_copy_keys(self.report)

        bulk_card = self._card(body)
        bulk_card.pack(fill="x")
        tk.Label(
            bulk_card,
            text="Toplu seri",
            bg=CARD,
            fg=INK,
            font=("Segoe UI", 13, "bold"),
        ).pack(anchor="w")
        tk.Label(
            bulk_card,
            text="Her satıra bir seri yapıştırın. Soldaki numara satır sırasıdır. Virgül, noktalı virgül ve boşluk da ayrılır.",
            bg=CARD,
            fg=MUTED,
            font=("Segoe UI", 10),
        ).pack(anchor="w", pady=(2, 8))
        bulk_box = tk.Frame(bulk_card, bg=CARD)
        bulk_box.pack(fill="x")
        self.bulk_numbers = tk.Text(
            bulk_box,
            width=4,
            height=5,
            font=("Consolas", 12),
            bg=FIELD,
            fg=MUTED,
            relief="flat",
            highlightthickness=1,
            highlightbackground=LINE,
            highlightcolor=LINE,
            wrap="none",
            padx=6,
            pady=8,
            takefocus=0,
            cursor="arrow",
        )
        self.bulk_numbers.pack(side="left", fill="y")
        self.bulk = tk.Text(
            bulk_box,
            height=5,
            font=("Consolas", 12),
            bg=FIELD,
            fg=INK,
            relief="flat",
            highlightthickness=1,
            highlightbackground=LINE,
            highlightcolor=PINE,
            wrap="none",
            padx=10,
            pady=8,
        )
        self.bulk.pack(side="left", fill="x", expand=True)
        self.bulk_scroll = tk.Scrollbar(bulk_box, command=self._bulk_yview)
        self.bulk_scroll.pack(side="left", fill="y", padx=(4, 0))
        self.bulk.configure(yscrollcommand=self._sync_bulk_scroll)
        self.bulk.bind("<<Modified>>", self._on_bulk_modified)
        self.refresh_list_numbers()
        self.bulk.edit_modified(False)
        actions = tk.Frame(bulk_box, bg=CARD)
        actions.pack(side="right", padx=(12, 0), anchor="s")
        self.query_button = self._button(actions, "Sorgula", self.query_bulk)
        self.query_button.pack(fill="x")
        self.stop_button = self._button(actions, "Durdur", self.stop_queries, role="danger")
        self.stop_button.pack(fill="x", pady=(8, 0))

        tk.Label(
            self.root,
            textvariable=self.status,
            bg=PAPER,
            fg=MUTED,
            anchor="w",
            font=("Segoe UI", 10),
            padx=28,
            pady=8,
        ).pack(fill="x")

    def _card(self, parent: tk.Widget) -> tk.Frame:
        card = tk.Frame(
            parent,
            bg=CARD,
            highlightthickness=1,
            highlightbackground=LINE,
            padx=16,
            pady=14,
        )
        return card

    def _button(self, parent: tk.Widget, text: str, command, *, role: str = "primary") -> tk.Button:
        colors = {
            "primary": (PINE, PINE_DARK, "#ffffff"),
            "danger": (CLAY, CLAY_DARK, "#ffffff"),
            "quiet": (PAPER, LINE, INK),
        }
        background, active, foreground = colors[role]
        button = tk.Button(
            parent,
            text=text,
            command=command,
            bg=background,
            fg=foreground,
            activebackground=active,
            activeforeground=foreground,
            relief="flat",
            bd=0,
            padx=16,
            pady=8,
            cursor="hand2",
            font=("Segoe UI", 10, "bold"),
        )
        return button

    def _keep_report_read_only(self, event: tk.Event) -> str | None:
        if event.state & 0x4 and event.keysym.lower() in {"c", "a"}:
            return None
        if event.keysym in {
            "Left",
            "Right",
            "Up",
            "Down",
            "Home",
            "End",
            "Prior",
            "Next",
            "Shift_L",
            "Shift_R",
            "Control_L",
            "Control_R",
        }:
            return None
        return "break"

    def _bind_copy_keys(self, widget: tk.Text) -> None:
        widget.bind("<Control-c>", self._copy_selection)
        widget.bind("<Control-C>", self._copy_selection)
        widget.bind("<Control-a>", self._select_all)
        widget.bind("<Control-A>", self._select_all)

    def _on_scan_key(self, _event: tk.Event) -> None:
        if self._single_after is not None:
            self.root.after_cancel(self._single_after)
            self._single_after = None
        value = self.scan.get()
        try:
            split_serial(value)
        except SerialInputError:
            return
        self._single_after = self.root.after(180, self._submit_scan)

    def _on_scan_return(self, _event: tk.Event) -> str:
        if self._single_after is not None:
            self.root.after_cancel(self._single_after)
            self._single_after = None
        self._submit_scan()
        return "break"

    def _submit_scan(self) -> None:
        self._single_after = None
        value = self.scan.get().strip()
        self.scan.delete(0, "end")
        if not value:
            return
        try:
            split_serial(value)
        except SerialInputError as exc:
            self.status.set(str(exc))
            return
        self.enqueue_serials([value])

    def query_bulk(self) -> None:
        try:
            values = parse_serial_list(self.bulk.get("1.0", "end"))
        except SerialInputError as exc:
            self.status.set(str(exc))
            return
        self.bulk.delete("1.0", "end")
        self.enqueue_serials(values)

    def enqueue_prepare(self) -> None:
        self.status.set("SAP hazırlanıyor...")
        self._enqueue([("prepare", "", "")])

    def enqueue_serials(self, values: list[str]) -> None:
        jobs = []
        for value in values:
            _base, support = split_serial(value)
            jobs.append(("query", value, support))
        self.status.set(f"Sırada {len(jobs)} seri var.")
        self._enqueue(jobs)

    def _enqueue(self, jobs: list[tuple[str, str, str]]) -> None:
        with self._worker_lock:
            if any(kind == "query" for kind, _raw, _support in jobs):
                self._stop.clear()
                self._dropped = 0
            for job in jobs:
                self.jobs.put(job)
            self._ensure_worker()

    def _ensure_worker(self) -> None:
        if not self._start_worker:
            return
        if self._worker is not None and self._worker.is_alive():
            return
        self._worker = threading.Thread(target=self._run_jobs, daemon=True)
        self._worker.start()

    def stop_queries(self) -> None:
        with self._worker_lock:
            self._stop.set()
            self._dropped += self._drain_queries_unlocked()
            running = self._worker is not None and self._worker.is_alive()
            dropped = self._dropped
            if not running:
                self._dropped = 0
        if running:
            self.status.set("Kontrol durduruluyor. Bu sorgu bitince kalan seriler atlanacak.")
            return
        if dropped:
            self._announce_stopped(dropped)
            return
        self.status.set("Çalışan kontrol yok.")

    def _drain_queries_unlocked(self) -> int:
        kept: list[tuple[str, str, str]] = []
        dropped = 0
        while True:
            try:
                job = self.jobs.get_nowait()
            except queue.Empty:
                break
            if job[0] == "query":
                dropped += 1
            else:
                kept.append(job)
        for job in kept:
            self.jobs.put(job)
        return dropped

    def _announce_stopped(self, dropped: int) -> None:
        if dropped:
            self.status.set(f"Kontrol durduruldu. {dropped} seri sorgulanmadı.")
            return
        self.status.set("Kontrol durduruldu.")

    def _run_jobs(self) -> None:
        try:
            import pythoncom

            pythoncom.CoInitialize()
        except Exception:
            pythoncom = None
        stopped = False
        dropped = 0
        try:
            while True:
                with self._worker_lock:
                    if self._stop.is_set():
                        self._dropped += self._drain_queries_unlocked()
                    try:
                        kind, _raw, support = self.jobs.get_nowait()
                    except queue.Empty:
                        self._worker = None
                        stopped = self._stop.is_set()
                        dropped = self._dropped
                        if stopped:
                            self._dropped = 0
                        break
                if kind == "prepare":
                    self._prepare_sap()
                    continue
                # The SAP call already in progress cannot be cut off safely.
                if self._stop.is_set():
                    with self._worker_lock:
                        self._dropped += 1
                    continue
                self.root.after(0, self.status.set, f"Sorgulanıyor: {support}")
                try:
                    result = self._query_serial(support)
                except (SapLogonError, SerialInputError) as exc:
                    result = SerialQuery(False, str(exc), "")
                self.root.after(0, self.add_result, support, result)
            if stopped:
                self.root.after(0, self._announce_stopped, dropped)
        finally:
            if pythoncom is not None:
                pythoncom.CoUninitialize()

    def _query_serial(self, support: str) -> SerialQuery:
        if find_logged_in_session() is None:
            open_sap_session()
        if self._client is None:
            self._client = ZseriClient()
        return self._client.query(support)

    def _prepare_sap(self) -> None:
        try:
            message = open_sap_session()
        except SapLogonError as exc:
            self.root.after(0, self.status.set, str(exc))
            return
        self.root.after(0, self.status.set, message)

    def add_result(self, support: str, result: SerialQuery) -> None:
        if result.found:
            location = result.location
            name = result.name
            tag = "found"
            detail = result.label
        else:
            location = result.location or NO_PURCHASE
            name = ""
            tag = "missing"
            detail = location
        index = len(self.rows) + 1
        self.rows.append((support, location, name))
        self.report.insert("end", f"{index}\t{support}\t{location}\t{name}\n", tag)
        self.report.see("end")
        self.status.set(f"{support}: {detail}")
        self.scan.focus_set()

    def clear_report(self) -> None:
        self.rows.clear()
        self.report.delete("1.0", "end")
        self.report.insert("1.0", f"{REPORT_HEADER}\n", "head")
        self.status.set("Rapor temizlendi.")

    def copy_report(self) -> None:
        if not self.rows:
            self.status.set("Kopyalanacak rapor yok.")
            return
        text = report_text(self.rows)
        self.root.clipboard_clear()
        self.root.clipboard_append(text)
        self.status.set("Rapor panoya kopyalandı.")

    def export_excel(self, path: str | None = None) -> None:
        if not self.rows:
            self.status.set("Aktarılacak rapor yok.")
            return
        if not path:
            path = filedialog.asksaveasfilename(
                parent=self.root,
                title="Raporu Excel'e kaydet",
                defaultextension=".xlsx",
                filetypes=[("Excel çalışma kitabı", "*.xlsx")],
                initialfile="depkont-rapor.xlsx",
            )
        if not path:
            return
        try:
            write_report_xlsx(path, self.rows)
        except ImportError:
            self.status.set("Excel için openpyxl kurulu değil.")
            return
        except OSError as exc:
            self.status.set(f"Excel kaydedilemedi: {exc}")
            return
        self.status.set(f"Excel kaydedildi: {path}")

    def refresh_list_numbers(self) -> None:
        text = self.bulk.get("1.0", "end-1c")
        lines = text.split("\n") if text else [""]
        numbers = "\n".join(str(index) for index in range(1, len(lines) + 1))
        self.bulk_numbers.configure(state="normal")
        self.bulk_numbers.delete("1.0", "end")
        self.bulk_numbers.insert("1.0", numbers)
        self.bulk_numbers.configure(state="disabled")

    def _on_bulk_modified(self, _event: tk.Event) -> None:
        if not self.bulk.edit_modified():
            return
        self.refresh_list_numbers()
        self.bulk.edit_modified(False)

    def _bulk_yview(self, *args: str) -> None:
        self.bulk.yview(*args)
        self.bulk_numbers.yview(*args)

    def _sync_bulk_scroll(self, first: str, last: str) -> None:
        self.bulk_scroll.set(first, last)
        self.bulk_numbers.yview_moveto(first)

    def _copy_selection(self, _event: tk.Event) -> str | None:
        try:
            selected = self.report.get("sel.first", "sel.last")
        except tk.TclError:
            return None
        self.root.clipboard_clear()
        self.root.clipboard_append(selected)
        return "break"

    def _select_all(self, _event: tk.Event) -> str:
        self.report.tag_add("sel", "1.0", "end")
        return "break"


def run_panel() -> None:
    try:
        from ctypes import windll

        windll.shcore.SetProcessDpiAwareness(1)
    except Exception:
        pass
    root = tk.Tk()
    default_font = tkfont.nametofont("TkDefaultFont")
    default_font.configure(family="Segoe UI", size=10)
    DepkontPanel(root)
    root.mainloop()
