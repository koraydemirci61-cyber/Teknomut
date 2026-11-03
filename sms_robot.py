from __future__ import annotations

import os
import threading
import time
from pathlib import Path
from tkinter import StringVar, Tk, ttk, messagebox

from openpyxl import load_workbook
from playwright.sync_api import sync_playwright


DEFAULT_EXCEL_PATH = Path(r"C:\Users\koray.demirci\Desktop\Sms Robot\sms.xlsx")
LOGIN_URL = "https://destekwega.com/Community/Login.aspx?LRP=/"
REPORT_URL = "https://destekwega.com/Reports/SerialNumberTransactions.aspx"


def read_notification_numbers(excel_path: Path):
    path = excel_path
    if not path.exists():
        candidates = [
            Path(__file__).resolve().parent / "sms.xlsx",
            Path.cwd() / "sms.xlsx",
            Path.cwd() / "Sms Robot" / "sms.xlsx",
        ]
        for candidate in candidates:
            if candidate.exists():
                path = candidate
                break
        else:
            return []

    workbook = load_workbook(path, read_only=True)
    worksheet = workbook.active
    numbers = []
    for row in worksheet.iter_rows(min_row=2, values_only=True):
        value = row[0]
        if value is None:
            continue
        text = str(value).strip()
        if text:
            numbers.append(text)
    workbook.close()
    return numbers


def send_sms_tik_kaldir(page):
    """SendSms checkbox'ını kaldır, onay dialog'unu yönet."""
    try:
        page.wait_for_timeout(1500)
        send_sms_checkbox = page.locator("#sendSmsChk")

        if send_sms_checkbox.count() == 0:
            return True

        if not send_sms_checkbox.is_checked():
            return True

        def dialog_handler(dialog):
            dialog.accept()

        page.on("dialog", dialog_handler)
        send_sms_checkbox.click()
        page.wait_for_timeout(2000)
        try:
            page.remove_listener("dialog", dialog_handler)
        except Exception:
            pass

        if send_sms_checkbox.is_checked() or send_sms_checkbox.get_attribute("checked") is not None:
            page.evaluate(
                """
                (function() {
                    var el = document.getElementById('sendSmsChk');
                    if (el) {
                        el.checked = false;
                        el.removeAttribute('checked');
                        var evt = new Event('change', { bubbles: true });
                        el.dispatchEvent(evt);
                    }
                })();
                """
            )
        page.evaluate(
            """
            (function() {
                var el = document.getElementById('sendSmsChk');
                if (el) {
                    el.checked = false;
                    el.removeAttribute('checked');
                }
            })();
            """
        )
        return True
    except Exception:
        try:
            page.evaluate(
                """
                (function() {
                    var el = document.getElementById('sendSmsChk');
                    if (el) {
                        el.checked = false;
                        el.removeAttribute('checked');
                        var evt = new Event('change', { bubbles: true });
                        el.dispatchEvent(evt);
                    }
                })();
                """
            )
        except Exception:
            pass
        return True


def process_notification(page, notification_no, index, total):
    """Tek bir bildirim için tüm prosedürü çalıştırır."""
    print(f"\n--- [{index}/{total}] Bildirim: {notification_no} işleniyor ---")

    try:
        page.fill("#RepairOrderNo", str(notification_no))
        print(f"  ✓ RepairOrderNo alanına '{notification_no}' yazıldı.")

        page.press("#RepairOrderNo", "Enter")
        print("  ✓ Enter tuşuna basıldı. Sonuç bekleniyor...")
        page.wait_for_timeout(5000)

        try:
            repair_link_target = f"/CustomerService/RepairOrder.aspx?SAPID={notification_no}"
            target_locator = page.locator(f"a[href='{repair_link_target}']")
            if target_locator.count() == 0:
                target_locator = page.locator(f"a[href*='RepairOrder.aspx'][href*='{notification_no}']")
            if target_locator.count() == 0:
                product_history = page.locator("a:has-text('Ürün Kabul Tarihçesi')")
                if product_history.count() > 0:
                    product_history.first.click()
                    print("  ✓ 'Ürün Kabul Tarihçesi' linkine tıklandı!")
                else:
                    text_history = page.locator("text='Ürün Kabul Tarihçesi'")
                    if text_history.count() > 0:
                        text_history.first.click()
                        print("  ✓ 'Ürün Kabul Tarihçesi' yazısına tıklandı!")
                    else:
                        print("  ✗ 'Ürün Kabul Tarihçesi' bulunamadı.")
                        return False
                page.wait_for_timeout(3000)
                repair_link = page.locator(f"a[href*='RepairOrder.aspx'][href*='{notification_no}']")
                if repair_link.count() == 0:
                    repair_link = page.locator(f"a[href*='RepairOrder.aspx'][href*='{notification_no}']")
                if repair_link.count() == 0:
                    print("  ✗ RepairOrder linki bulunamadı.")
                    return False
            with page.expect_popup() as popup_info:
                target_locator.first.click()
            new_tab = popup_info.value
            print("  ✓ RepairOrder linkine tıklandı! Yeni sekme açıldı.")
            new_tab.wait_for_load_state()
            new_tab.wait_for_timeout(2000)
        except Exception as exc:
            print(f"  ✗ RepairOrder linki tıklanamadı: {exc}")
            return False

        send_sms_tik_kaldir(new_tab)

        try:
            new_tab.wait_for_timeout(1000)
            save_button = new_tab.locator("input[type='submit'][value='Kaydet']")
            if save_button.count() > 0:
                save_button.first.click()
                print("  ✓ Kaydet butonuna basıldı!")
                new_tab.wait_for_timeout(3000)
            else:
                print("  ✗ Kaydet butonu bulunamadı.")
                try:
                    new_tab.close()
                except Exception:
                    pass
                return False
        except Exception as exc:
            print(f"  ✗ Kaydet butonuna basılamadı: {exc}")
            try:
                new_tab.close()
            except Exception:
                pass
            return False

        try:
            new_tab.close()
            print("  ✓ Yeni sekme kapatıldı.")
        except Exception:
            pass

        try:
            page.goto(REPORT_URL)
            print("  ✓ Alt Q sayfasına geri dönüldü.")
            page.wait_for_timeout(3000)
        except Exception as exc:
            print(f"  ✗ Alt Q sayfasına dönülemedi: {exc}")
            return False

        print(f"  ✓ [{index}/{total}] Bildirim {notification_no} BAŞARILI!")
        return True
    except Exception as exc:
        print(f"  ✗ [{index}/{total}] Bildirim {notification_no} hata: {exc}")
        try:
            page.goto(REPORT_URL)
            page.wait_for_timeout(3000)
        except Exception:
            pass
        return False


