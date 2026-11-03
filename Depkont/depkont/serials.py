from __future__ import annotations

import re
from dataclasses import dataclass

SERIAL_LENGTH = 15
NO_PURCHASE = "satın alması yok"
EMPTY_WAREHOUSE = "depo yeri boş"
REPORT_COLUMNS = ("Sıra", "Destek seri", "Depo yeri", "Depo yeri tanımı")
REPORT_HEADER = "\t".join(REPORT_COLUMNS)


class SerialInputError(ValueError):
    pass


def split_serial(value: str) -> tuple[str, str]:
    """Return the 15-digit serial and the destek seri sent to ZSERI1."""
    token = value.strip().upper()
    base = token[:-1] if token.endswith("V") else token
    if not re.fullmatch(rf"\d{{{SERIAL_LENGTH}}}", base):
        raise SerialInputError(
            f"Seri tam {SERIAL_LENGTH} rakam olmalı. Sonda V varsa yeniden eklenmez."
        )
    return base, f"{base}V"


def parse_serial_list(text: str) -> list[str]:
    tokens = [token for token in re.split(r"[\s,;]+", text.strip()) if token]
    if not tokens:
        raise SerialInputError("Sorgulanacak seri girilmedi.")
    errors: list[str] = []
    accepted: list[str] = []
    for token in tokens:
        try:
            split_serial(token)
        except SerialInputError:
            errors.append(token)
            continue
        accepted.append(token)
    if errors:
        preview = ", ".join(errors[:5])
        extra = f" ve {len(errors) - 5} değer daha" if len(errors) > 5 else ""
        raise SerialInputError(
            f"Geçersiz seri: {preview}{extra}. Her seri {SERIAL_LENGTH} rakam olmalı."
        )
    return accepted


def format_warehouse(row_count: int, location: str, name: str) -> str:
    if row_count <= 0:
        return NO_PURCHASE
    place = location.strip()
    title = name.strip()
    if place and title and title.casefold() != place.casefold():
        return f"{place} — {title}"
    if place or title:
        return place or title
    return EMPTY_WAREHOUSE


@dataclass(frozen=True)
class SerialQuery:
    found: bool
    location: str = ""
    name: str = ""

    @property
    def label(self) -> str:
        if not self.found:
            return NO_PURCHASE
        return format_warehouse(1, self.location, self.name)


def report_text(rows: list[tuple[str, str, str]]) -> str:
    lines = [REPORT_HEADER]
    for index, (support, location, name) in enumerate(rows, start=1):
        lines.append(f"{index}\t{support}\t{location}\t{name}")
    return "\n".join(lines)


def write_report_xlsx(path: str, rows: list[tuple[str, str, str]]) -> None:
    """Write the copyable report as an Excel workbook. Serials stay text."""
    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Font, PatternFill
    from openpyxl.utils import get_column_letter

    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "Rapor"
    sheet.append(list(REPORT_COLUMNS))
    for index, (support, location, name) in enumerate(rows, start=1):
        sheet.append([index, support, location, name])
    header_fill = PatternFill("solid", fgColor="0F6E56")
    header_font = Font(bold=True, color="FFFFFF", name="Calibri")
    for cell in sheet[1]:
        cell.fill = header_fill
        cell.font = header_font
        cell.alignment = Alignment(vertical="center")
    for row in sheet.iter_rows(min_row=2, min_col=2, max_col=2):
        for cell in row:
            cell.number_format = "@"
    for index, width in enumerate((8, 22, 18, 32), start=1):
        sheet.column_dimensions[get_column_letter(index)].width = width
    sheet.auto_filter.ref = sheet.dimensions
    sheet.freeze_panes = "A2"
    workbook.save(path)
