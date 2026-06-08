/* CRM H2EAUX SERVICES — Application */

const BRAND = {
  gold: "#d4af37",
  goldLight: "#f5d76e",
  green: "#2ecc71",
  greenBright: "#3dff9a",
  muted: "#8a8578",
  danger: "#e74c3c",
  pie: ["#d4af37", "#2ecc71", "#b794f6", "#5eead4"],
};

const PAGE_TITLES = {
  dashboard: "Tableau de bord",
  table: "Relevés détaillés",
  ensembles: "Ensembles immobiliers",
  km: "Kilomètres & carburant",
  guide: "Guide & tutoriel",
};

const COLS = [
  { key: "date_releve", label: "Date", fmt: v => (v || "").slice(0, 16).replace("T", " ") },
  { key: "statut_label", label: "Statut", badge: "statut" },
  { key: "categorie_label", label: "Type", badge: "cat" },
  { key: "code_ensemble", label: "Code" },
  { key: "nom_ensemble", label: "Ensemble" },
  { key: "ville", label: "Ville" },
  { key: "fluide", label: "Fluide" },
  { key: "index_val", label: "Index" },
  { key: "montant", label: "Montant €", fmt: v => v != null ? Number(v).toFixed(2) : "0.00" },
  { key: "lib_obs", label: "Observation" },
];

let allRows = [];
let charts = {};
let selectedEnsemble = null;

function filterParams() {
  const cat = document.getElementById("filterCategorie").value;
  const date = document.getElementById("filterDate").value;
  const code = document.getElementById("filterCode").value;
  const p = new URLSearchParams();
  if (cat) p.set("categorie", cat);
  if (date) p.set("date", date);
  if (code) p.set("code", code);
  const s = p.toString();
  return s ? "?" + s : "";
}

function showStatus(msg, ok = true) {
  const el = document.getElementById("status");
  el.textContent = msg;
  el.className = "status show " + (ok ? "ok" : "err");
  setTimeout(() => el.classList.remove("show"), 7000);
}

function catBadgeClass(row) {
  const c = row.categorie_facture || row.categorie || "";
  if (c === "VISUEL_LOGEMENT") return "vl";
  if (c === "VISUEL_GPA") return "vg";
  if (c === "RADIO_DISTANCE") return "rd";
  if (c === "COMPTEUR_GENERAL") return "cg";
  return "";
}

function fmtEuro(n) {
  return Number(n || 0).toLocaleString("fr-FR", { minimumFractionDigits: 2, maximumFractionDigits: 2 }) + " €";
}

async function loadFilterMeta() {
  const meta = await fetch("/api/filters").then(r => r.json());
  const dateSel = document.getElementById("filterDate");
  const codeSel = document.getElementById("filterCode");
  const curDate = dateSel.value;
  const curCode = codeSel.value;
  dateSel.innerHTML = '<option value="">Toutes dates</option>' +
    (meta.dates || []).map(d => `<option value="${d}">${d}</option>`).join("");
  codeSel.innerHTML = '<option value="">Tous les ensembles</option>' +
    (meta.codes || []).map(c =>
      `<option value="${c.code_ensemble}">${c.code_ensemble} — ${c.nom_ensemble || c.ville || ""}</option>`
    ).join("");
  if (curDate) dateSel.value = curDate;
  if (curCode) codeSel.value = curCode;
}

async function loadAll() {
  const qs = filterParams();
  const [stats, km, rows, totals, ensembles] = await Promise.all([
    fetch("/api/stats" + qs).then(r => r.json()),
    fetch("/api/km" + qs).then(r => r.json()),
    fetch("/api/releves" + qs + (qs ? "&" : "?") + "limit=5000").then(r => r.json()),
    fetch("/api/totals" + qs).then(r => r.json()),
    fetch("/api/ensembles").then(r => r.json()),
  ]);
  allRows = rows;
  renderHeroKpi(stats, totals);
  renderTotalsBar(totals);
  renderDashboard(stats, km);
  renderTable(rows);
  renderKm(km, stats);
  renderTarifs(stats.tarifs || {});
  renderEnsembles(ensembles);
  renderAlert(totals.sans_pat_ok);
  const note = document.getElementById("regleNote");
  if (note && stats.gpa_estime_count) {
    note.textContent = `${stats.gpa_estime_count} relevés facturés en GPA estimé à 0,70 € HT (PAT absent en base)`;
    note.style.display = "block";
  } else if (note) note.style.display = "none";
}

