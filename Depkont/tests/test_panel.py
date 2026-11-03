import tempfile
import unittest
from pathlib import Path
from tkinter import Tk

from openpyxl import load_workbook

from depkont.panel import DepkontPanel
from depkont.serials import NO_PURCHASE, REPORT_HEADER, SerialQuery, report_text


class PanelReportTests(unittest.TestCase):
    def test_result_is_shown_and_can_be_copied(self) -> None:
        root = Tk()
        try:
            panel = DepkontPanel(root, start_sap=False)
            panel.add_result("123456789012345V", SerialQuery(False))
            panel.add_result("123456789012346V", SerialQuery(True, "1005", "K.Yedek Parça"))
            shown = panel.report.get("1.0", "end").strip()
            self.assertIn("1\t123456789012345V\tsatın alması yok", shown)
            self.assertIn("2\t123456789012346V\t1005\tK.Yedek Parça", shown)
            panel.copy_report()
            copied = root.clipboard_get()
        finally:
            root.destroy()
        self.assertEqual(
            copied,
            report_text(
                [
                    ("123456789012345V", NO_PURCHASE, ""),
                    ("123456789012346V", "1005", "K.Yedek Parça"),
                ]
            ),
        )

    def test_clear_removes_only_the_report(self) -> None:
        root = Tk()
        try:
            panel = DepkontPanel(root, start_sap=False)
            panel.bulk.insert("1.0", "123456789012345")
            panel.add_result("123456789012345V", SerialQuery(False))
            panel.clear_report()
            shown = panel.report.get("1.0", "end").strip()
            listed = panel.bulk.get("1.0", "end")
        finally:
            root.destroy()
        self.assertEqual(shown, REPORT_HEADER)
        self.assertIn("123456789012345", listed)

    def test_list_shows_a_sequence_number_per_line(self) -> None:
        root = Tk()
        try:
            panel = DepkontPanel(root, start_sap=False)
            panel.bulk.insert("1.0", "123456789012345\n123456789012346")
            panel.refresh_list_numbers()
            numbers = panel.bulk_numbers.get("1.0", "end").strip().splitlines()
        finally:
            root.destroy()
        self.assertEqual(numbers, ["1", "2"])

    def test_excel_button_writes_the_current_report(self) -> None:
        root = Tk()
        try:
            panel = DepkontPanel(root, start_sap=False)
            panel.add_result("123456789012345V", SerialQuery(True, "1005", "K.Yedek Parça"))
            with tempfile.TemporaryDirectory() as folder:
                path = str(Path(folder) / "rapor.xlsx")
                panel.export_excel(path)
                sheet = load_workbook(path).active
                status = panel.status.get()
        finally:
            root.destroy()
        self.assertEqual(sheet["A2"].value, 1)
        self.assertEqual(sheet["B2"].value, "123456789012345V")
        self.assertIn("Excel kaydedildi", status)

    def test_stop_skips_serials_that_have_not_started(self) -> None:
        root = Tk()
        try:
            panel = DepkontPanel(root, start_sap=False)
            panel._start_worker = False
            seen: list[str] = []

            def query(support: str) -> SerialQuery:
                seen.append(support)
                panel._stop.set()
                return SerialQuery(False)

            panel._query_serial = query
            panel.jobs.put(("query", "123456789012345", "123456789012345V"))
            panel.jobs.put(("query", "123456789012346", "123456789012346V"))
            panel._run_jobs()
            root.update()
            status = panel.status.get()
            shown = panel.report.get("1.0", "end")
        finally:
            root.destroy()
        self.assertEqual(seen, ["123456789012345V"])
        self.assertIn("1\t123456789012345V", shown)
        self.assertNotIn("123456789012346V", shown)
        self.assertIn("1 seri sorgulanmadı", status)

    def test_stop_drops_a_queued_bulk_list_before_it_starts(self) -> None:
        root = Tk()
        try:
            panel = DepkontPanel(root, start_sap=False)
            panel._start_worker = False
            panel.enqueue_serials(["123456789012345", "123456789012346"])
            panel.stop_queries()
            waiting = panel.jobs.qsize()
            status = panel.status.get()
        finally:
            root.destroy()
        self.assertEqual(waiting, 0)
        self.assertIn("2 seri sorgulanmadı", status)


if __name__ == "__main__":
    unittest.main()
