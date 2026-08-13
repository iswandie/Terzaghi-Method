"use strict";

const $ = (selector, root = document) => root.querySelector(selector);
const $$ = (selector, root = document) => [...root.querySelectorAll(selector)];
const state = { result: null, payload: null };
const SESSION_RESULT_KEY = "terrasettle.analysisResult";

const labels = {
  name: "Layer Name", description: "Soil Description", thickness: "Compressible layer thickness H",
  unitWeight: "Total unit weight γ", saturatedUnitWeight: "Saturated unit weight γsat",
  voidRatio: "Initial void ratio e₀", compressionIndex: "Compression index Cc",
  cv: "Coefficient of consolidation Cv", condition: "Soil condition",
  drainage: "Drainage condition", preconsolidationPressure: "Preconsolidation pressure σ′p",
  recompressionIndex: "Recompression index Cr"
};

function escapeHtml(value) {
  return String(value ?? "").replace(/[&<>'"]/g, character => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", "'": "&#39;", '"': "&quot;"
  }[character]));
}

function value(id) { return $(id).value.trim(); }
function numberOrRaw(id) { const raw = value(id); return raw === "" ? "" : Number(raw); }
function format(number, digits = 2) {
  return Number(number).toLocaleString(undefined, { minimumFractionDigits: digits, maximumFractionDigits: digits });
}
function formatTime(number) {
  if (number >= 1000) return format(number, 0);
  if (number >= 10) return format(number, 1);
  return format(number, 2);
}

function saveAnalysisSession(result, payload) {
  try {
    sessionStorage.setItem(SESSION_RESULT_KEY, JSON.stringify({ result, payload }));
  } catch (error) {
    console.warn("Analysis results could not be saved for this browser session.", error);
  }
}

function restoreAnalysisSession() {
  try {
    const saved = sessionStorage.getItem(SESSION_RESULT_KEY);
    if (!saved) return false;
    const restored = JSON.parse(saved);
    if (!restored?.result?.summary || !restored?.payload?.project) return false;
    state.result = restored.result;
    state.payload = restored.payload;
    renderResults(restored.result, restored.payload);
    return true;
  } catch (error) {
    sessionStorage.removeItem(SESSION_RESULT_KEY);
    console.warn("Saved analysis results could not be restored.", error);
    return false;
  }
}

function navigateToSection(id, updateHash = true) {
  const target = document.getElementById(id);
  if (!target) return;
  target.hidden = false;
  if (updateHash && window.location.hash !== `#${id}`) {
    history.replaceState(null, "", `#${id}`);
  }
  target.scrollIntoView({ behavior: "smooth", block: "start" });
  $$(".sidebar nav a").forEach(link => {
    link.classList.toggle("active", link.getAttribute("href") === `#${id}`);
  });
}

function addLayer(data = {}) {
  const fragment = $("#layer-template").content.cloneNode(true);
  const card = $(".layer-card", fragment);
  Object.entries(data).forEach(([field, fieldValue]) => {
    const input = $(`[data-field="${field}"]`, card);
    if (input) input.value = fieldValue;
  });
  $("#layers-container").append(card);
  bindLayer(card);
  renumberLayers();
  updateUnits();
  updateLayerMode(card);
}

function bindLayer(card) {
  $("[data-field='condition']", card).addEventListener("change", () => updateLayerMode(card));
  $("[data-field='drainage']", card).addEventListener("change", () => updateDrainagePreview(card));
  $("[data-field='thickness']", card).addEventListener("input", () => updateDrainagePreview(card));
  $(".remove-layer", card).addEventListener("click", () => {
    if ($$(".layer-card").length === 1) {
      showAlert("At least one soil layer is required.");
      return;
    }
    card.remove();
    renumberLayers();
  });
  $$(`input, select`, card).forEach(input => input.addEventListener("input", () => clearFieldError(input)));
}

function renumberLayers() {
  $$(".layer-card").forEach((card, index) => {
    $(".layer-index", card).textContent = String(index + 1).padStart(2, "0");
    $("header h3", card).textContent = valueOr($(".layer-name", card).value, `Soil Layer ${index + 1}`);
    $$('[data-field]', card).forEach(input => input.dataset.path = `layers.${index}.${input.dataset.field}`);
    $(".layer-name", card).oninput = () => {
      $("header h3", card).textContent = valueOr($(".layer-name", card).value, `Soil Layer ${index + 1}`);
      clearFieldError($(".layer-name", card));
    };
  });
}

