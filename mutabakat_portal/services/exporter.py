"""
Teknosa Mutabakat Verilerini Excel (.xlsx) Olarak Dışa Aktarma Servisi
Yüksek performanslı write_only akışı kullanır.
"""
import io
import openpyxl
from openpyxl.cell import WriteOnlyCell
from openpyxl.styles import Font, PatternFill, Alignment
from datetime import datetime
from ..database import query_all


def generate_mutabakat_excel(status_filter: str = "", store_filter: str = "") -> io.BytesIO:
    """Veritabanındaki güncel mutabakat kayıtlarını kurumsal Excel dosyasına dönüştürür."""
    wb = openpyxl.Workbook(write_only=True)
    ws = wb.create_sheet(title="MUTABAKAT")

    header_font = Font(name="Calibri", size=10, bold=True, color="FFFFFF")
    header_fill = PatternFill(start_color="1F4E78", end_color="1F4E78", fill_type="solid")
    align_center = Alignment(horizontal="center", vertical="center")

    headers = [
        "Müşteri Adı Soyadı", "T.C. Kimlik No", "Müşteri Telefon", "Adres", "Email",
        "Product ID", "IMEI", "Çift Adet Kontrol", "Wega Kaydı", "Ürün No",
        "Marka", "Model", "Durum", "Teslim Bilgisi", "Teslim Tarihi",
        "Takip Numarası", "Teslim Eden Kullanıcı", "İptal Nedeni", "Çek Bilgisi", "Çek Prefix",
        "Çek Tutarı", "Çek Durum", "Başlangıç Tarih", "Bitiş Tarih", "Sipariş No",
        "Sipariş Tutarı", "Sipariş Tarihi", "İşlem Tarihi", "İşlemi Yapan", "Mağaza Id",
        "Mağaza", "Firma Adı", "FİYAT (Hakediş)", "EKSİ PUAN", "TAM DEĞER",
        "Fark", "Statü", "Ekran Orijinal", "Kamera Orijinal", "Pil Orijinal", "Açıklama"
    ]

    header_cells = []
    for h in headers:
        c = WriteOnlyCell(ws, value=h)
        c.font = header_font
        c.fill = header_fill
        c.alignment = align_center
        header_cells.append(c)
    ws.append(header_cells)

    # Filtreli sorgu
    query = "SELECT * FROM mutabakat_records WHERE 1=1"
    params = []
    if status_filter:
        query += " AND reconciliation_status = ?"
        params.append(status_filter)
    if store_filter:
        query += " AND store_name = ?"
        params.append(store_filter)
    query += " ORDER BY id DESC"

    rows = query_all(query, tuple(params))

    for r in rows:
        vals = [
            r["customer_name"], r["tc_no"], r["phone"], r["address"], r["email"],
            r["product_id"], r["imei"], "ÇİFT İMEİ" if r["is_duplicate"] else "1",
            r["wega_record"], r["product_no"], r["brand"], r["model"], r["status"],
            r["delivery_info"], r["delivery_date"], r["tracking_no"], r["delivery_user"],
            r["cancel_reason"], r["voucher_no"], r["voucher_prefix"], r["voucher_amount"],
            r["voucher_status"], r["start_date"], r["end_date"], r["order_no"],
            r["order_amount"], r["order_date"], r["process_start_date"], r["process_user"],
            r["store_id"], r["store_name"], r["company_name"], r["calculated_price"],
            r["penalty_points"], r["full_price"], r["difference_amount"],
            r["reconciliation_status"], r["screen_original"], r["camera_original"],
            r["battery_original"], r["notes"]
        ]
        ws.append(vals)

    output = io.BytesIO()
    wb.save(output)
    output.seek(0)
    return output
