from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
import io
from pathlib import Path
import sqlite3
import tempfile
import unittest

from fastapi.testclient import TestClient
from openpyxl import Workbook, load_workbook

from seans_portal.app import create_app
from seans_portal.database import connect
from seans_portal.services import (
    PortalError, import_workbook, parse_workbook, save_assignments,
)


def sample_excel(*, duplicate=False, employee_numbers=True):
    book = Workbook()
    sheet = book.active
    sheet.title = "PERSONEL LİSTESİ"
    sheet.merge_cells("A1:D1")
    sheet["A1"] = "Personel Listesi"
    sheet["E1"] = "Test Eğitimi"
    sheet.append(["T.C. Kimlik No.", "Personel Ad Soyad", "İşyeri (Son)", "Birim (Son)",
                  "Sicil No." if employee_numbers else None])
    for values in [
        ["00000000001", "Örnek Personel", "Test İşyeri", "Birim A", "00007"],
        ["00000000002", "Örnek Personel", "Diğer İşyeri", "Birim A", "00008"],
        ["00000000001" if duplicate else "00000000003", "=literal-name", "Test İşyeri", "Birim B", "00009"],
    ]:
        sheet.append(values if employee_numbers else values[:4])
    sheet["B5"].data_type = "s"
    output = io.BytesIO()
    book.save(output)
    book.close()
    return output.getvalue()


class SeansPortalTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.path = Path(self.temporary.name) / "test.db"
        self.app = create_app(self.path)
        self.client = TestClient(self.app)
        self.addCleanup(self.client.close)
        import_workbook(self.path, sample_excel())
        with connect(self.path, write=True) as db:
            db.execute("DELETE FROM training_sessions")
            db.execute("INSERT INTO training_sessions VALUES (1, 'Sabah', '2026-11-19T09:00')")
            db.execute("INSERT INTO training_sessions VALUES (2, 'Öğleden sonra', '2026-11-19T14:00')")
            self.departments = [dict(row) for row in db.execute("SELECT * FROM departments ORDER BY name")]
            self.people = [dict(row) for row in db.execute("SELECT * FROM personnel ORDER BY identity_no")]

    def assignment(self, index=0, session_id=1, version=0, unavailable=False, absence_reason=""):
        return {
            "id": self.people[index]["id"],
            "session_id": session_id,
            "version": version,
            "unavailable": unavailable,
            "absence_reason": absence_reason,
        }

    def save(self, assignments, department_id=None):
        dept_id = department_id if department_id is not None else self.departments[0]["id"]
        return self.client.post("/api/assignments", json={
            "department_id": dept_id,
            "assignments": assignments,
        })

    def test_single_link_home_page_shows_departments_without_password(self):
        response = self.client.get("/")
        self.assertEqual(response.status_code, 200)
        self.assertIn("Birim A", response.text)
        self.assertIn("Birim B", response.text)
        self.assertNotIn('type="password"', response.text)

    def test_manager_screen_never_contains_sensitive_identifiers(self):
        response = self.client.get(f"/?dept_id={self.departments[0]['id']}")
        self.assertEqual(response.status_code, 200)
        for person in self.people:
            self.assertNotIn(person["identity_no"], response.text)
            self.assertNotIn(person["employee_no"], response.text)
        self.assertNotIn("identity_no", response.text)
        self.assertNotIn("employee_no", response.text)
        self.assertNotIn("00000000001", response.text)
        self.assertIn("Örnek Personel", response.text)
        self.assertIn("Diğer İşyeri", response.text)

    def test_assign_clear_and_export_preserve_identity_and_all_personnel(self):
        res = self.save([self.assignment(1, 2)])
        self.assertEqual(res.status_code, 200)

        response = self.client.get("/yonetim/excel")
        self.assertEqual(response.status_code, 200)
        book = load_workbook(io.BytesIO(response.content))
        self.addCleanup(book.close)
        detail = list(book["KATILIM LİSTESİ"].values)
        self.assertEqual(len(detail), 4)
        by_identity = {row[0]: row for row in detail[1:]}
        self.assertEqual(by_identity["00000000002"][1], "00008")
        self.assertEqual(by_identity["00000000002"][5:7], ("Öğleden sonra", "2026-11-19T14:00"))
        self.assertEqual(by_identity["00000000001"][5], "Seçilmedi")
        self.assertEqual(by_identity["00000000003"][2], "=literal-name")
        self.assertFalse(any(cell.data_type == "f" for sheet in book for row in sheet for cell in row))
        self.assertEqual(list(book["OTURUM ÖZETİ"].values)[-2:], [("Seçilmedi", None, 2), ("TOPLAM", None, 3)])

    def test_unavailable_requires_reason_and_exports_with_identity(self):
        absent_invalid = self.assignment(0, None, unavailable=True, absence_reason="")
        self.assertEqual(self.save([absent_invalid]).status_code, 400)

        absent_valid = self.assignment(0, None, unavailable=True, absence_reason="Raporlu")
        self.assertEqual(self.save([absent_valid]).status_code, 200)

        html = self.client.get(f"/?dept_id={self.departments[0]['id']}").text
        self.assertIn('value="absent" checked', html)
        self.assertIn("Raporlu", html)
        self.assertNotIn("00000000001", html)

        book = load_workbook(io.BytesIO(self.client.get("/yonetim/excel").content))
        self.addCleanup(book.close)
        rows = list(book["KATILIM LİSTESİ"].values)
        row = next(r for r in rows[1:] if r[0] == "00000000001")
        self.assertEqual(row[5], "Katılamayacak")
        self.assertEqual(row[9:], ("Katılamayacak", "Raporlu"))

    def test_contradictory_absence_and_stale_reason_changes_rejected(self):
        # hem seans hem katılamayacak seçilemez
        self.assertEqual(self.save([self.assignment(0, 1, unavailable=True, absence_reason="Hata")]).status_code, 400)
        # seans seçilip açıklama girilemez
        self.assertEqual(self.save([self.assignment(0, 1, unavailable=False, absence_reason="Gereksiz")]).status_code, 400)
        # 500 karakterden uzun açıklama girilemez
        self.assertEqual(self.save([self.assignment(0, None, unavailable=True, absence_reason="x" * 501)]).status_code, 422)

    def test_conflict_is_atomic_and_parallel_departments_do_not_lose_writes(self):
        with ThreadPoolExecutor(max_workers=2) as pool:
            futures = [
                pool.submit(save_assignments, self.path, self.departments[0]["id"], [self.assignment(0, 1)]),
                pool.submit(save_assignments, self.path, self.departments[1]["id"], [self.assignment(2, 2)]),
            ]
            for future in futures:
                future.result()
        # Stale version
        self.assertEqual(self.save([self.assignment(0, 2, version=0)]).status_code, 409)

    def test_simultaneous_edits_to_same_person_have_one_winner(self):
        def attempt(session_id):
            try:
                save_assignments(self.path, self.departments[0]["id"], [self.assignment(0, session_id)])
                return 200
            except PortalError as exc:
                return exc.status
        with ThreadPoolExecutor(max_workers=2) as pool:
            self.assertEqual(sorted(pool.map(attempt, [1, 2])), [200, 409])

    def test_admin_dashboard_and_session_management(self):
        page = self.client.get("/yonetim")
        self.assertEqual(page.status_code, 200)
        self.assertIn("Sabah", page.text)
        self.assertIn("Öğleden sonra", page.text)

        # Yeni seans ekleme
        res = self.client.post("/yonetim/seans", data={"label": "Akşam Grubu", "starts_at": "2026-11-19T18:00"})
        self.assertEqual(res.status_code, 200)
        page2 = self.client.get("/yonetim")
        self.assertIn("Akşam Grubu", page2.text)

        # Boş seansı silme
        with connect(self.path) as db:
            new_id = db.execute("SELECT id FROM training_sessions WHERE label='Akşam Grubu'").fetchone()[0]
        del_res = self.client.post(f"/yonetim/seans/{new_id}/sil")
        self.assertEqual(del_res.status_code, 200)

    def test_locked_mode_prevents_updates(self):
        self.client.post("/yonetim/settings", data={"title": "Kilitli Test", "locked": "on"})
        res = self.save([self.assignment(0, 1)])
        self.assertEqual(res.status_code, 403)
        self.assertIn("kapatıldı", res.json()["error"])

    def test_legacy_routes_redirect_to_single_link(self):
        self.assertEqual(self.client.get("/katilim", follow_redirects=False).status_code, 303)
        self.assertEqual(self.client.get("/giris", follow_redirects=False).status_code, 303)
        self.assertEqual(self.client.get("/birim", follow_redirects=False).status_code, 303)
        self.assertEqual(self.client.get("/birim?department_id=1", follow_redirects=False).headers["location"], "/?dept_id=1")
        self.assertEqual(self.client.get("/yonetici", follow_redirects=False).headers["location"], "/yonetim")