function valueOr(input, fallback) { return String(input || "").trim() || fallback; }

function updateLayerMode(card) {
  const oc = $("[data-field='condition']", card).value === "OC";
  $$(".oc-only", card).forEach(field => {
    field.hidden = !oc;
    const input = $("input", field);
    input.disabled = !oc;
    if (!oc) clearFieldError(input);
  });
}

function updateDrainagePreview(card) {
  const drainage = $("[data-field='drainage']", card).value;
  const rawThickness = Number($("[data-field='thickness']", card).value);
  const unit = $("#unit-length").value;
  let message = "Select drainage to establish Hdr";
  if (drainage && Number.isFinite(rawThickness) && rawThickness > 0) {
    const path = drainage === "single" ? rawThickness : rawThickness / 2;
    message = `Drainage path Hdr = ${format(path, 3)} ${unit} (${drainage})`;
  }
  $(".drainage-preview", card).textContent = message;
}

function updateLoadingMode() {
  const foundation = $("input[name='load-type']:checked").value === "foundation";
  $$(".foundation-only").forEach(field => {
    field.hidden = !foundation;
    $$(`input, select`, field).forEach(input => {
      input.disabled = !foundation;
      if (!foundation) clearFieldError(input);
    });
  });
  $("#load-equation").innerHTML = foundation
    ? "<strong>Δσ<sub>z</sub> = q(BL) / [(B+z)(L+z)]</strong><span>2:1 distribution; z is depth below foundation base.</span>"
    : "<strong>Δσ<sub>z</sub> = q</strong><span>Uniform stress increase at every layer midpoint.</span>";
}

function updateUnits() {
  const length = $("#unit-length").value;
  const stress = $("#unit-stress").value;
  const cv = $("#unit-cv").value.replace("m2", "m²");
  const time = $("#unit-time").value;
  $$('[data-length-unit]').forEach(element => element.textContent = length);
  $$('[data-stress-unit]').forEach(element => element.textContent = stress);
  $$('[data-cv-unit]').forEach(element => element.textContent = cv);
  $$('[data-time-unit]').forEach(element => element.textContent = time);
  $$(".layer-card").forEach(updateDrainagePreview);
}

function collectPayload() {
  const loadType = $("input[name='load-type']:checked").value;
  return {
    project: {
      name: value("#project-name"), id: value("#project-id"), location: value("#project-location"),
      engineer: value("#project-engineer"), date: value("#project-date"), description: value("#project-description")
    },
    units: { length: value("#unit-length"), stress: value("#unit-stress"), cv: value("#unit-cv"), time: value("#unit-time") },
    groundwater: { depth: numberOrRaw("#gwt-depth"), gammaWater: numberOrRaw("#gamma-water") },
    loading: loadType === "uniform"
      ? { type: "uniform", q: numberOrRaw("#load-q") }
      : { type: "foundation", method: value("#load-method"), q: numberOrRaw("#load-q"), width: numberOrRaw("#foundation-width"), length: numberOrRaw("#foundation-length"), embedmentDepth: numberOrRaw("#foundation-depth") },
    analysis: { selectedTime: numberOrRaw("#selected-time"), targetDegree: numberOrRaw("#target-degree") },
    layers: $$(".layer-card").map(card => Object.fromEntries($$('[data-field]', card).map(input => {
      const numeric = input.type === "number";
      return [input.dataset.field, numeric ? (input.value.trim() === "" ? "" : Number(input.value)) : input.value.trim()];
    })))
  };
}

function clearValidation() {
  $$(".field.invalid").forEach(field => field.classList.remove("invalid"));
  $$(".field-error").forEach(error => error.textContent = "");
  $("#form-alert").hidden = true;
}

function clearFieldError(input) {
  const field = input.closest(".field");
  if (!field) return;
  field.classList.remove("invalid");
  const error = $(".field-error", field);
  if (error) error.textContent = "";
}

function setFieldError(input, message) {
  if (!input || input.disabled) return;
  const field = input.closest(".field");
  if (!field) return;
  field.classList.add("invalid");
  $(".field-error", field).textContent = message;
}

