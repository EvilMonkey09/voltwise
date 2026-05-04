
document.addEventListener("DOMContentLoaded", () => {
  let I = {};
  try {
    const raw =
      document.body?.getAttribute("data-vw-i18n") ||
      document.body?.dataset?.vwI18n;
    if (raw) I = JSON.parse(raw);
  } catch (_) {
    I = {};
  }

  const statusEl = document.getElementById("connection-status");
  const btnCreate = document.getElementById("btn-create-event");

  let SENSOR_ADDRESSES = [];
  try {
    const raw =
      document.body?.getAttribute("data-sensor-addresses") ||
      document.body?.dataset?.sensorAddresses;
    if (raw) SENSOR_ADDRESSES = JSON.parse(raw);
  } catch (_) {
    SENSOR_ADDRESSES = [];
  }
  SENSOR_ADDRESSES = SENSOR_ADDRESSES.map(Number).sort((a, b) => a - b);

  const PHASE_COLORS = ["#dc2626", "#2563eb", "#ca8a04"];
  const NEUTRAL_COLOR = "#0d9488";
  const TOTAL_COLOR = "#7c3aed";

  const MAX_POINTS = 200;

  let charts = {};
  let pollInterval = setInterval(fetchData, 1000);

  const LOG_KEYS = [
    { v: "p1_v", i: "p1_i", p: "p1_p" },
    { v: "p2_v", i: "p2_i", p: "p2_p" },
    { v: "p3_v", i: "p3_i", p: "p3_p" },
  ];

  // --- Tabs ---
  function initTabs() {
    const tabs = document.querySelectorAll(".vw-tab");
    const panels = document.querySelectorAll(".vw-tab-panel");
    const panelByTab = {
      "tab-live": "panel-live",
      "tab-details": "panel-details",
    };
    function selectTab(tabId) {
      tabs.forEach((t) => {
        const on = t.id === tabId;
        t.classList.toggle("active", on);
        t.setAttribute("aria-selected", on ? "true" : "false");
        t.tabIndex = on ? 0 : -1;
      });
      const showPanelId = panelByTab[tabId];
      panels.forEach((p) => {
        const show = p.id === showPanelId;
        if (show) {
          p.classList.remove("hidden");
          p.hidden = false;
        } else {
          p.classList.add("hidden");
          p.hidden = true;
        }
      });
      if (tabId === "tab-live") {
        requestAnimationFrame(() => {
          Object.values(charts).forEach((c) => {
            if (c && typeof c.resize === "function") c.resize();
          });
        });
      }
    }
    tabs.forEach((tab) => {
      tab.addEventListener("click", () => selectTab(tab.id));
      tab.addEventListener("keydown", (e) => {
        if (e.key === "ArrowRight" || e.key === "ArrowLeft") {
          e.preventDefault();
          const i = [...tabs].indexOf(tab);
          const next =
            e.key === "ArrowRight"
              ? tabs[(i + 1) % tabs.length]
              : tabs[(i - 1 + tabs.length) % tabs.length];
          next.focus();
          selectTab(next.id);
        }
      });
    });
  }

  initTabs();
  initDetailPlaceholders();
  initCharts();
  loadHistory();
  fetchInitialHistory();

  function phaseLabel(idx) {
    return "L" + (idx + 1);
  }

  function datasetLabelForAddr(addr, idx) {
    return phaseLabel(idx) + " · " + addr;
  }

  function chartOptionsExtra(yTitle) {
    return {
      responsive: true,
      maintainAspectRatio: false,
      animation: false,
      interaction: { mode: "index", intersect: false },
      plugins: {
        legend: {
          position: "top",
          labels: { boxWidth: 10, usePointStyle: true, padding: 12 },
        },
        tooltip: {
          mode: "index",
          intersect: false,
        },
      },
      scales: {
        x: {
          display: true,
          ticks: {
            maxRotation: 0,
            autoSkip: true,
            maxTicksLimit: 8,
            font: { size: 10 },
          },
          grid: { display: false },
        },
        y: {
          beginAtZero: false,
          grace: "8%",
          ticks: { font: { size: 11 } },
          title: {
            display: !!yTitle,
            text: yTitle || "",
            font: { size: 11 },
          },
        },
      },
      elements: { point: { radius: 0, hoverRadius: 4 } },
    };
  }

  function initCharts() {
    const n = SENSOR_ADDRESSES.length;
    const vDatasets = SENSOR_ADDRESSES.map((addr, idx) => ({
      label: datasetLabelForAddr(addr, idx),
      borderColor: PHASE_COLORS[idx % PHASE_COLORS.length],
      backgroundColor: "transparent",
      borderWidth: 2,
      tension: 0.15,
      data: [],
    }));

    const iDatasets = SENSOR_ADDRESSES.map((addr, idx) => ({
      label: datasetLabelForAddr(addr, idx),
      borderColor: PHASE_COLORS[idx % PHASE_COLORS.length],
      backgroundColor: "transparent",
      borderWidth: 2,
      tension: 0.15,
      data: [],
    }));
    if (n === 3) {
      iDatasets.push({
        label: "N",
        borderColor: NEUTRAL_COLOR,
        backgroundColor: "transparent",
        borderWidth: 2,
        tension: 0.15,
        data: [],
      });
    }

    const pDatasets = [
      {
        label: "Σ",
        borderColor: TOTAL_COLOR,
        borderWidth: 2.5,
        data: [],
        tension: 0.15,
      },
      ...SENSOR_ADDRESSES.map((addr, idx) => ({
        label: datasetLabelForAddr(addr, idx),
        borderColor: PHASE_COLORS[idx % PHASE_COLORS.length],
        borderDash: [6, 4],
        borderWidth: 1.5,
        data: [],
        tension: 0.15,
      })),
    ];

    charts.voltage = new Chart(document.getElementById("chart-live-voltage"), {
      type: "line",
      data: { labels: [], datasets: vDatasets },
      options: chartOptionsExtra("V"),
    });

    charts.current = new Chart(document.getElementById("chart-live-current"), {
      type: "line",
      data: { labels: [], datasets: iDatasets },
      options: chartOptionsExtra("A"),
    });

    charts.power = new Chart(document.getElementById("chart-live-power"), {
      type: "line",
      data: { labels: [], datasets: pDatasets },
      options: chartOptionsExtra("W"),
    });
  }

  function initDetailPlaceholders() {
    const grid = document.getElementById("detail-stats-grid");
    if (!grid) return;
    grid.innerHTML = "";
    SENSOR_ADDRESSES.forEach((addr, idx) => {
      const card = document.createElement("article");
      card.className = "detail-sensor-card";
      card.dataset.address = String(addr);
      card.innerHTML = `
        <h3>${phaseLabel(idx)} · addr ${addr}</h3>
        <div class="detail-metric-block" data-metric="voltage">
          <div class="detail-metric-label">U (${I.unit_v || "V"})</div>
          <div class="detail-stat-row">
            <div><span class="lbl">${I.detail_min || "Min"}</span><span class="val" data-field="min">—</span></div>
            <div><span class="lbl">${I.detail_max || "Max"}</span><span class="val" data-field="max">—</span></div>
            <div><span class="lbl">${I.detail_delta || "Δ"}</span><span class="val" data-field="delta">—</span></div>
          </div>
        </div>
        <div class="detail-metric-block" data-metric="current">
          <div class="detail-metric-label">I (${I.unit_a || "A"})</div>
          <div class="detail-stat-row">
            <div><span class="lbl">${I.detail_min || "Min"}</span><span class="val" data-field="min">—</span></div>
            <div><span class="lbl">${I.detail_max || "Max"}</span><span class="val" data-field="max">—</span></div>
            <div><span class="lbl">${I.detail_delta || "Δ"}</span><span class="val" data-field="delta">—</span></div>
          </div>
        </div>
        <div class="detail-metric-block" data-metric="power">
          <div class="detail-metric-label">P (${I.unit_w || "W"})</div>
          <div class="detail-stat-row">
            <div><span class="lbl">${I.detail_min || "Min"}</span><span class="val" data-field="min">—</span></div>
            <div><span class="lbl">${I.detail_max || "Max"}</span><span class="val" data-field="max">—</span></div>
            <div><span class="lbl">${I.detail_delta || "Δ"}</span><span class="val" data-field="delta">—</span></div>
          </div>
        </div>`;
      grid.appendChild(card);
    });
  }

  function statsFromSeries(arr) {
    const nums = arr.filter((x) => typeof x === "number" && !Number.isNaN(x));
    if (nums.length === 0) return { min: null, max: null, delta: null };
    let min = nums[0];
    let max = nums[0];
    for (const x of nums) {
      if (x < min) min = x;
      if (x > max) max = x;
    }
    const delta =
      nums.length >= 2 ? nums[nums.length - 1] - nums[nums.length - 2] : null;
    return { min, max, delta };
  }

  function fmtStat(v, decimals) {
    if (v === null || v === undefined || Number.isNaN(v)) return "—";
    return Number(v).toFixed(decimals);
  }

  function refreshDetailStats() {
    const grid = document.getElementById("detail-stats-grid");
    if (!grid || !charts.voltage) return;

    SENSOR_ADDRESSES.forEach((addr, idx) => {
      const card = grid.querySelector(`[data-address="${addr}"]`);
      if (!card) return;

      const vArr = charts.voltage.data.datasets[idx]?.data || [];
      const iArr = charts.current.data.datasets[idx]?.data || [];
      const pArr = charts.power.data.datasets[idx + 1]?.data || [];

      const sv = statsFromSeries(vArr);
      const si = statsFromSeries(iArr);
      const sp = statsFromSeries(pArr);

      const blocks = {
        voltage: { stats: sv, dec: 2 },
        current: { stats: si, dec: 3 },
        power: { stats: sp, dec: 1 },
      };

      for (const [metric, { stats, dec }] of Object.entries(blocks)) {
        const block = card.querySelector(`[data-metric="${metric}"]`);
        if (!block) continue;
        block.querySelector('[data-field="min"]').textContent = fmtStat(
          stats.min,
          dec
        );
        block.querySelector('[data-field="max"]').textContent = fmtStat(
          stats.max,
          dec
        );
        block.querySelector('[data-field="delta"]').textContent = fmtStat(
          stats.delta,
          dec
        );
      }
    });
  }

  async function fetchData() {
    try {
      const response = await fetch("/api/data");
      const data = await response.json();

      updateDashboard(data);
      updateLiveCharts(data);
      refreshDetailStats();

      const demoBanner = document.getElementById("demo-banner");
      if (demoBanner) {
        demoBanner.hidden = !data.simulation;
      }

      statusEl.textContent = I.connected || "Connected";
      statusEl.style.color = "green";
    } catch (error) {
      console.error("Error fetching data:", error);
      statusEl.textContent = I.disconnected || "Disconnected";
      statusEl.style.color = "red";
    }
  }

  function updateDashboard(data) {
    const sensors = data.sensors || {};
    for (const [address, values] of Object.entries(sensors)) {
      const idBase = (k) => `${k}-${address}`;
      if (!values) {
        ["voltage", "current", "power", "energy", "frequency", "pf"].forEach(
          (k) => setVal(idBase(k), "—")
        );
        continue;
      }
      setVal(idBase("voltage"), fmt(values.voltage, 1));
      setVal(idBase("current"), fmt(values.current, 3));
      setVal(idBase("power"), fmt(values.power, 1));
      setVal(idBase("energy"), fmt(values.energy, 2));
      setVal(idBase("frequency"), fmt(values.frequency, 1));
      setVal(idBase("pf"), fmt(values.pf, 2));
    }

    let totalP = 0;
    for (const s of Object.values(sensors)) {
      if (s && typeof s.power === "number") totalP += s.power;
    }
    setVal("total-power", totalP.toFixed(1));

    const nEl = document.getElementById("neutral-current");
    if (
      nEl &&
      data.neutral_current !== undefined &&
      data.neutral_current !== null
    ) {
      nEl.textContent = Number(data.neutral_current).toFixed(3);
    }
  }

  function fmt(v, decimals) {
    if (v === undefined || v === null || Number.isNaN(Number(v))) return "—";
    return Number(v).toFixed(decimals);
  }

  function setVal(id, val) {
    const el = document.getElementById(id);
    if (el) el.textContent = val;
  }

  document
    .querySelector(".live-table-wrap")
    ?.addEventListener("click", async (e) => {
      const btn = e.target.closest(".reset-btn");
      if (!btn) return;
      const address = btn.getAttribute("data-address");
      if (!address || !confirm(I.reset_confirm || "?")) return;
      try {
        const res = await fetch("/api/reset", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ address: Number(address) }),
        });
        const j = await res.json();
        if (!j.success) alert(j.error || I.reset_failed || "");
      } catch (err) {
        alert(I.reset_failed || "");
      }
    });

  function logRowToValues(log) {
    const n = SENSOR_ADDRESSES.length;
    const vs = [];
    const is = [];
    const ps = [];
    for (let i = 0; i < n; i++) {
      const k = LOG_KEYS[i];
      if (!k) break;
      vs.push(log[k.v] ?? null);
      is.push(log[k.i] ?? null);
      ps.push(log[k.p] ?? null);
    }
    return { vs, is, ps, neutral: log.neutral_i ?? null };
  }

  async function fetchInitialHistory() {
    try {
      const res = await fetch("/api/history?limit=300");
      const logs = await res.json();
      logs.forEach((log) => {
        const label = new Date(log.timestamp * 1000).toLocaleTimeString();
        const { vs, is, ps, neutral } = logRowToValues(log);
        let totalP = 0;
        ps.forEach((p) => {
          if (typeof p === "number") totalP += p;
        });
        padArrays(vs, SENSOR_ADDRESSES.length);
        padArrays(is, SENSOR_ADDRESSES.length);
        padArrays(ps, SENSOR_ADDRESSES.length);

        addDataToChart(charts.voltage, label, vs);
        const iPayload =
          SENSOR_ADDRESSES.length === 3
            ? [...is, neutral]
            : [...is];
        addDataToChart(charts.current, label, iPayload);
        addDataToChart(charts.power, label, [totalP, ...ps]);
      });
      refreshDetailStats();
    } catch (e) {
      console.error("Error loading history", e);
    }
  }

  function padArrays(arr, len) {
    while (arr.length < len) arr.push(null);
  }

  function updateLiveCharts(data) {
    const label = new Date(data.timestamp * 1000).toLocaleTimeString();
    const sensors = data.sensors || {};

    const vs = SENSOR_ADDRESSES.map((a) =>
      sensors[a] ? sensors[a].voltage : null
    );
    const is_ = SENSOR_ADDRESSES.map((a) =>
      sensors[a] ? sensors[a].current : null
    );
    let totalP = 0;
    SENSOR_ADDRESSES.forEach((a) => {
      const s = sensors[a];
      if (s && typeof s.power === "number") totalP += s.power;
    });
    const ps = SENSOR_ADDRESSES.map((a) =>
      sensors[a] ? sensors[a].power : null
    );

    addDataToChart(charts.voltage, label, vs);
    const iPayload =
      SENSOR_ADDRESSES.length === 3
        ? [...is_, data.neutral_current]
        : is_;
    addDataToChart(charts.current, label, iPayload);
    addDataToChart(charts.power, label, [totalP, ...ps]);
  }

  function addDataToChart(chart, label, dataArray) {
    if (!chart) return;
    if (chart.data.labels.length > MAX_POINTS) {
      chart.data.labels.shift();
      chart.data.datasets.forEach((ds) => ds.data.shift());
    }
    chart.data.labels.push(label);
    chart.data.datasets.forEach((ds, idx) => {
      const v = dataArray[idx];
      ds.data.push(v !== undefined ? v : null);
    });
    chart.update("none");
  }

  btnCreate?.addEventListener("click", async () => {
    const name = prompt(I.event_prompt || "");
    if (!name) return;

    try {
      const res = await fetch("/api/events", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ name }),
      });
      const json = await res.json();

      if (json.success) {
        window.location.href = `/events/${json.event_id}`;
      } else {
        alert(json.error);
      }
    } catch (e) {
      alert(I.event_create_error || "");
    }
  });

  async function loadHistory() {
    try {
      const res = await fetch("/api/events");
      const events = await res.json();

      const tbody = document.querySelector("#events-table tbody");
      tbody.innerHTML = "";

      events.forEach((evt) => {
        const tr = document.createElement("tr");
        const start = new Date(evt.start_time * 1000).toLocaleString();

        let status = I.events_created || "";
        if (evt.end_time) status = I.events_closed || "";
        if (evt.is_active) status = I.events_recording || "";

        let duration = "—";
        if (evt.end_time) {
          duration =
            ((evt.end_time - evt.start_time) / 60).toFixed(1) +
            " " +
            (I.min_unit || "min");
        } else if (evt.is_active) {
          duration = I.events_running || "";
        }

        tr.innerHTML = `
            <td>
                <span class="event-name-display">${evt.name}</span>
                <input class="edit-name-input hidden" value="${evt.name}" />
            </td>
            <td>${start}</td>
            <td>${duration}</td>
            <td>${status}</td>
            <td>
                <a href="/events/${evt.id}" class="btn primary small">${I.btn_open || "Open"}</a>
                <button class="btn secondary small" onclick="renameEvent(this, ${evt.id})">${I.btn_rename || ""}</button>
                <button class="btn danger small" onclick="deleteEvent(${evt.id})">${I.btn_delete || ""}</button>
                <a href="/api/events/${evt.id}/export" class="btn secondary small" target="_blank">${I.btn_csv || "CSV"}</a>
            </td>
        `;
        tbody.appendChild(tr);
      });
    } catch (e) {
      console.error("Error loading events", e);
    }
  }

  window.renameEvent = async (btn, id) => {
    const td = btn.closest("tr").cells[0];
    const span = td.querySelector("span");
    const input = td.querySelector("input");

    if (input.classList.contains("hidden")) {
      input.classList.remove("hidden");
      span.classList.add("hidden");
      btn.textContent = I.btn_save || "Save";
      input.focus();
    } else {
      const newName = input.value.trim();
      if (newName) {
        await fetch(`/api/events/${id}`, {
          method: "PUT",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ name: newName }),
        });
        loadHistory();
      }
    }
  };

  window.deleteEvent = async (id) => {
    if (confirm(I.delete_confirm || "")) {
      await fetch(`/api/events/${id}`, { method: "DELETE" });
      loadHistory();
    }
  };

  async function checkUpdate() {
    try {
      const r = await fetch("/api/update/status");
      const d = await r.json();
      if (!d.ok || !d.update_available) return;
      const bd = document.getElementById("update-backdrop");
      const md = document.getElementById("update-modal");
      if (!bd || !md) return;
      document.getElementById("upd-current").textContent = d.current;
      document.getElementById("upd-latest").textContent =
        d.latest_tag || d.latest_version || "";
      const warn = document.getElementById("upd-no-sudo");
      const installBtn = document.getElementById("upd-install");
      if (!d.can_apply_zip) {
        warn.classList.remove("hidden");
        installBtn.classList.add("hidden");
      }
      bd.classList.remove("hidden");
      md.classList.remove("hidden");
      document.getElementById("upd-dismiss").onclick = () => {
        bd.classList.add("hidden");
        md.classList.add("hidden");
      };
      installBtn.onclick = async () => {
        installBtn.disabled = true;
        const logEl = document.getElementById("upd-log");
        logEl.classList.remove("hidden");
        logEl.textContent = I.installing || "";
        try {
          const resp = await fetch("/api/update/apply", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ confirm: true }),
          });
          const out = await resp.json();
          logEl.textContent =
            (out.stdout || "") +
            "\n" +
            (out.stderr || "") +
            "\n" +
            (out.error || "") +
            "\n";
          if (out.ok) {
            logEl.textContent += "\n" + (I.install_done || "");
            setTimeout(() => location.reload(), 5000);
          }
        } catch (e) {
          logEl.textContent += String(e);
        }
        installBtn.disabled = false;
      };
      bd.onclick = (ev) => {
        if (ev.target === bd) {
          bd.classList.add("hidden");
          md.classList.add("hidden");
        }
      };
    } catch (e) {
      /* ignore */
    }
  }
  checkUpdate();
});
