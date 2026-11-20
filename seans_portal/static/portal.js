"use strict";

document.querySelector("#go-back")?.addEventListener("click", () => history.back());
document.querySelectorAll("form[data-confirm]").forEach(form => {
  form.addEventListener("submit", event => {
    if (!window.confirm(form.dataset.confirm)) event.preventDefault();
  });
});

async function postJSON(url, body) {
  const response = await fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body)
  });
  if (!response.headers.get("content-type")?.includes("application/json")) {
    throw new Error("Sunucu beklenmeyen yanıt verdi. Sayfayı yenileyip tekrar deneyin.");
  }
  const result = await response.json();
  if (!response.ok) {
    throw new Error(result.error || "İşlem tamamlanamadı. Lütfen kontrol edin.");
  }
  return result;
}

// --- DEPARTMAN SEÇİM AÇILIR KUTUSU ---
const deptSelect = document.querySelector("#dept-select");
if (deptSelect) {
  deptSelect.addEventListener("change", () => {
    const roster = document.querySelector("#roster");
    if (roster && window.__isDirty && window.__isDirty()) {
      if (!window.confirm("Kaydedilmemiş seçimleriniz var. Sayfadan ayrılırsanız bu değişiklikler kaybolacak. Devam edilsin mi?")) {
        deptSelect.value = roster.dataset.deptId || "";
        return;
      }
    }
    const val = deptSelect.value;
    if (val) {
      window.location.href = `/?dept_id=${val}`;
    } else {
      window.location.href = "/";
    }
  });
}

// --- ŞEFLERLE PAYLAŞILACAK TEK LİNK KOPYALAMA (YÖNETİM SAYFASI) ---
const shareLinkInput = document.querySelector("#share-link");
const copyShareBtn = document.querySelector("#copy-share-btn");
if (shareLinkInput && copyShareBtn) {
  const shareMsg = document.querySelector("#share-msg");
  shareLinkInput.value = `${window.location.origin}/`;
  copyShareBtn.addEventListener("click", async () => {
    try {
      shareLinkInput.select();
      shareLinkInput.focus();
      if (navigator.clipboard && navigator.clipboard.writeText) {
        await navigator.clipboard.writeText(shareLinkInput.value);
      } else {
        document.execCommand("copy");
      }
      if (shareMsg) {
        shareMsg.textContent = "✓ Link panoya kopyalandı! Yöneticilerle bu tek linki paylaşabilirsiniz.";
        shareMsg.style.color = "#127f83";
      }
    } catch {
      if (shareMsg) {
        shareMsg.textContent = "Link seçildi, kopyalamak için Ctrl+C tuşlarına basın.";
      }
    }
  });
}

