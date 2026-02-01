
document.addEventListener("DOMContentLoaded", async () => {
    if (typeof EVENT_ID === 'undefined') return;

    const nameEl = document.getElementById('event-name');
    const nameHeaderEl = document.getElementById('event-name-header');
    const startEl = document.getElementById('event-start');
    const durationEl = document.getElementById('event-duration');
    const pointsEl = document.getElementById('event-points');
    const statusEl = document.getElementById('event-status-indicator');
    
    const btnRecordStart = document.getElementById('btn-start-recording');
    const btnRecordStop = document.getElementById('btn-stop-recording');
    const btnDownload = document.getElementById('btn-download-csv');

    let isRecording = false;
    let pollInterval = null;
    let charts = {};

    // --- Initial Load ---
    try {
        await fetchEventDetails();
        initCharts();
        checkRecordingStatus();
        
        // Start polling for updates (charts + status)
        pollInterval = setInterval(async () => {
            await updateCharts();
            checkRecordingStatus();
        }, 1000);
        
    } catch (e) {
        console.error("Error init event view", e);
    }

    async function fetchEventDetails() {
        const res = await fetch(`/api/events/${EVENT_ID}`);
        const data = await res.json();
        
        if (!data.details) return;

        const d = data.details;
        nameEl.textContent = d.name;
        nameHeaderEl.textContent = d.name;
        startEl.textContent = new Date(d.start_time * 1000).toLocaleString();
        pointsEl.textContent = data.logs.length;
        
        // Duration
        if (d.end_time) {
             durationEl.textContent = ((d.end_time - d.start_time)/60).toFixed(1) + " min";
        } else {
             durationEl.textContent = "Open";
        }
        
        btnDownload.href = `/api/events/${EVENT_ID}/export`;
        
        // Initial Chart Data
        renderCharts(data.logs);
    }
    
    // --- Chart Controls ---
    const inputLimit = document.getElementById('chart-limit');
    const inputYVol = document.getElementById('ymax-voltage');
    const inputYCur = document.getElementById('ymax-current');
    const inputYPow = document.getElementById('ymax-power');
    const btnUpdate = document.getElementById('btn-update-charts');

    btnUpdate.addEventListener('click', () => {
        // Re-render with current full data but applied scale options
        // We need 'currentLogs' stored globally or refetch? 
        // Best to just trigger updateCharts which fetches latest
        updateCharts();
    });

    // --- Chart Logic ---

    // Store latest logs to apply local filtering without refetch if needed, 
    // but refetch is safer for live data.
    let currentLogs = [];

    async function updateCharts() {
        const res = await fetch(`/api/events/${EVENT_ID}`);
        const data = await res.json();
        if (data.logs) {
            currentLogs = data.logs;
            pointsEl.textContent = data.logs.length;
            renderCharts(data.logs);
        }
    }

    function renderCharts(logs) {
        if (!logs) return;
        
        // Filter by Limit?
        let displayLogs = logs;
        const limit = parseInt(inputLimit.value) || 0;
        if (limit > 0 && logs.length > limit) {
             displayLogs = logs.slice(logs.length - limit);
        }
        
        const labels = displayLogs.map(l => new Date(l.timestamp * 1000).toLocaleTimeString());
        
        if (!charts.voltage) {
             charts.voltage = createLineChart('chart-voltage', 'Voltage (V)');
        }
        updateChartData(charts.voltage, labels, [
            { label: 'L1', data: displayLogs.map(l=>l.p1_v), borderColor: 'red' },
            { label: 'L2', data: displayLogs.map(l=>l.p2_v), borderColor: 'blue' },
            { label: 'L3', data: displayLogs.map(l=>l.p3_v), borderColor: 'yellow' }
        ], inputYVol.value);
        
        if (!charts.current) {
             charts.current = createLineChart('chart-current', 'Current (A)');
        }
        updateChartData(charts.current, labels, [
            { label: 'L1', data: displayLogs.map(l=>l.p1_i), borderColor: 'red' },
            { label: 'L2', data: displayLogs.map(l=>l.p2_i), borderColor: 'blue' },
            { label: 'L3', data: displayLogs.map(l=>l.p3_i), borderColor: 'yellow' },
            { label: 'N', data: displayLogs.map(l=>l.neutral_i), borderColor: 'teal' }
        ], inputYCur.value);

        if (!charts.power) {
             charts.power = createLineChart('chart-power', 'Power (W)');
        }
        // Calculate Total
        const totalP = displayLogs.map(l => (l.p1_p||0)+(l.p2_p||0)+(l.p3_p||0));
        updateChartData(charts.power, labels, [
             { label: 'Total', data: totalP, borderColor: 'purple', borderWidth: 2 }, // Keep total slightly thicker? Or 1?
             { label: 'L1', data: displayLogs.map(l=>l.p1_p), borderColor: 'red', borderDash:[5,5] },
        ], inputYPow.value);
    }
    
    function createLineChart(canvasId, title) {
        return new Chart(document.getElementById(canvasId), {
            type: 'line',
            data: { labels: [], datasets: [] },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                interaction: { mode: 'index', intersect: false },
                elements: { point: { radius: 0, hitRadius: 10 }, line: { borderWidth: 1 } }, // Thinner lines globally
                plugins: { legend: { position: 'top' } },
                scales: {
                    y: { beginAtZero: true }
                }
            }
        });
    }
    
    function updateChartData(chart, labels, datasets, yMax) {
        chart.data.labels = labels;
        chart.data.datasets = datasets.map(d => ({
            ...d,
            fill: false,
            borderWidth: d.borderWidth || 1 // Force 1px unless specified
        }));
        
        // Update Scales
        if (yMax && parseFloat(yMax) > 0) {
            chart.options.scales.y.max = parseFloat(yMax);
        } else {
            delete chart.options.scales.y.max;
        }
        
        chart.update('none');
    }
});