function showAlert(message, details = []) {
  const alert = $("#form-alert");
  alert.innerHTML = `<strong>${escapeHtml(message)}</strong>${details.length ? `<ul>${details.map(item => `<li>${escapeHtml(item)}</li>`).join("")}</ul>` : ""}`;
  alert.hidden = false;
}

function required(input, label) {
  if (!input.value.trim()) { setFieldError(input, `${label} is required.`); return false; }
  return true;
}

function positive(input, label, allowZero = false) {
  if (!required(input, label)) return false;
  const parsed = Number(input.value);
  if (!Number.isFinite(parsed)) { setFieldError(input, `${label} must be numeric.`); return false; }
  if (allowZero ? parsed < 0 : parsed <= 0) {
    setFieldError(input, allowZero ? `${label} cannot be negative.` : `${label} must be greater than 0.`);
    return false;
  }
  return true;
}

function clientValidate() {
  clearValidation();
  let valid = required($("#project-name"), "Project Name");
  valid = positive($("#gwt-depth"), "Groundwater table depth", true) && valid;
  valid = positive($("#gamma-water"), "Unit weight of water γw") && valid;
  valid = positive($("#load-q"), "Applied pressure q") && valid;
  valid = positive($("#selected-time"), "Specified consolidation time", true) && valid;
  valid = positive($("#target-degree"), "Target degree of consolidation U") && valid;
  const target = Number($("#target-degree").value);
  if (Number.isFinite(target) && target >= 100) { setFieldError($("#target-degree"), "Target degree of consolidation must be less than 100%."); valid = false; }
  if ($("input[name='load-type']:checked").value === "foundation") {
    valid = required($("#load-method"), "Stress distribution method") && valid;
    valid = positive($("#foundation-width"), "Foundation width B") && valid;
    valid = positive($("#foundation-length"), "Foundation length L") && valid;
    valid = positive($("#foundation-depth"), "Foundation embedment depth Df", true) && valid;
  }
  $$(".layer-card").forEach(card => {
    const get = field => $(`[data-field='${field}']`, card);
    valid = required(get("name"), labels.name) && valid;
    valid = required(get("description"), labels.description) && valid;
    valid = required(get("condition"), labels.condition) && valid;
    valid = positive(get("thickness"), labels.thickness) && valid;
    valid = positive(get("unitWeight"), labels.unitWeight) && valid;
    valid = positive(get("saturatedUnitWeight"), labels.saturatedUnitWeight) && valid;
    valid = positive(get("voidRatio"), labels.voidRatio, true) && valid;
    valid = positive(get("compressionIndex"), labels.compressionIndex) && valid;
    valid = positive(get("cv"), labels.cv) && valid;
    valid = required(get("drainage"), labels.drainage) && valid;
    if (get("condition").value === "OC") {
      valid = positive(get("preconsolidationPressure"), labels.preconsolidationPressure) && valid;
      valid = positive(get("recompressionIndex"), labels.recompressionIndex) && valid;
      const cc = Number(get("compressionIndex").value), cr = Number(get("recompressionIndex").value);
      if (Number.isFinite(cc) && Number.isFinite(cr) && cc <= cr) {
        setFieldError(get("compressionIndex"), "Compression index Cc must be greater than recompression index Cr for OC soil.");
        valid = false;
      }
    }
  });
  if (!valid) {
    showAlert("Calculation stopped. Correct all mandatory engineering inputs before running the analysis.");
    const first = $(".field.invalid");
    if (first) first.scrollIntoView({ behavior: "smooth", block: "center" });
  }
  return valid;
}

function applyServerErrors(errors) {
  const unmapped = [];
  Object.entries(errors || {}).forEach(([path, message]) => {
    const input = document.querySelector(`[data-path="${CSS.escape(path)}"]`);
    if (input) setFieldError(input, message); else unmapped.push(message);
  });
  showAlert("The engineering engine rejected the analysis.", unmapped.length ? unmapped : Object.values(errors || {}));
  const first = $(".field.invalid");
  if (first) first.scrollIntoView({ behavior: "smooth", block: "center" });
}

