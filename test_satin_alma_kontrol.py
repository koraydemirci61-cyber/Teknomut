import unittest
import threading
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest.mock import patch

from openpyxl import load_workbook
from satin_alma_kontrol import (
    CheckResult,
    ImeiInputError,
    OperationCancelled,
    ResultRecord,
    SapGuiClient,
    PurchaseCheckApp,
    STATUS_FOUND,
    STATUS_NOT_FOUND,
    STATUS_PENDING,
    classify_grid_result,
    is_sap_logon_title,
    is_sap_session_title,
    normalize_imei,
    parse_imei_list,
    save_results_excel,
)


class ImeiParsingTests(unittest.TestCase):
    def test_accepts_exactly_15_digits(self):
        self.assertEqual(normalize_imei(" 356817113139387 "), "356817113139387")

    def test_parses_multiple_delimiters_and_preserves_order(self):
        self.assertEqual(
            parse_imei_list(
                "356817113139387\n"
                "357973434939804, 351380440090877"
            ),
            [
                "356817113139387",
                "357973434939804",
                "351380440090877",
            ],
        )

    def test_rejects_invalid_values_instead_of_skipping_them(self):
        with self.assertRaises(ImeiInputError):
            parse_imei_list("356817113139387\nnot-an-imei")

    def test_rejects_empty_list(self):
        with self.assertRaises(ImeiInputError):
            parse_imei_list(" \n, ; ")

    def test_rejects_short_imei(self):
        with self.assertRaisesRegex(ImeiInputError, "15 rakam"):
            normalize_imei("1" * 14)

    def test_rejects_long_imei(self):
        with self.assertRaisesRegex(ImeiInputError, "16 karakter"):
            normalize_imei("1" * 16)

    def test_rejects_non_digit_suffix(self):
        with self.assertRaises(ImeiInputError):
            normalize_imei("1" * 26 + "v")


class SapResultClassificationTests(unittest.TestCase):
    def test_result_rows_mean_purchase_record_exists(self):
        result = classify_grid_result(header_pixels=100, body_pixels=11)
        self.assertEqual(result, CheckResult(STATUS_FOUND, "SAP sonuç tablosunda kayıt bulundu."))
        self.assertEqual(result.status, "Transfer edilebilir")

    def test_empty_result_grid_means_no_purchase_record(self):
        result = classify_grid_result(header_pixels=100, body_pixels=0)
        self.assertEqual(result.status, "SAS yok")

    def test_blank_sap_screen_means_no_purchase_record(self):
        result = classify_grid_result(header_pixels=0, body_pixels=0)
        self.assertEqual(result.status, STATUS_NOT_FOUND)
        self.assertEqual(result.details, "SAP ekranı boş; satınalma kaydı bulunamadı.")

    def test_unrecognized_screen_is_an_error_not_a_negative_result(self):
        with self.assertRaises(RuntimeError):
            classify_grid_result(header_pixels=0, body_pixels=1)

    def test_check_imei_accepts_a_persistently_blank_sap_screen(self):
        sap = SapGuiClient.__new__(SapGuiClient)
        sap.at_selection_screen = True
        sap.hwnd = 1
        sap.win32con = SimpleNamespace(VK_F8=1)
        with (
            patch.object(SapGuiClient, "_raise_if_cancelled"),
            patch.object(SapGuiClient, "_activate_window"),
            patch.object(SapGuiClient, "_notify_status"),
            patch.object(SapGuiClient, "_click"),
            patch.object(SapGuiClient, "_ctrl_a"),
            patch.object(SapGuiClient, "_type_text"),
            patch.object(SapGuiClient, "_press"),
            patch.object(SapGuiClient, "_read_grid_pixel_counts", return_value=(0, 0)) as read_grid,
            patch.object(SapGuiClient, "_wait_or_cancel"),
        ):
            result = sap.check_imei("356817113139387")

        self.assertEqual(result.status, STATUS_NOT_FOUND)
        self.assertEqual(read_grid.call_count, 3)

    def test_sap_easy_access_is_a_valid_session_window(self):
        self.assertTrue(is_sap_session_title("QAS - SAP Easy Access"))

    def test_seri_takip_report_is_a_valid_session_window(self):
        self.assertTrue(is_sap_session_title("Seri Takip Raporu"))

    def test_sap_logon_pad_is_not_a_logged_in_session(self):
        self.assertFalse(is_sap_session_title("SAP Logon 740"))

    def test_sap_logon_title_is_detected(self):
        self.assertTrue(is_sap_logon_title("SAP Logon 740"))

    def test_sap_wait_is_interruptible_when_interface_closes(self):
        sap = SapGuiClient.__new__(SapGuiClient)
        sap.cancel_event = threading.Event()
        sap.cancel_event.set()
        with self.assertRaises(OperationCancelled):
            sap._wait_or_cancel(5)


class ExcelOutputTests(unittest.TestCase):
    def test_saves_imeis_in_sequence_with_v_suffix_and_status(self):
        records = [
            ResultRecord(1, "356817113139387", STATUS_NOT_FOUND, "2026-10-27 12:00:00"),
            ResultRecord(2, "357973434939804", STATUS_FOUND, "2026-10-27 12:00:01"),
        ]
        with TemporaryDirectory() as directory:
            output = Path(directory) / "results.xlsx"
            save_results_excel(output, records)

            workbook = load_workbook(output, read_only=True, data_only=True)
            worksheet = workbook.active
            rows = list(worksheet.iter_rows(values_only=True))
            workbook.close()

        self.assertEqual(
            rows[1][0:4],
            (1, "356817113139387", "356817113139387v", STATUS_NOT_FOUND),
        )
        self.assertEqual(
            rows[2][0:4],
            (2, "357973434939804", "357973434939804v", STATUS_FOUND),
        )

    def test_cancelled_bulk_records_are_not_reported_as_missing(self):
        records = [
            ResultRecord(1, "356817113139387", STATUS_PENDING),
            ResultRecord(2, "357973434939804", STATUS_PENDING),
        ]
        PurchaseCheckApp._mark_bulk_not_checked(records)
        self.assertEqual([record.status for record in records], ["Kontrol edilmedi", "Kontrol edilmedi"])


if __name__ == "__main__":
    unittest.main()