function renderHeroKpi(s, t) {
  const g = t.global || {};
  const el = document.getElementById("heroKpi");
  el.innerHTML = `
    <div class="hero-main">
      <div class="kpi-label">Chiffre d'affaires TTC</div>
      <div class="kpi-value">${fmtEuro(s.ca_ttc)}</div>
      <div class="kpi-sub">HT ${fmtEuro(s.ca_total)} · TVA 20 % ${fmtEuro(s.ca_tva)}</div>
    </div>
    <div class="hero-mini green">
      <div class="kpi-label">Relevés facturables</div>
      <div class="kpi-value">${s.total_releves_ok || 0}</div>
    </div>
    <div class="hero-mini gold">
      <div class="kpi-label">Total HT filtré</div>
      <div class="kpi-value">${fmtEuro(g.montant_ht)}</div>
    </div>
    <div class="hero-mini red">
      <div class="kpi-label">Non relevés</div>
      <div class="kpi-value">${s.total_non_releves || 0}</div>
    </div>`;
}

function renderAlert(sansPat) {
  const el = document.getElementById("alertSansPat");
  if (sansPat > 0) {
    el.textContent = `${sansPat} relevé(s) OK sans PAT en base — importez le PAT avant les CST pour un matching optimal.`;
    el.style.display = "flex";
  } else el.style.display = "none";
}

function renderTotalsBar(t) {
  const el = document.getElementById("totalsBar");
  const g = t.global || {};
  let html = `<div class="total-block global">
    <span class="label">Total global</span>
    <span class="value">${g.count || 0} relevés · ${fmtEuro(g.montant_ht)} HT</span>
    <span class="sub">TVA 20 % : ${fmtEuro(g.tva)} · TTC : ${fmtEuro(g.montant_ttc)}</span>
  </div>`;
  if (t.filtre_categorie) {
    const f = t.filtre_categorie;
    html += `<div class="total-block active">
      <span class="label">${t.filtre_categorie_label}</span>
      <span class="value">${f.count || 0} relevés · ${fmtEuro(f.montant_ht)} HT</span>
    </div>`;
  }
  el.innerHTML = html;
}

function renderTarifs(t) {
  document.getElementById("tarifs").innerHTML = Object.entries(t).map(([k, v]) =>
    `<span class="tarif-chip"><strong>${k}</strong> ${v.toFixed(2)} € HT</span>`
  ).join("");
}

function renderDashboard(s, km) {
  document.getElementById("cards").innerHTML = [
    { l: "CA HT", v: fmtEuro(s.ca_total), c: "ca" },
    { l: "TVA 20 %", v: fmtEuro(s.ca_tva), c: "gold" },
    { l: "Total TTC", v: fmtEuro(s.ca_ttc), c: "gold" },
    { l: "Relevés OK", v: s.total_releves_ok || 0, c: "" },
    { l: "Non relevés", v: s.total_non_releves || 0, c: "ko" },
    { l: "Km parcourus", v: (km.km_total || 0) + " km", c: "" },
    { l: "Carburant", v: fmtEuro(km.carburant?.cout_euros), c: "ko" },
    { l: "Marge nette", v: fmtEuro(km.marge_apres_carburant), c: "ca" },
  ].map(x => `<div class="card ${x.c}"><h3>${x.l}</h3><div class="val">${x.v}</div></div>`).join("");

  const pc = (s.totals && s.totals.par_categorie) || {};
  document.getElementById("catTotals").innerHTML = Object.values(pc).map(c =>
    `<div class="cat-card"><strong>${c.label}</strong><div>${c.count} relevés</div><div class="amt">${fmtEuro(c.montant_ht)} HT</div></div>`
  ).join("");

  renderCharts(s);
}

function chartDefaults() {
  return {
    responsive: true,
    plugins: {
      legend: { labels: { color: BRAND.muted, font: { family: "'Outfit', sans-serif", size: 11 } } },
    },
    scales: {
      x: { ticks: { color: BRAND.muted }, grid: { color: "rgba(212,175,55,0.06)" } },
      y: { ticks: { color: BRAND.muted }, grid: { color: "rgba(212,175,55,0.06)" } },
    },
  };
}

function renderCharts(s) {
  const ok = s.releves_ok_par_type || {};
  const ko = s.releves_non_ok_par_type || {};
  const labels = [...new Set([...Object.keys(ok), ...Object.keys(ko)])];
  if (charts.bar) charts.bar.destroy();
  if (charts.pie) charts.pie.destroy();

  charts.bar = new Chart(document.getElementById("chartBar"), {
    type: "bar",
    data: {
      labels,
      datasets: [
        { label: "Relevé OK", data: labels.map(l => ok[l] || 0), backgroundColor: BRAND.green, borderRadius: 6 },
        { label: "Non relevé", data: labels.map(l => ko[l] || 0), backgroundColor: BRAND.danger, borderRadius: 6 },
      ],
    },
    options: chartDefaults(),
  });

  const pc = (s.totals && s.totals.par_categorie) || {};
  charts.pie = new Chart(document.getElementById("chartPie"), {
    type: "doughnut",
    data: {
      labels: Object.values(pc).map(c => c.label),
      datasets: [{
        data: Object.values(pc).map(c => c.montant_ht),
        backgroundColor: BRAND.pie,
        borderColor: "#0f0f0f",
        borderWidth: 3,
      }],
    },
    options: {
      responsive: true,
      cutout: "62%",
      plugins: {
        legend: { labels: { color: BRAND.muted, font: { family: "'Outfit', sans-serif", size: 11 } } },
      },
    },
  });
}