async function runAnalysis(event) {
  event.preventDefault();
  if (!clientValidate()) return;
  const submitters = $$('[type="submit"]');
  submitters.forEach(button => { button.disabled = true; button.dataset.label = button.textContent; button.textContent = "Calculating…"; });
  const payload = collectPayload();
  try {
    const response = await fetch("/api/analyze", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(payload) });
    const result = await response.json();
    if (!response.ok) { applyServerErrors(result.errors || { analysis: result.message }); return; }
    state.result = result; state.payload = payload;
    renderResults(result, payload);
    saveAnalysisSession(result, payload);
    navigateToSection("results");
  } catch (error) {
    showAlert("Unable to contact the calculation engine. Check the deployment and try again.");
  } finally {
    submitters.forEach(button => { button.disabled = false; button.textContent = button.dataset.label; });
  }
}

function metric(label, valueText, note, featured = false) {
  return `<article class="metric${featured ? " featured" : ""}"><small>${escapeHtml(label)}</small><strong>${escapeHtml(valueText)}</strong><span>${escapeHtml(note)}</span></article>`;
}

function renderResults(result, payload) {
  $("#results").hidden = false; $("#calculation-details").hidden = false; $("#report").hidden = false;
  $$(".print-action").forEach(button => button.disabled = false);
  $("#result-project").textContent = [payload.project.name, payload.project.id, payload.project.location].filter(Boolean).join("  ·  ");
  const summary = result.summary, first = result.layers[0];
  $("#key-results").innerHTML = [
    metric("Initial effective stress", result.layers.length === 1 ? `${format(first.initialEffectiveStressKPa)} kPa` : `${format(Math.min(...result.layers.map(x => x.initialEffectiveStressKPa)))}–${format(Math.max(...result.layers.map(x => x.initialEffectiveStressKPa)))} kPa`, result.layers.length === 1 ? "At layer midpoint" : "Layer midpoint range"),
    metric("Stress increase", result.layers.length === 1 ? `${format(first.stressIncreaseKPa)} kPa` : `${format(Math.min(...result.layers.map(x => x.stressIncreaseKPa)))}–${format(Math.max(...result.layers.map(x => x.stressIncreaseKPa)))} kPa`, payload.loading.type === "uniform" ? "Uniform surcharge" : "2:1 distribution"),
    metric("Final effective stress", result.layers.length === 1 ? `${format(first.finalEffectiveStressKPa)} kPa` : `${format(Math.min(...result.layers.map(x => x.finalEffectiveStressKPa)))}–${format(Math.max(...result.layers.map(x => x.finalEffectiveStressKPa)))} kPa`, "σ′f = σ′0 + Δσz"),
    metric("Primary consolidation", `${format(summary.totalPrimarySettlementMm, 1)} mm`, "Σ layer primary settlement", true),
    metric("Degree at selected time", `${format(summary.selectedDegree * 100, 1)}%`, `At ${formatTime(summary.selectedTimeDisplay)} ${result.units.time}`),
    metric("Settlement at selected time", `${format(summary.selectedSettlementMm, 1)} mm`, "St = U × Sc"),
    metric("Time to U50", `${formatTime(summary.timesDisplay["50"])} ${result.units.time}`, "Settlement-weighted multilayer response"),
    metric("Time to U90", `${formatTime(summary.timesDisplay["90"])} ${result.units.time}`, "Settlement-weighted multilayer response"),
    metric("Time to U95", `${formatTime(summary.timesDisplay["95"])} ${result.units.time}`, "Settlement-weighted multilayer response"),
    metric(`Time to target U${format(summary.targetDegree * 100, 0)}`, `${formatTime(summary.targetTimeDisplay)} ${result.units.time}`, "Specified target"),
    metric("Immediate settlement", "Not included", "Not calculated in Version 1"),
    metric("Secondary settlement", "Not included", "Not calculated in Version 1")
  ].join("");
  renderWarnings(result.warnings);
  renderLayerTable(result.layers);
  renderTimeTable(result.timeSeries);
  renderDetails(result.calculationDetails);
  renderAssumptions(result.assumptions);
  drawChart($("#settlement-chart"), result.timeSeries, "settlementMm", "Settlement (mm)", "#176b4d", true, result.units.time);
  drawChart($("#degree-chart"), result.timeSeries.map(point => ({...point, degreePercent: point.degree * 100})), "degreePercent", "Degree U (%)", "#d69a2d", false, result.units.time);
  renderReport(result, payload);
}