// --- PERSONEL SEANS LİSTESİ VE KAYDETME İŞLEMLERİ ---
const roster = document.querySelector("#roster");
if (roster) {
  const rows = [...roster.querySelectorAll(".person-row")];
  const saveButton = document.querySelector("#save-assignments");
  const status = document.querySelector("#save-status");
  let saving = false;
  let saved = false;

  const choice = row => {
    const checked = row.querySelector(".person-session:checked");
    return checked ? checked.value : "";
  };

  const reason = row => {
    const ch = choice(row);
    if (ch === "absent") {
      const area = row.querySelector(".absence-reason");
      return area ? area.value.trim() : "";
    }
    return "";
  };

  const isRowDirty = row => {
    const originalChoice = row.dataset.original || "";
    const currentChoice = choice(row);
    const area = row.querySelector(".absence-reason");
    const originalReason = area ? (area.dataset.original || "") : "";
    const currentReason = reason(row);
    return currentChoice !== originalChoice || currentReason !== originalReason;
  };

  const dirtyRows = () => rows.filter(isRowDirty);
  window.__isDirty = () => dirtyRows().length > 0;

  function filterRows() {
    const search = document.querySelector("#person-search")?.value.toLocaleLowerCase("tr").trim() || "";
    const onlyPending = document.querySelector("#only-pending")?.checked || false;

    rows.forEach(row => {
      const name = row.querySelector(".person-name")?.textContent || "";
      const workplace = row.querySelector(".person-workplace")?.textContent || "";
      const text = `${name} ${workplace}`.toLocaleLowerCase("tr");

      const matchesSearch = !search || text.includes(search);
      const isPending = choice(row) === "";
      const matchesPending = !onlyPending || isPending;

      row.hidden = !(matchesSearch && matchesPending);
    });

    const emptySearch = document.querySelector("#empty-search");
    if (emptySearch) {
      emptySearch.hidden = rows.some(r => !r.hidden);
    }
  }

  function changed() {
    rows.forEach(row => {
      const absent = choice(row) === "absent";
      const field = row.querySelector(".absence-field");
      const textarea = row.querySelector(".absence-reason");
      if (field) field.hidden = !absent;
      if (textarea) textarea.required = absent;
    });

    const count = dirtyRows().length;
    if (status) {
      status.textContent = count
        ? `${count} personel için değişiklik yapıldı (Kaydedilmedi).`
        : "Kaydedilmemiş değişiklik yok.";
      status.style.color = count ? "#ce922a" : "#65788b";
    }

    if (saveButton) {
      saveButton.disabled = !count || saving;
    }

    filterRows();
  }

  rows.forEach(row => {
    row.querySelectorAll(".person-session").forEach(input => {
      input.addEventListener("change", changed);
    });
    const textarea = row.querySelector(".absence-reason");
    if (textarea) {
      textarea.addEventListener("input", changed);
    }
  });

  document.querySelector("#person-search")?.addEventListener("input", filterRows);
  document.querySelector("#only-pending")?.addEventListener("change", filterRows);

  // Toplu seans uygulama
  document.querySelector("#apply-bulk")?.addEventListener("click", () => {
    const bulkValue = document.querySelector("#bulk-session")?.value;
    if (bulkValue === undefined) return;

    rows.filter(row => !row.hidden).forEach(row => {
      const radio = row.querySelector(`.person-session[value="${bulkValue}"]`);
      if (radio) {
        radio.checked = true;
      }
    });
    changed();
  });

  // Kaydet butonu
  saveButton?.addEventListener("click", async () => {
    if (saving) return;

    // Katılamayacak seçilip açıklama yazılmamış olan var mı?
    const missingReasonRow = dirtyRows().find(row => choice(row) === "absent" && !reason(row));
    if (missingReasonRow) {
      const textarea = missingReasonRow.querySelector(".absence-reason");
      missingReasonRow.hidden = false;
      if (textarea) {
        textarea.reportValidity();
        textarea.focus();
      }
      if (status) {
        status.textContent = "Lütfen katılamayacak personel için açıklama yazınız.";
        status.style.color = "#c0392b";
      }
      return;
    }

    const assignments = dirtyRows().map(row => {
      const ch = choice(row);
      const isAbsent = ch === "absent";
      return {
        id: row.dataset.id,
        version: Number(row.dataset.version),
        session_id: (!isAbsent && ch) ? Number(ch) : null,
        unavailable: isAbsent,
        absence_reason: reason(row)
      };
    });

    if (!assignments.length) return;

    saving = true;
    saveButton.disabled = true;
    if (status) {
      status.textContent = "Kaydediliyor, lütfen bekleyiniz…";
      status.style.color = "#127f83";
    }

    try {
      await postJSON("/api/assignments", {
        department_id: Number(roster.dataset.deptId),
        assignments: assignments
      });

      saved = true;
      if (status) {
        status.textContent = "✓ Seçimleriniz başarıyla kaydedildi!";
        status.style.color = "#27ae60";
      }

      // Sayfayı yenileyerek yeni durum ve sayaçları göster
      setTimeout(() => {
        window.location.reload();
      }, 700);

    } catch (error) {
      saving = false;
      saveButton.disabled = false;
      if (status) {
        status.textContent = `Hata: ${error.message}`;
        status.style.color = "#c0392b";
      }
    }
  });
}