class WorkbookTests(unittest.TestCase):
    def test_optional_employee_column_and_duplicate_names_preserved(self):
        people, title = parse_workbook(sample_excel(employee_numbers=False))
        self.assertEqual(len(people), 3)
        self.assertTrue(all(person.employee_no == "" for person in people))
        self.assertEqual(people[0].name, people[1].name)
        self.assertEqual(title, "Test Eğitimi")

    def test_invalid_workbooks_do_not_partially_import(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "test.db"
            create_app(path)
            for content in (b"invalid", sample_excel(duplicate=True)):
                with self.assertRaises(PortalError):
                    import_workbook(path, content)
                with connect(path) as db:
                    self.assertEqual(db.execute("SELECT COUNT(*) FROM personnel").fetchone()[0], 0)
                    self.assertEqual(db.execute("SELECT COUNT(*) FROM departments").fetchone()[0], 0)


if __name__ == "__main__":
    unittest.main()


class WorkbookTests(unittest.TestCase):
    def test_optional_employee_column_and_duplicate_names_preserved(self):
        people, title = parse_workbook(sample_excel(employee_numbers=False))
        self.assertEqual(len(people), 3)
        self.assertTrue(all(person.employee_no == "" for person in people))
        self.assertEqual(people[0].name, people[1].name)
        self.assertEqual(title, "Test Eğitimi")

    def test_invalid_workbooks_do_not_partially_import(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "test.db"
            create_app(path)
            for content in (b"invalid", sample_excel(duplicate=True)):
                with self.assertRaises(PortalError):
                    import_workbook(path, content)
                with connect(path) as db:
                    self.assertEqual(db.execute("SELECT COUNT(*) FROM personnel").fetchone()[0], 0)
                    self.assertEqual(db.execute("SELECT COUNT(*) FROM departments").fetchone()[0], 0)

    def test_numeric_identifier_format_and_formula_rejection(self):
        book = load_workbook(io.BytesIO(sample_excel()))
        sheet = book.active
        sheet["A3"] = 1
        sheet["A3"].number_format = "00000000000"
        output = io.BytesIO()
        book.save(output)
        self.assertEqual(parse_workbook(output.getvalue())[0][0].identity_no, "00000000001")
        sheet["B3"] = "=1+1"
        output = io.BytesIO()
        book.save(output)
        book.close()
        with self.assertRaisesRegex(PortalError, "formül"):
            parse_workbook(output.getvalue())


if __name__ == "__main__":
    unittest.main()