function renderWarnings(warnings) {
  const container = $("#warnings");
  if (!warnings.length) { container.innerHTML = ""; return; }
  container.innerHTML = `<div class="alert warning"><strong>Engineering warnings</strong><ul>${warnings.map(warning => `<li>${escapeHtml(warning)}</li>`).join("")}</ul></div>`;
}

function renderLayerTable(layers) {
  $("#layer-results-body").innerHTML = layers.map(layer => `<tr>
    <td><strong>${escapeHtml(layer.name)}</strong><br><span class="condition-tag">${layer.condition} · ${layer.drainage}</span></td>
    <td>${format(layer.midDepthM, 3)}</td><td>${format(layer.totalStressKPa)}</td><td>${format(layer.porePressureKPa)}</td>
    <td><strong>${format(layer.initialEffectiveStressKPa)}</strong></td><td>${format(layer.stressIncreaseKPa)}</td><td>${format(layer.finalEffectiveStressKPa)}</td>
    <td>${format(layer.recompressionSettlementM * 1000, 2)}</td><td>${format(layer.virginSettlementM * 1000, 2)}</td><td><strong>${format(layer.primarySettlementM * 1000, 2)}</strong></td>
  </tr>`).join("");
}

function renderTimeTable(series) {
  $("#time-results-body").innerHTML = series.map(point => `<tr><td>${formatTime(point.timeDisplay)}</td><td>${escapeHtml(point.timeUnit)}</td><td>${format(point.tvMin, 4)}${Math.abs(point.tvMax - point.tvMin) > 1e-9 ? `–${format(point.tvMax, 4)}` : ""}</td><td>${format(point.degree * 100, 2)}%</td><td>${format(point.settlementMm, 2)} mm</td></tr>`).join("");
}

function renderDetails(details) {
  let category = "";
  $("#details-list").innerHTML = details.map(detail => {
    const heading = detail.category !== category ? `<h3 class="detail-category">${escapeHtml(detail.category)}</h3>` : "";
    category = detail.category;
    return `${heading}<article class="detail-row"><div><small>Parameter · ${escapeHtml(detail.layer)}</small><strong>${escapeHtml(detail.parameter)}</strong></div><div><small>Formula</small><code>${escapeHtml(detail.formula)}</code></div><div><small>Substitution</small><code>${escapeHtml(detail.substitution)}</code></div><div class="detail-result"><small>Result</small><strong>${format(detail.result, detail.unit === "%" ? 2 : 3)} ${escapeHtml(detail.unit)}</strong></div></article>`;
  }).join("");
}

function renderAssumptions(assumptions) {
  $("#assumptions-list").innerHTML = assumptions.map(item => `<li>${escapeHtml(item)}</li>`).join("");
}

function drawChart(canvas, series, key, yLabel, color, invert, timeUnit) {
  const ratio = window.devicePixelRatio || 1;
  const cssWidth = canvas.parentElement.clientWidth - 60;
  const width = Math.max(420, cssWidth), height = 300;
  canvas.style.width = `${width}px`; canvas.style.height = `${height}px`;
  canvas.width = width * ratio; canvas.height = height * ratio;
  const context = canvas.getContext("2d"); context.scale(ratio, ratio);
  const pad = { left: 64, right: 20, top: 20, bottom: 48 };
  const plotW = width - pad.left - pad.right, plotH = height - pad.top - pad.bottom;
  const maxX = Math.max(...series.map(item => item.timeDisplay), 1);
  const maxData = Math.max(...series.map(item => item[key]), 1);
  const maxY = key === "degreePercent" ? 100 : maxData * 1.08;
  context.font = "10px Segoe UI"; context.fillStyle = "#708079"; context.strokeStyle = "#dde4e0"; context.lineWidth = 1;
  for (let i = 0; i <= 5; i++) {
    const y = pad.top + plotH * i / 5;
    context.beginPath(); context.moveTo(pad.left, y); context.lineTo(width - pad.right, y); context.stroke();
    const valueY = invert ? maxY * i / 5 : maxY * (1 - i / 5);
    context.textAlign = "right"; context.fillText(format(valueY, key === "degreePercent" ? 0 : 1), pad.left - 10, y + 3);
    const x = pad.left + plotW * i / 5;
    context.textAlign = "center"; context.fillText(formatTime(maxX * i / 5), x, height - pad.bottom + 19);
  }
  context.save(); context.translate(15, pad.top + plotH / 2); context.rotate(-Math.PI / 2); context.textAlign = "center"; context.fillText(yLabel, 0, 0); context.restore();
  context.textAlign = "center"; context.fillText(`Time (${timeUnit})`, pad.left + plotW / 2, height - 8);
  const pointXY = item => ({ x: pad.left + (item.timeDisplay / maxX) * plotW, y: invert ? pad.top + (item[key] / maxY) * plotH : pad.top + (1 - item[key] / maxY) * plotH });
  context.beginPath(); series.forEach((item, index) => { const point = pointXY(item); index ? context.lineTo(point.x, point.y) : context.moveTo(point.x, point.y); });
  context.strokeStyle = color; context.lineWidth = 2.5; context.stroke();
  context.lineTo(pointXY(series.at(-1)).x, invert ? pad.top : pad.top + plotH); context.lineTo(pad.left, invert ? pad.top : pad.top + plotH); context.closePath();
  const gradient = context.createLinearGradient(0, pad.top, 0, pad.top + plotH); gradient.addColorStop(0, `${color}18`); gradient.addColorStop(1, `${color}02`); context.fillStyle = gradient; context.fill();
}