function renderKm(km, stats) {
  document.getElementById("kmSegments").innerHTML = (km.segments || []).map(s =>
    `<tr><td>${(s.de_heure || "").slice(0, 16)}</td><td>${s.de} ${s.de_nom || ""}</td><td>${s.vers} ${s.vers_nom || ""}</td><td><strong style="color:var(--gold-light)">${s.km} km</strong></td></tr>`
  ).join("") || "<tr><td colspan='4' style='color:var(--text-muted)'>Pas de données GPS TRN pour cette date</td></tr>";

  document.getElementById("kmSummary").innerHTML =
    `<p style="font-size:1.1rem;margin-bottom:0.5rem"><strong style="color:var(--gold-light)">${km.km_total || 0} km</strong> parcourus entre <strong>${km.nb_sites || 0}</strong> sites</p>` +
    `<p>Carburant estimé : <strong style="color:var(--green)">${fmtEuro(km.carburant?.cout_euros)}</strong> · ` +
    `CA TTC <strong style="color:var(--gold-light)">${fmtEuro(stats.ca_ttc)}</strong> · ` +
    `Marge nette <strong style="color:var(--green)">${fmtEuro(km.marge_apres_carburant)}</strong></p>`;
}

function renderTable(rows) {
  document.getElementById("rowCount").textContent = rows.length;
  document.getElementById("tableHead").innerHTML = "<tr>" + COLS.map(c => `<th>${c.label}</th>`).join("") + "</tr>";
  document.getElementById("tableBody").innerHTML = rows.map(r =>
    "<tr>" + COLS.map(c => {
      let v = r[c.key];
      if (c.fmt) v = c.fmt(v);
      if (c.badge === "statut") {
        const cls = r.statut_releve === "RELEVE_OK" ? "ok" : "ko";
        return `<td><span class="badge ${cls}">${v || "—"}</span></td>`;
      }
      if (c.badge === "cat") {
        return `<td><span class="badge ${catBadgeClass(r)}">${v || "—"}</span></td>`;
      }
      if (c.key === "code_ensemble") return `<td><strong style="color:var(--gold-light)">${v ?? "—"}</strong></td>`;
      if (c.key === "montant") return `<td><strong style="color:var(--green)">${v}</strong></td>`;
      return `<td>${v ?? "—"}</td>`;
    }).join("") + "</tr>"
  ).join("") || `<tr><td colspan="${COLS.length}" style="color:var(--text-muted);padding:2rem;text-align:center">Aucune donnée — importez PAT puis CST via le menu latéral</td></tr>`;
}

function renderEnsembles(list) {
  const tbody = document.getElementById("ensembleList");
  tbody.innerHTML = list.map(e =>
    `<tr class="ens-row${selectedEnsemble === e.code_ensemble ? " selected" : ""}" data-code="${e.code_ensemble}">
      <td><strong>${e.code_ensemble}</strong></td>
      <td>${e.nom_ensemble || "—"}</td>
      <td>${e.ville || "—"}</td>
      <td>${e.nb_releves_ok || 0}</td>
      <td style="color:var(--green)">${fmtEuro(e.ca_ht)}</td>
    </tr>`
  ).join("") || "<tr><td colspan='5' style='color:var(--text-muted)'>Importez PAT/TRN pour créer les fiches</td></tr>";

  tbody.querySelectorAll(".ens-row").forEach(row => {
    row.onclick = () => selectEnsemble(row.dataset.code);
  });
}

async function selectEnsemble(code) {
  selectedEnsemble = code;
  const ens = await fetch(`/api/ensembles/${encodeURIComponent(code)}`).then(r => r.json());
  document.getElementById("ensembleForm").style.display = "block";
  document.querySelector("#ensembleEditor .hint").style.display = "none";
  document.getElementById("ensCode").value = code;
  document.getElementById("ensTitle").textContent = `${code} — ${ens.nom_ensemble || ""} · ${ens.ville || ""}`;
  document.getElementById("ensCodeAcces").value = ens.code_acces || "";
  document.getElementById("ensContacts").value = ens.contacts || "";
  document.getElementById("ensCommentaires").value = ens.commentaires || "";
  renderEnsembles(await fetch("/api/ensembles").then(r => r.json()));
}

