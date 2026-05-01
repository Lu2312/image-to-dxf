// arqgen.js — shared utilities

/**
 * POST JSON to an endpoint and return the parsed response.
 * For binary responses (DXF, PDF, XLSX) pass binary=true.
 */
async function apiPost(endpoint, body, binary = false) {
  const res = await fetch(endpoint, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(JSON.stringify(err.detail ?? err));
  }
  return binary ? res.blob() : res.json();
}

/** Trigger a file download from a Blob */
function downloadBlob(blob, filename) {
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  a.click();
  URL.revokeObjectURL(url);
}

/** Show / hide a spinner element */
function setLoading(btnEl, spinnerEl, loading) {
  btnEl.disabled = loading;
  spinnerEl.style.display = loading ? "inline-block" : "none";
}

/** Render an NTC report into a container element */
function renderNTC(container, report) {
  if (!report) { container.innerHTML = ""; return; }
  const { valid, errors, warnings } = report;
  let html = "";
  if (valid && warnings.length === 0) {
    html = `<div class="ntc-box ok"><span class="ntc-ok">✔ Cumple NTC-RCDF sin observaciones.</span></div>`;
  }
  if (warnings.length > 0) {
    html += `<div class="ntc-box warn"><span class="ntc-warn">⚠ Advertencias NTC:</span><ul>`;
    warnings.forEach(w => { html += `<li>${w}</li>`; });
    html += `</ul></div>`;
  }
  if (errors.length > 0) {
    html += `<div class="ntc-box error"><span class="ntc-error">✖ Errores NTC:</span><ul>`;
    errors.forEach(e => { html += `<li>${e}</li>`; });
    html += `</ul></div>`;
  }
  container.innerHTML = html;
}

/** Render a catalog array as an HTML table */
function renderCatalog(container, rows) {
  if (!rows || rows.length === 0) { container.innerHTML = "<p style='color:var(--muted)'>Sin datos.</p>"; return; }
  const cols = Object.keys(rows[0]);
  let html = `<table class="catalog-table"><thead><tr>`;
  cols.forEach(c => { html += `<th>${c}</th>`; });
  html += `</tr></thead><tbody>`;
  rows.forEach(r => {
    html += "<tr>";
    cols.forEach(c => { html += `<td>${r[c]}</td>`; });
    html += "</tr>";
  });
  html += "</tbody></table>";
  container.innerHTML = html;
}

/** Tab switcher */
function initTabs(containerEl) {
  const btns = containerEl.querySelectorAll(".tab-btn");
  const contents = containerEl.querySelectorAll(".tab-content");
  btns.forEach(btn => {
    btn.addEventListener("click", () => {
      btns.forEach(b => b.classList.remove("active"));
      contents.forEach(c => c.classList.remove("active"));
      btn.classList.add("active");
      containerEl.querySelector(`#${btn.dataset.tab}`).classList.add("active");
    });
  });
}
