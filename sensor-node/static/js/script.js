
document.addEventListener("DOMContentLoaded", () => {
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
      
      statusEl.textContent = "Connected";
      statusEl.style.color = "green";

    } catch (error) {
      console.error("Error fetching data:", error);
      statusEl.textContent = "Disconnected";
      statusEl.style.color = "red";
    }
  }

  function updateDashboard(data) {
    // Update per-sensor cards
    for (const [address, values] of Object.entries(data.sensors)) {
      if (values) {
        setVal(`voltage-${address}`, values.voltage);
        setVal(`current-${address}`, values.current);
        setVal(`power-${address}`, values.power);
        setVal(`energy-${address}`, values.energy);
        setVal(`frequency-${address}`, values.frequency);
        setVal(`pf-${address}`, values.pf);
      }
    }

    // Update Sum/Neutral
    if (data.neutral_current !== undefined) {
      setVal("neutral-current", data.neutral_current);

      // Calculate Total Power
      let totalP = 0;
      for (const s of Object.values(data.sensors)) {
        if (s) totalP += s.power;
      }
      setVal("total-power", totalP.toFixed(1));
    }
  }

  function setVal(id, val) {
    const el = document.getElementById(id);
    if (el) el.textContent = val;
  }

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
    const name = prompt("Enter Event Name:");
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
      alert("Error creating event");
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
        let status = "Created";
        if (evt.end_time) status = "Closed";
        if (evt.is_active) status = "recording..."; 
        
        // Duration
        let duration = "-";
        if (evt.end_time) {
            duration = ((evt.end_time - evt.start_time) / 60).toFixed(1) + " min";
        } else if (evt.is_active) {
            duration = "Running"; 
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
                <a href="/events/${evt.id}" class="btn primary small">Open</a>
                <button class="btn secondary small" onclick="renameEvent(this, ${evt.id})">Rename</button>
                <button class="btn danger small" onclick="deleteEvent(${evt.id})">Delete</button>
                <a href="/api/events/${evt.id}/export" class="btn secondary small" target="_blank">CSV</a>
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
          btn.textContent = "Save";
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
      if (confirm("Are you sure? This will delete all data for this event.")) {
          await fetch(`/api/events/${id}`, { method: 'DELETE' });
          loadHistory();
      }
  };
});