function setupNav() {
  document.querySelectorAll(".nav-item").forEach(item => {
    item.onclick = () => {
      const panel = item.dataset.panel;
      document.querySelectorAll(".nav-item").forEach(x => x.classList.remove("active"));
      document.querySelectorAll(".panel").forEach(x => x.classList.remove("active"));
      item.classList.add("active");
      document.getElementById("panel-" + panel).classList.add("active");
      document.getElementById("pageTitle").textContent = PAGE_TITLES[panel] || panel;
      document.getElementById("sidebar").classList.remove("open");

      const tools = document.getElementById("contentTools");
      const subtitle = document.querySelector(".topbar-title p");
      if (panel === "guide") {
        tools.classList.add("hidden");
        if (subtitle) subtitle.textContent = "Documentation complète — workflow PAT / CST et utilisation du CRM";
      } else {
        tools.classList.remove("hidden");
        if (subtitle) subtitle.textContent = "Index saisi = relevé facturable · TVA 20 % · Matching PAT / CST";
      }
    };
  });

  document.querySelectorAll(".guide-toc a").forEach(link => {
    link.onclick = e => {
      e.preventDefault();
      const id = link.getAttribute("href").slice(1);
      const el = document.getElementById(id);
      if (el) el.scrollIntoView({ behavior: "smooth", block: "start" });
    };
  });
}

async function doImport(url, label) {
  showStatus(`${label} en cours…`);
  const res = await fetch(url, { method: "POST" }).then(r => r.json());
  if (res.ok) {
    let msg = `${label} terminé avec succès`;
    if (res.stats.releves != null) msg += ` — ${res.stats.releves} relevés`;
    if (res.stats.sans_pat) msg += ` (${res.stats.sans_pat} sans PAT)`;
    if (res.stats.pdcs) msg += ` — ${res.stats.pdcs} compteurs`;
    showStatus(msg, !res.stats.sans_pat);
    await loadFilterMeta();
    loadAll();
  } else showStatus(res.error || "Erreur d'import", false);
}

document.getElementById("btnImportPat").onclick = () => doImport("/api/import/pat", "Import PAT");
document.getElementById("btnImportCst").onclick = () => doImport("/api/import/cst", "Import CST");
document.getElementById("btnImportAll").onclick = () => doImport("/api/import", "Import complet");

["filterCategorie", "filterDate", "filterCode"].forEach(id => {
  document.getElementById(id).onchange = () => loadAll();
});

document.getElementById("btnReset").onclick = () => {
  document.getElementById("filterCategorie").value = "";
  document.getElementById("filterDate").value = "";
  document.getElementById("filterCode").value = "";
  loadAll();
};

document.getElementById("btnExport").onclick = () => {
  window.location.href = "/api/export/csv" + filterParams();
};

document.getElementById("btnShare").onclick = async () => {
  const res = await fetch("/api/share" + filterParams(), { method: "POST" }).then(r => r.json());
  document.getElementById("shareLink").value = location.origin + "/share/" + res.token;
  document.getElementById("modalShare").classList.add("show");
};

document.getElementById("btnCopyLink").onclick = () => {
  const inp = document.getElementById("shareLink");
  inp.select();
  navigator.clipboard?.writeText(inp.value);
  showStatus("Lien copié dans le presse-papier");
};

document.getElementById("btnEmail").onclick = async () => {
  window.location.href = (await fetch("/api/mailto" + filterParams()).then(r => r.json())).url;
};

document.getElementById("btnSettings").onclick = () => {
  document.getElementById("modalSettings").classList.add("show");
};

document.getElementById("btnSaveSettings").onclick = async () => {
  const fuel = document.getElementById("fuelPrice").value;
  const conso = document.getElementById("fuelConso").value;
  await fetch(`/api/settings?fuel_price_l=${fuel}&consumption_l_100=${conso}`, { method: "POST" });
  document.getElementById("modalSettings").classList.remove("show");
  loadAll();
  showStatus("Paramètres véhicule enregistrés");
};

document.getElementById("ensembleForm").onsubmit = async e => {
  e.preventDefault();
  const code = document.getElementById("ensCode").value;
  await fetch(`/api/ensembles/${encodeURIComponent(code)}`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      code_acces: document.getElementById("ensCodeAcces").value,
      contacts: document.getElementById("ensContacts").value,
      commentaires: document.getElementById("ensCommentaires").value,
    }),
  });
  showStatus(`Fiche ${code} enregistrée`);
};

document.querySelectorAll(".modal-close").forEach(b => {
  b.onclick = () => b.closest(".modal").classList.remove("show");
});

document.getElementById("sidebarToggle").onclick = () => {
  document.getElementById("sidebar").classList.toggle("open");
};

fetch("/api/settings").then(r => r.json()).then(s => {
  document.getElementById("fuelPrice").value = s.fuel_price_l;
  document.getElementById("fuelConso").value = s.consumption_l_100;
});

setupNav();
loadFilterMeta().then(loadAll);
