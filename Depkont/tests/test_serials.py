from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from openpyxl import load_workbook

from depkont.serials import (
    NO_PURCHASE,
    SerialInputError,
    format_warehouse,
    parse_serial_list,
    report_text,
    split_serial,
    write_report_xlsx,
)
from depkont.zseri import query_support_serial


class _Field:
    def __init__(self, text: str = "") -> None:
        self.Text = text


class _LateGrid:
    def __init__(self) -> None:
        self.reads = 0
        self.current: tuple[int, str] | None = None

    @property
    def RowCount(self) -> int:
        self.reads += 1
        return 0 if self.reads < 3 else 1

    def GetCellValue(self, row: int, column: str) -> str:
        del row
        return {"LGORT": "1005", "LGOBE": "K.Yedek Parça"}[column]

    def SetCurrentCell(self, row: int, column: str) -> None:
        self.current = (row, column)


class _Grid:
    def __init__(self, rows: list[dict[str, str]]) -> None:
        self.RowCount = len(rows)
        self.rows = rows
        self.current: tuple[int, str] | None = None

    def GetCellValue(self, row: int, column: str) -> str:
        return self.rows[row][column]

    def SetCurrentCell(self, row: int, column: str) -> None:
        self.current = (row, column)


class _Window:
    def __init__(self, session: _Session) -> None:
        self.session = session

    def sendVKey(self, key: int) -> None:
        self.session.keys.append(key)
        if key == 0 and self.session.okcd.Text == "/nZSERI1":
            self.session.mode = "selection"
        elif key == 8 and self.session.mode == "selection":
            self.session.mode = "result"
        elif key == 3 and self.session.mode == "result":
            self.session.mode = "selection"


class _Session:
    def __init__(self, grid: _Grid, mode: str = "main") -> None:
        self.mode = mode
        self.okcd = _Field()
        self.field = _Field()
        self.grid = grid
        self.window = _Window(self)
        self.keys: list[int] = []

    def findById(self, path: str) -> object:
        if path == "wnd[0]/tbar[0]/okcd":
            return self.okcd
        if path == "wnd[0]":
            return self.window
        if path == "wnd[0]/usr/txtSZSERNR-LOW":
            if self.mode != "selection":
                raise RuntimeError(path)
            return self.field
        if path == "wnd[0]/usr/cntlGRID1/shellcont/shell":
            if self.mode != "result":
                raise RuntimeError(path)
            return self.grid
        raise RuntimeError(path)


class SerialTests(unittest.TestCase):
    def test_fifteen_digits_get_one_v(self) -> None:
        base, support = split_serial("123456789012345")
        self.assertEqual(base, "123456789012345")
        self.assertEqual(support, "123456789012345V")

    def test_existing_v_is_not_repeated(self) -> None:
        base, support = split_serial("123456789012345v")
        self.assertEqual(base, "123456789012345")
        self.assertEqual(support, "123456789012345V")

    def test_short_serial_is_rejected(self) -> None:
        with self.assertRaises(SerialInputError):
            split_serial("123V")

    def test_bulk_list_splits_lines_and_commas(self) -> None:
        values = parse_serial_list("123456789012345\n123456789012346V,123456789012347")
        self.assertEqual(len(values), 3)

    def test_empty_grid_means_no_purchase(self) -> None:
        self.assertEqual(format_warehouse(0, "", ""), NO_PURCHASE)

    def test_warehouse_uses_the_last_row_values(self) -> None:
        self.assertEqual(format_warehouse(2, "2200", "Servis Depo"), "2200 — Servis Depo")

    def test_report_is_tab_separated(self) -> None:
        text = report_text([("123456789012345V", NO_PURCHASE, "")])
        self.assertEqual(
            text,
            "Sıra\tDestek seri\tDepo yeri\tDepo yeri tanımı\n1\t123456789012345V\tsatın alması yok\t",
        )

    def test_report_xlsx_keeps_sequence_and_serial_text(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "rapor.xlsx"
            write_report_xlsx(
                str(path),
                [
                    ("123456789012345V", NO_PURCHASE, ""),
                    ("123456789012346V", "1005", "K.Yedek Parça"),
                ],
            )
            sheet = load_workbook(path).active
        self.assertEqual(
            [cell.value for cell in sheet[1]],
            ["Sıra", "Destek seri", "Depo yeri", "Depo yeri tanımı"],
        )
        self.assertEqual(sheet["A2"].value, 1)
        self.assertEqual(sheet["B2"].value, "123456789012345V")
        self.assertEqual(sheet["C2"].value, NO_PURCHASE)
        self.assertEqual(sheet["A3"].value, 2)
        self.assertEqual(sheet["C3"].value, "1005")
        self.assertEqual(sheet["D3"].value, "K.Yedek Parça")
        self.assertEqual(sheet["B2"].number_format, "@")


class ZseriFlowTests(unittest.TestCase):
    def test_main_screen_opens_zseri_and_reads_last_warehouse(self) -> None:
        grid = _Grid(
            [
                {"LGORT": "1000", "LGOBE": "Eski Depo"},
                {"LGORT": "2200", "LGOBE": "Servis Depo"},
            ]
        )
        session = _Session(grid)
        outcome = query_support_serial(
            session,
            "123456789012345V",
            clock=lambda: 0.0,
            pause=lambda _seconds: None,
        )
        self.assertEqual(session.field.Text, "123456789012345V")
        self.assertEqual(session.keys, [0, 8])
        self.assertEqual(grid.current, (1, "LGORT"))
        self.assertTrue(outcome.found)
        self.assertEqual(outcome.location, "2200")
        self.assertEqual(outcome.name, "Servis Depo")
        self.assertEqual(outcome.label, "2200 — Servis Depo")

    def test_result_screen_steps_back_before_the_next_query(self) -> None:
        grid = _Grid([])
        session = _Session(grid, mode="result")
        outcome = query_support_serial(
            session,
            "123456789012345V",
            clock=lambda: 0.0,
            pause=lambda _seconds: None,
        )
        self.assertEqual(session.keys[0], 3)
        self.assertFalse(outcome.found)
        self.assertEqual(outcome.label, NO_PURCHASE)

    def test_waits_until_the_last_filled_row_is_loaded(self) -> None:
        grid = _LateGrid()
        session = _Session(grid)
        outcome = query_support_serial(
            session,
            "350893110068016V",
            clock=lambda: 0.0,
            pause=lambda _seconds: None,
        )
        self.assertTrue(outcome.found)
        self.assertEqual(outcome.location, "1005")
        self.assertEqual(outcome.name, "K.Yedek Parça")


if __name__ == "__main__":
    unittest.main()