function reportValue(label, content) { return `<div class="report-value"><small>${escapeHtml(label)}</small><strong>${escapeHtml(valueOr(content, "Not provided"))}</strong></div>`; }
function reportTable(headers, rows) {
  return `<div class="table-wrap"><table><thead><tr>${headers.map(header => `<th>${escapeHtml(header)}</th>`).join("")}</tr></thead><tbody>${rows.map(row => `<tr>${row.map(cell => `<td>${escapeHtml(cell)}</td>`).join("")}</tr>`).join("")}</tbody></table></div>`;
}

function renderReport(result, payload) {
  $("#report-meta").innerHTML = `${escapeHtml(payload.project.id || "No project ID")}<br>${escapeHtml(payload.project.date || "Undated")}`;
  const layerRows = payload.layers.map((layer, index) => [layer.name, layer.description, layer.condition, `${layer.thickness} ${payload.units.length}`, `${layer.unitWeight} / ${layer.saturatedUnitWeight} kN/m³`, String(layer.voidRatio), String(layer.compressionIndex), String(layer.cv), layer.drainage]);
  const resultRows = result.layers.map(layer => [layer.name, format(layer.midDepthM, 3), format(layer.totalStressKPa), format(layer.porePressureKPa), format(layer.initialEffectiveStressKPa), format(layer.stressIncreaseKPa), format(layer.finalEffectiveStressKPa), format(layer.primarySettlementM * 1000, 2)]);
  const loadDescription = payload.loading.type === "uniform"
    ? `Uniform surcharge, q = ${payload.loading.q} ${payload.units.stress}`
    : `Rectangular foundation, B × L = ${payload.loading.width} × ${payload.loading.length} ${payload.units.length}, q = ${payload.loading.q} ${payload.units.stress}, Df = ${payload.loading.embedmentDepth} ${payload.units.length}; 2:1 method`;
  const detailRows = result.calculationDetails.map(detail => [detail.layer, detail.parameter, detail.formula, detail.substitution, `${format(detail.result, 3)} ${detail.unit}`]);
  const warningList = result.warnings.length ? result.warnings : ["No calculation-specific warnings generated."];
  $("#report-content").innerHTML = `
    <section class="report-section"><h3>1. Project Information</h3><div class="report-grid">${reportValue("Project Name", payload.project.name)}${reportValue("Project ID", payload.project.id)}${reportValue("Location", payload.project.location)}${reportValue("Engineer / Designer", payload.project.engineer)}${reportValue("Date", payload.project.date)}${reportValue("Description", payload.project.description)}</div></section>
    <section class="report-section"><h3>2. Soil Profile</h3>${reportTable(["Layer","Description","State","H","γ / γsat","e₀","Cc","Cv " + payload.units.cv,"Drainage"], layerRows)}</section>
    <section class="report-section"><h3>3. Groundwater & Loading Conditions</h3><div class="report-grid">${reportValue("Groundwater depth", `${payload.groundwater.depth} ${payload.units.length}`)}${reportValue("Unit weight of water", `${payload.groundwater.gammaWater} kN/m³`)}${reportValue("Loading condition", loadDescription)}</div></section>
    <section class="report-section"><h3>4. Calculation Assumptions</h3><ul>${result.assumptions.map(item => `<li>${escapeHtml(item)}</li>`).join("")}</ul></section>
    <section class="report-section"><h3>5–8. Effective Stresses, Stress Increments & Settlement</h3>${reportTable(["Layer","z mid (m)","σv₀ (kPa)","u₀ (kPa)","σ′₀ (kPa)","Δσz (kPa)","σ′f (kPa)","Sc (mm)"], resultRows)}</section>
    <section class="report-section"><h3>9. Consolidation Calculations</h3><div class="report-grid">${reportValue("Selected time", `${formatTime(result.summary.selectedTimeDisplay)} ${result.units.time}`)}${reportValue("Average U", `${format(result.summary.selectedDegree * 100, 2)}%`)}${reportValue("Settlement at time", `${format(result.summary.selectedSettlementMm, 2)} mm`)}${reportValue("Time to U50", `${formatTime(result.summary.timesDisplay["50"])} ${result.units.time}`)}${reportValue("Time to U90", `${formatTime(result.summary.timesDisplay["90"])} ${result.units.time}`)}${reportValue("Time to U95", `${formatTime(result.summary.timesDisplay["95"])} ${result.units.time}`)}</div></section>
    <section class="report-section"><h3>10–11. Layer Results & Total Settlement</h3><div class="report-grid">${reportValue("Immediate settlement", "Not included in this analysis")}${reportValue("Primary consolidation", `${format(result.summary.totalPrimarySettlementMm, 2)} mm`)}${reportValue("Secondary settlement", "Not included in this analysis")}${reportValue("Total included settlement", `${format(result.summary.totalSettlementMm, 2)} mm`)}</div></section>
    <section class="report-section"><h3>12. Settlement–Time Graph</h3><img alt="Settlement time graph" src="${$("#settlement-chart").toDataURL("image/png")}" style="display:block;max-width:720px;width:100%;margin:auto"></section>
    <section class="report-section"><h3>13. Calculation Details</h3>${reportTable(["Layer","Parameter","Formula","Substitution","Result"], detailRows)}</section>
    <section class="report-section"><h3>14. Warnings</h3><ul>${warningList.map(item => `<li>${escapeHtml(item)}</li>`).join("")}</ul></section>
    <section class="report-section"><h3>15. Assumptions & Limitations</h3><p><strong>Professional review required.</strong> This report is based on Terzaghi one-dimensional consolidation theory and requires engineering judgment. It does not establish suitability for construction.</p></section>`;
}

