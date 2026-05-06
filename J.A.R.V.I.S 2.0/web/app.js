// DASHBOARD_EVOLVED_MARKER: Neural HUD wiring verified by DashboardAgent.
// J.A.R.V.I.S. 2.0 - Dashboard Neural Core Interface

const CONFIG = {
    API_URL: "/api",
    UPDATE_INTERVAL: 1000,
    LOG_LIMIT: 30
};

// State Tracking
let lastHistoryCount = 0;
let currentTab = 'hud';

// Tab Switching Logic
document.querySelectorAll('.nav-item').forEach(item => {
    item.addEventListener('click', () => {
        const tab = item.getAttribute('data-tab');
        if (!tab) return;

        // Update Nav UI
        document.querySelectorAll('.nav-item').forEach(n => n.classList.remove('active'));
        item.classList.add('active');

        // Update Content UI
        document.querySelectorAll('.tab-content').forEach(c => c.classList.remove('active'));
        document.getElementById(`tab-${tab}`).classList.add('active');

        document.getElementById('active-tab-label').innerText = (item.getAttribute('title') || 'HUD').toUpperCase();
        currentTab = tab;
    });
});

async function updateDashboard() {
    try {
        // 1. Fetch System Status
        const response = await fetch(`${CONFIG.API_URL}/status`);
        if (!response.ok) throw new Error("Backend offline");
        const data = await response.json();

        // Update Hardware Panels
        const cpuVal = document.getElementById('cpu-val');
        if (cpuVal) cpuVal.innerText = `${Math.round(data.cpu)}%`;
        const cpuFill = document.getElementById('cpu-fill');
        if (cpuFill) cpuFill.style.width = `${data.cpu}%`;

        const memVal = document.getElementById('mem-val');
        if (memVal) memVal.innerText = `${Math.round(data.memory)}%`;
        const memFill = document.getElementById('mem-fill');
        if (memFill) memFill.style.width = `${data.memory}%`;

        // Update Identity Panel (Arc Reactor)
        const hostName = document.getElementById('host-name');
        const trustLevel = document.getElementById('trust-level');
        const authIndicator = document.getElementById('auth-indicator');
        const arcReactor = document.querySelector('.arc-reactor');

        if (data.authenticated) {
            if (hostName) hostName.innerText = data.owner.toUpperCase();
            if (trustLevel) trustLevel.innerText = `Trust: ${Math.round(data.urgency * 100)}% (Verified)`;
            if (authIndicator) authIndicator.classList.add('authenticated');
            if (arcReactor) arcReactor.classList.add('pulse-arc');
        } else {
            if (hostName) hostName.innerText = "UNAUTHORIZED";
            if (trustLevel) trustLevel.innerText = "Trust: 0.0% (Pending)";
            if (authIndicator) authIndicator.classList.remove('authenticated');
            if (arcReactor) arcReactor.classList.remove('pulse-arc');
        }

        // Update Mood & Core
        const moodLabel = document.getElementById('mood-label');
        if (moodLabel) moodLabel.innerText = `MOOD: ${data.mood.toUpperCase()}`;
        const moodBar = document.getElementById('mood-intensity');
        if (moodBar) moodBar.style.width = `${data.urgency * 100}%`;

        // Thinking State & Core Animation
        const coreVisualizer = document.querySelector('.core-visualizer');
        const thinkingIndicator = document.getElementById('thinking-indicator');
        const thoughtProcess = document.getElementById('thought-process');

        if (data.thinking) {
            if (coreVisualizer) coreVisualizer.classList.add('thinking');
            if (thinkingIndicator) thinkingIndicator.classList.remove('thinking-hidden');
            if (thoughtProcess) thoughtProcess.innerText = data.thought.toUpperCase();

            // If we are in the Neural tab, update the COT feed
            if (currentTab === 'neural') {
                updateThinkingStream(data.thought);
            }
        } else {
            if (coreVisualizer) coreVisualizer.classList.remove('thinking');
            if (thinkingIndicator) thinkingIndicator.classList.add('thinking-hidden');
        }

        // 3. Fetch History & Logs
        const historyResponse = await fetch(`${CONFIG.API_URL}/history`);
        const historyData = await historyResponse.json();

        if (historyData.length !== lastHistoryCount) {
            updateLogs(historyData);
            lastHistoryCount = historyData.length;
        }

        // System Header
        const systemMode = document.getElementById('system-mode');
        if (systemMode) systemMode.innerText = "SYSTEM OPERATIONAL | NEURAL CORE NOMINAL";
        const statusDot = document.querySelector('.status-dot');
        if (statusDot) statusDot.style.background = "#4ade80";

    } catch (error) {
        console.error("Dashboard Sync Error:", error);
        const systemMode = document.getElementById('system-mode');
        if (systemMode) systemMode.innerText = "SYSTEM OFFLINE";
        const statusDot = document.querySelector('.status-dot');
        if (statusDot) statusDot.style.background = "#ff007a";
    }
}

function updateThinkingStream(thought) {
    const cotFeed = document.getElementById('cot-feed');
    if (!cotFeed) return;

    const lastEntry = cotFeed.querySelector('.entry:last-child');
    if (lastEntry && lastEntry.innerText.includes(thought)) return;

    const p = document.createElement('p');
    p.className = 'entry';
    p.innerText = `[${new Date().toLocaleTimeString()}] ${thought}`;
    cotFeed.appendChild(p);
    cotFeed.scrollTop = cotFeed.scrollHeight;
}

function updateLogs(history) {
    const logStream = document.getElementById('log-stream');
    if (!logStream) return;

    logStream.innerHTML = "";

    history.slice(-CONFIG.LOG_LIMIT).forEach(event => {
        const p = document.createElement('p');
        p.className = 'log-entry';
        const time = new Date(event.created_at).toLocaleTimeString();

        if (event.content.startsWith("/")) {
            p.classList.add('sys');
            p.innerText = `> [${time}] COMMAND: ${event.content}`;
        } else {
            p.innerText = `> [${time}] ${event.content}`;
        }

        logStream.appendChild(p);
    });

    logStream.scrollTop = logStream.scrollHeight;
}

// Clock Update
setInterval(() => {
    const clock = document.getElementById('clock');
    if (clock) clock.innerText = new Date().toLocaleTimeString();
}, 1000);

// Command Sending
async function sendCommand() {
    const input = document.getElementById('web-command');
    const command = input.value.trim();
    if (!command) return;

    input.value = "";
    input.disabled = true;

    try {
        await fetch(`${CONFIG.API_URL}/command`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ command })
        });
    } catch (error) {
        console.error("Command Error:", error);
    } finally {
        input.disabled = false;
        input.focus();
    }
}

const sendBtn = document.getElementById('send-command');
if (sendBtn) sendBtn.addEventListener('click', sendCommand);
const webInput = document.getElementById('web-command');
if (webInput) webInput.addEventListener('keypress', (e) => {
    if (e.key === 'Enter') sendCommand();
});

// Start Refresh Loop
setInterval(updateDashboard, CONFIG.UPDATE_INTERVAL);
updateDashboard();