class SmsRobotApp:
    def __init__(self, root: Tk):
        self.root = root
        self.root.title("SMS Robot Panel")
        self.root.geometry("500x360")
        self.root.resizable(False, False)

        self.excel_path = DEFAULT_EXCEL_PATH
        self.notification_numbers = read_notification_numbers(self.excel_path)
        if not self.notification_numbers:
            self.notification_numbers = []

        self.total_count = len(self.notification_numbers)
        self.success_count = 0
        self.failed_count = 0
        self.processed_count = 0
        self.current_notification = "Bekleniyor"
        self._is_running = False
        self._paused = False
        self._stop_requested = False
        self._thread = None

        self._build_ui()
        self.refresh_stats()

    def _build_ui(self):
        container = ttk.Frame(self.root, padding=16)
        container.pack(fill="both", expand=True)

        label_title = ttk.Label(container, text="SMS Robot", font=("Segoe UI", 18, "bold"))
        label_title.pack(anchor="w", pady=(0, 12))

        card = ttk.Frame(container, padding=12)
        card.pack(fill="x")

        self.total_var = StringVar(value="0")
        self.processed_var = StringVar(value="0")
        self.success_var = StringVar(value="0")
        self.failed_var = StringVar(value="0")
        self.percent_var = StringVar(value="0%")
        self.current_var = StringVar(value=self.current_notification)
        self.status_var = StringVar(value="Hazır")

        stats = [
            ("Toplam", self.total_var),
            ("İşlenen", self.processed_var),
            ("Başarılı", self.success_var),
            ("Başarısız", self.failed_var),
            ("Yüzde", self.percent_var),
        ]

        for index, (title, variable) in enumerate(stats):
            row = ttk.Frame(card)
            row.pack(fill="x", pady=4)
            ttk.Label(row, text=f"{title}:", width=14, anchor="w").pack(side="left")
            ttk.Label(row, textvariable=variable, width=12, anchor="e", font=("Segoe UI", 11, "bold")).pack(side="right")

        current_frame = ttk.Frame(container)
        current_frame.pack(fill="x", pady=(14, 8))
        ttk.Label(current_frame, text="Mevcut bildirim:", font=("Segoe UI", 10, "bold")).pack(anchor="w")
        ttk.Label(current_frame, textvariable=self.current_var, foreground="#1e3a8a", font=("Segoe UI", 11, "bold")).pack(anchor="w", pady=(4, 0))

        status_frame = ttk.Frame(container)
        status_frame.pack(fill="x", pady=(0, 12))
        ttk.Label(status_frame, text="Durum:", font=("Segoe UI", 10, "bold")).pack(anchor="w")
        ttk.Label(status_frame, textvariable=self.status_var, foreground="#0f766e", font=("Segoe UI", 10, "bold")).pack(anchor="w", pady=(4, 0))

        buttons = ttk.Frame(container)
        buttons.pack(fill="x")

        self.start_button = ttk.Button(buttons, text="Başlat", command=self.start_processing)
        self.start_button.pack(side="left", padx=(0, 8))

        self.pause_button = ttk.Button(buttons, text="Duraklat", command=self.toggle_pause, state="disabled")
        self.pause_button.pack(side="left", padx=(0, 8))

        self.close_button = ttk.Button(buttons, text="Kapat", command=self.close_app)
        self.close_button.pack(side="left")

    def refresh_stats(self):
        self.total_var.set(str(self.total_count))
        self.processed_var.set(str(self.processed_count))
        self.success_var.set(str(self.success_count))
        self.failed_var.set(str(self.failed_count))

        if self.total_count > 0:
            pct = round((self.processed_count / self.total_count) * 100)
        else:
            pct = 0
        self.percent_var.set(f"{pct}%")
        self.current_var.set(self.current_notification)

    def _update_ui_async(self):
        self.root.after(0, self.refresh_stats)
        self.root.after(0, lambda: self.status_var.set("Çalışıyor" if self._is_running and not self._paused else "Duraklatıldı" if self._paused else "Tamamlandı" if self.processed_count >= self.total_count and self.total_count else "Hazır"))

    def start_processing(self):
        if self._is_running:
            return

        if not self.notification_numbers:
            messagebox.showwarning("SMS Robot", "Excel dosyasında işlenecek bildirim bulunamadı.")
            return

        self._is_running = True
        self._paused = False
        self._stop_requested = False
        self.success_count = 0
        self.failed_count = 0
        self.processed_count = 0
        self.current_notification = "Başlatıldı"
        self.pause_button.configure(state="normal", text="Duraklat")
        self.start_button.configure(state="disabled")
        self.status_var.set("Çalışıyor")
        self.refresh_stats()

        self._thread = threading.Thread(target=self._run_worker, daemon=True)
        self._thread.start()

    def toggle_pause(self):
        if not self._is_running:
            return

        self._paused = not self._paused
        if self._paused:
            self.pause_button.configure(text="Devam Et")
            self.status_var.set("Duraklatıldı")
        else:
            self.pause_button.configure(text="Duraklat")
            self.status_var.set("Çalışıyor")

    def close_app(self):
        if self._is_running:
            self._stop_requested = True
            self._paused = False
            self.pause_button.configure(text="Duraklat")
        self.show_summary()
        self.root.destroy()

    def show_summary(self):
        summary = (
            "SMS Robot Özeti\n\n"
            f"Toplam: {self.total_count}\n"
            f"İşlenen: {self.processed_count}\n"
            f"Başarılı: {self.success_count}\n"
            f"Başarısız: {self.failed_count}\n"
            f"Mevcut bildirim: {self.current_notification}"
        )
        messagebox.showinfo("Özet", summary)

    def _run_worker(self):
        try:
            with sync_playwright() as p:
                browser = p.chromium.launch(headless=False)
                context = browser.new_context()
                page = context.new_page()

                page.goto(LOGIN_URL)
                page.wait_for_timeout(2000)
                page.fill("#UserName", "koray")
                page.fill("input[name='Password']", "3A5MF62W")
                page.click("input[name='Enter']")
                page.wait_for_timeout(5000)

                page.goto(REPORT_URL)
                page.wait_for_timeout(3000)

                for index, notification in enumerate(self.notification_numbers, start=1):
                    if self._stop_requested:
                        break

                    while self._paused and not self._stop_requested:
                        self.root.after(0, lambda: self.status_var.set("Duraklatıldı"))
                        time.sleep(0.25)

                    if self._stop_requested:
                        break

                    self.current_notification = str(notification)
                    self.processed_count = index - 1
                    self.root.after(0, self.refresh_stats)
                    result = process_notification(page, notification, index, self.total_count)
                    self.processed_count = index

                    if result:
                        self.success_count += 1
                    else:
                        self.failed_count += 1

                    self.root.after(0, self.refresh_stats)

                if not self._stop_requested:
                    self.status_var.set("Tamamlandı")
        except Exception as exc:
            self.root.after(0, lambda: self.status_var.set(f"Hata: {exc}"))
        finally:
            self._is_running = False
            self._paused = False
            self.root.after(0, self._finalize_worker)

    def _finalize_worker(self):
        self.pause_button.configure(state="disabled", text="Duraklat")
        self.start_button.configure(state="normal")
        self.current_notification = self.current_notification if self.current_notification else "Tamamlandı"
        self.refresh_stats()

        if self.processed_count >= self.total_count and self.total_count > 0 and not self._stop_requested:
            self.status_var.set("Tamamlandı")
            messagebox.showinfo("İşlem Tamamlandı", f"Toplam {self.total_count} bildirim işlendi.\nBaşarılı: {self.success_count}\nBaşarısız: {self.failed_count}")
        elif self._stop_requested:
            self.status_var.set("Durduruldu")


def main():
    root = Tk()
    app = SmsRobotApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