function initialize() {
  $("#project-date").value = new Date().toISOString().slice(0, 10);
  addLayer();
  $("#add-layer").addEventListener("click", () => addLayer());
  $("#analysis-form").addEventListener("submit", runAnalysis);
  $$(`input[name="load-type"]`).forEach(input => input.addEventListener("change", updateLoadingMode));
  ["#unit-length", "#unit-stress", "#unit-cv", "#unit-time"].forEach(id => $(id).addEventListener("change", updateUnits));
  $$(`input, select, textarea`, $("#analysis-form")).forEach(input => input.addEventListener("input", () => clearFieldError(input)));
  $$(".print-action").forEach(button => button.addEventListener("click", () => window.print()));
  $$(".sidebar nav a, .brand").forEach(link => link.addEventListener("click", event => {
    const id = link.getAttribute("href")?.replace(/^#/, "");
    if (!id) return;
    event.preventDefault();
    navigateToSection(id);
  }));
  const observer = new IntersectionObserver(entries => entries.forEach(entry => {
    if (entry.isIntersecting) {
      $$(".sidebar nav a").forEach(link => link.classList.toggle("active", link.getAttribute("href") === `#${entry.target.id}`));
    }
  }), { rootMargin: "-20% 0px -70% 0px" });
  $$(".anchor").forEach(section => observer.observe(section));
  updateLoadingMode(); updateUnits();
  restoreAnalysisSession();
  const initialId = window.location.hash.replace(/^#/, "");
  if (initialId) requestAnimationFrame(() => navigateToSection(initialId, false));
}

initialize();