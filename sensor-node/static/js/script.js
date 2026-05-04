
document.addEventListener("DOMContentLoaded", () => {
  let I = {};
  try {
    const raw = document.body?.dataset?.vwI18n;
    if (raw) I = JSON.parse(raw);
  } catch (_) {
    I = {};
  }
  const statusEl = document.getElementById("connection-status");
  const btnCreate = document.getElementById("btn-create-event");

  // Chart Instances
  let charts = {};
  
  // Polling interval
  let pollInterval = setInterval(fetchData, 1000);

  // --- Initialization ---
  initCharts();
  loadHistory();
  fetchInitialHistory(); // Load past data for charts

  // --- Data Polling ---
  async function fetchData() {
    try {
      const response = await fetch("/api/data");
      const data = await response.json();

      updateDashboard(data);
      updateLiveCharts(data);

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
        ["voltage", "current", "power", "energy", "frequency", "pf"].forEach((k) =>
          setVal(idBase(k), "—")
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
    if (nEl && data.neutral_current !== undefined && data.neutral_current !== null) {
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

  document.querySelector(".live-table-wrap")?.addEventListener("click", async (e) => {
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

  // --- Live Charts ---
  async function fetchInitialHistory() {
      try {
          const res = await fetch('/api/history?limit=100'); // Load last 100 points
          const logs = await res.json();
          // Populate charts
          logs.forEach(log => {
             // Convert log structure to chart format if needed, but updateLiveCharts expects 'data' object structure from /api/data
             // The logs from DB have p1_v etc.
             // We need to map DB log format to the format updateLiveCharts expects, OR make updateLiveCharts handle DB format?
             // Easier to just push data points directly to chart datasets here.
             
             const label = new Date(log.timestamp * 1000).toLocaleTimeString();
             
             addDataToChart(charts.voltage, label, [log.p1_v, log.p2_v, log.p3_v]);
             addDataToChart(charts.current, label, [log.p1_i, log.p2_i, log.p3_i, log.neutral_i]);
             
             // Calculate totals/sum if needed or just plot phases
             const totalP = (log.p1_p||0) + (log.p2_p||0) + (log.p3_p||0);
             addDataToChart(charts.power, label, [totalP, log.p1_p, log.p2_p, log.p3_p]);
          });
      } catch (e) {
          console.error("Error loading history", e);
      }
  }

  function initCharts() {
      const commonOpts = {
          responsive: true,
          maintainAspectRatio: false,
          animation: false, // Performance
          interaction: { mode: 'index', intersect: false },
          scales: { x: { display: false } }, // Hide X axis labels for live view to save space? Or Limit?
          elements: { point: { radius: 0 } }
      };
      
      charts.voltage = new Chart(document.getElementById('chart-live-voltage'), {
          type: 'line',
          data: { labels: [], datasets: [
              { label: 'L1', borderColor: 'red', data: [] },
              { label: 'L2', borderColor: 'blue', data: [] },
              { label: 'L3', borderColor: 'yellow', data: [] }
          ]},
          options: commonOpts
      });
      
      charts.current = new Chart(document.getElementById('chart-live-current'), {
          type: 'line',
          data: { labels: [], datasets: [
              { label: 'L1', borderColor: 'red', data: [] },
              { label: 'L2', borderColor: 'blue', data: [] },
              { label: 'L3', borderColor: 'yellow', data: [] },
              { label: 'N', borderColor: 'teal', data: [] }
          ]},
          options: commonOpts
      });
      
      charts.power = new Chart(document.getElementById('chart-live-power'), {
          type: 'line',
          data: { labels: [], datasets: [
              { label: 'Total', borderColor: 'purple', borderWidth: 2, data: [] },
              { label: 'L1', borderColor: 'red', borderDash: [5,5], borderWidth: 1, data: [] },
              { label: 'L2', borderColor: 'blue', borderDash: [5,5], borderWidth: 1, data: [] },
              { label: 'L3', borderColor: 'yellow', borderDash: [5,5], borderWidth: 1, data: [] }
          ]},
          options: commonOpts
      });
  }
  
  function updateLiveCharts(data) {
      const label = new Date(data.timestamp * 1000).toLocaleTimeString();
      
      // Extract values safely
      const v = (n) => data.sensors[n] ? data.sensors[n].voltage : null;
      const i = (n) => data.sensors[n] ? data.sensors[n].current : null;
      const p = (n) => data.sensors[n] ? data.sensors[n].power : null;
      
      let totalP = 0;
      Object.values(data.sensors).forEach(s => { if(s) totalP += s.power });
      
      addDataToChart(charts.voltage, label, [v(1), v(2), v(3)]);
      addDataToChart(charts.current, label, [i(1), i(2), i(3), data.neutral_current]);
      addDataToChart(charts.power, label, [totalP, p(1), p(2), p(3)]);
  }
  
  function addDataToChart(chart, label, dataArray) {
      if (chart.data.labels.length > 100) {
          chart.data.labels.shift();
          chart.data.datasets.forEach(ds => ds.data.shift());
      }
      chart.data.labels.push(label);
      chart.data.datasets.forEach((ds, idx) => {
          if (dataArray[idx] !== undefined) ds.data.push(dataArray[idx]);
      });
      chart.update('none'); // Update without animation
  }

  // --- Event Management ---
  
  btnCreate.addEventListener("click", async () => {
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
          // Redirect to event view
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
        
        // Status logic
        let status = I.events_created || "";
        if (evt.end_time) status = I.events_closed || "";
        if (evt.is_active) status = I.events_recording || "";
        
        let duration = "—";
        if (evt.end_time) {
            duration = ((evt.end_time - evt.start_time) / 60).toFixed(1) + " " + (I.min_unit || "min");
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
      // Toggle edit mode
      const td = btn.closest('tr').cells[0];
      const span = td.querySelector('span');
      const input = td.querySelector('input');
      
      if (input.classList.contains('hidden')) {
          input.classList.remove('hidden');
          span.classList.add('hidden');
          btn.textContent = I.btn_save || "Save";
          input.focus();
      } else {
          // Save
          const newName = input.value.trim();
          if (newName) {
              await fetch(`/api/events/${id}`, {
                  method: 'PUT',
                  headers: { 'Content-Type': 'application/json' },
                  body: JSON.stringify({ name: newName })
              });
              loadHistory();
          }
      }
  };
  
  window.deleteEvent = async (id) => {
      if (confirm(I.delete_confirm || "")) {
          await fetch(`/api/events/${id}`, { method: 'DELETE' });
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
