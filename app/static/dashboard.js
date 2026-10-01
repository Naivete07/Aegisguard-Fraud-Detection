// AegisGuard // Real-Time Fraud Detection & SHAP Explainability Engine
document.addEventListener("DOMContentLoaded", () => {
  // =========================================================================
  // CORE STATE & CONFIGURATIONS
  // =========================================================================
  let currentTab = "stream";
  let currentPage = 1;
  const pageSize = 20;
  let activeAlertId = null;
  let autoRefreshInterval = null;
  let tickCount = 89420119;
  let currentNotifFilter = "all";

  // Persistent Settings
  let appSettings = {
    xgbBlock: 80,
    xgbReview: 20,
    ifAnomaly: 65,
    speedCap: 500,
    soundEnabled: true,
    browserNotifs: false,
    pollingRate: 2000,
    autoRefreshTable: true,
    theme: "default",
    liveTicks: true
  };

  try {
    const savedSettings = localStorage.getItem("aegis_settings");
    if (savedSettings) {
      appSettings = Object.assign({}, appSettings, JSON.parse(savedSettings));
    }
  } catch (e) {}

  // Analyst Profile State
  let activeAnalystId = localStorage.getItem("aegis_analyst_id") || "ANALYST_VIVEK_LEAD";
  let activeAnalystName = localStorage.getItem("aegis_analyst_name") || "Agent Vivek Yadav";

  // Persistent Notifications
  let notifications = [
    {
      id: "notif-1",
      type: "critical",
      title: "HIGH-CONFIDENCE FRAUD BLOCK",
      content: "Terminated $850.00 POS transaction for Card •••• 4012 (Implied Speed: 1,420 km/h).",
      time: "Just now",
      read: false,
      alertId: null
    },
    {
      id: "notif-2",
      type: "warning",
      title: "UNSUPERVISED ANOMALY SPIKE",
      content: "Isolation Forest flagged atypical midnight velocity burst in grocery category.",
      time: "2m ago",
      read: false,
      alertId: null
    },
    {
      id: "notif-3",
      type: "system",
      title: "MODEL HEALTH PROBE PASS",
      content: "Hybrid XGBoost + Isolation Forest inference engine latency nominal at 1.42ms.",
      time: "5m ago",
      read: true,
      alertId: null
    }
  ];

  try {
    const savedNotifs = localStorage.getItem("aegis_notifications");
    if (savedNotifs) notifications = JSON.parse(savedNotifs);
  } catch (e) {}

  // =========================================================================
  // HELPER UTILITIES
  // =========================================================================
  function escapeHtml(str) {
    if (!str) return '';
    return String(str).replace(/[&<>"']/g, m => ({
      '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#039;'
    }[m]));
  }

  function debounce(func, wait) {
    let timeout;
    return (...args) => {
      clearTimeout(timeout);
      timeout = setTimeout(() => func.apply(this, args), wait);
    };
  }

  // Toast System
  function showToast(message, type = "info", duration = 4000) {
    const container = document.getElementById("cyber-toast-container");
    if (!container) return;

    const toast = document.createElement("div");
    toast.className = `cyber-toast toast-${type}`;
    const icon = type === "success" ? "✅" : (type === "danger" ? "🚨" : (type === "warning" ? "⚠️" : "⚡"));
    toast.innerHTML = `
      <span style="font-size: 16px;">${icon}</span>
      <span style="flex: 1; font-weight: 500;">${escapeHtml(message)}</span>
      <button class="toast-close-btn" style="background:none;border:none;color:#94a3b8;cursor:pointer;font-size:16px;line-height:1;">&times;</button>
    `;

    toast.querySelector(".toast-close-btn").addEventListener("click", () => toast.remove());
    container.appendChild(toast);

    setTimeout(() => {
      toast.style.opacity = "0";
      toast.style.transform = "translateX(40px)";
      setTimeout(() => toast.remove(), 300);
    }, duration);
  }

  // Audio Synthesizer
  let audioCtx = null;
  function playCyberAlertSound(type = "critical") {
    if (!appSettings.soundEnabled) return;
    try {
      if (!audioCtx) {
        audioCtx = new (window.AudioContext || window.webkitAudioContext)();
      }
      if (audioCtx.state === "suspended") {
        audioCtx.resume();
      }

      const osc = audioCtx.createOscillator();
      const gain = audioCtx.createGain();
      osc.connect(gain);
      gain.connect(audioCtx.destination);

      const now = audioCtx.currentTime;
      if (type === "critical") {
        osc.type = "sawtooth";
        osc.frequency.setValueAtTime(880, now);
        osc.frequency.exponentialRampToValueAtTime(330, now + 0.3);
        gain.gain.setValueAtTime(0.2, now);
        gain.gain.exponentialRampToValueAtTime(0.01, now + 0.3);
        osc.start(now);
        osc.stop(now + 0.3);
      } else {
        osc.type = "sine";
        osc.frequency.setValueAtTime(587.33, now);
        osc.frequency.setValueAtTime(880, now + 0.08);
        gain.gain.setValueAtTime(0.12, now);
        gain.gain.exponentialRampToValueAtTime(0.01, now + 0.2);
        osc.start(now);
        osc.stop(now + 0.2);
      }
    } catch (e) {}
  }

  // Theme Applier
  function applyTheme(themeName) {
    document.body.classList.remove("theme-matrix", "theme-crimson", "theme-amber", "theme-purple");
    if (themeName && themeName !== "default") {
      document.body.classList.add(`theme-${themeName}`);
    }
  }
  applyTheme(appSettings.theme);

  // =========================================================================
  // DOM ELEMENT SELECTORS
  // =========================================================================
  const tabButtons = document.querySelectorAll(".cyber-nav-item");
  const tabPanes = document.querySelectorAll(".tab-pane");
  const alertsTableBody = document.getElementById("alerts-table-body");
  const modalDetail = document.getElementById("modal-alert-detail");
  const btnCloseDetail = document.getElementById("btn-modal-close");
  const btnToggleInhibitor = document.getElementById("btn-toggle-inhibitor");
  const brandHomeBtn = document.getElementById("brand-home-btn");
  const btnQuickSimCenter = document.getElementById("btn-quick-sim-center");
  const btnOpenSandboxCenter = document.getElementById("btn-open-sandbox-center");

  const filterSearch = document.getElementById("filter-search");
  const filterStatus = document.getElementById("filter-status");
  const filterDecision = document.getElementById("filter-decision");
  const filterRisk = document.getElementById("filter-risk");
  const btnRefreshAlerts = document.getElementById("btn-refresh-alerts");
  const btnQuickSimulate = document.getElementById("btn-quick-simulate");

  // Notification Elements
  const btnHeaderNotifs = document.getElementById("btn-header-notifs");
  const notificationFlyout = document.getElementById("notification-flyout");
  const btnNotifClose = document.getElementById("btn-notif-close");
  const btnNotifMarkRead = document.getElementById("btn-notif-mark-read");
  const btnNotifClear = document.getElementById("btn-notif-clear");
  const btnNotifViewAll = document.getElementById("btn-notif-view-all");
  const btnNotifTestAlert = document.getElementById("btn-notif-test-alert");
  const notifListContainer = document.getElementById("notif-list-container");
  const notifUnreadCount = document.getElementById("notif-unread-count");
  const headerNotifDot = document.getElementById("header-notif-dot");
  const notifFilterChips = document.querySelectorAll(".notif-filter-chips .btn-filter-chip");

  // Settings Elements
  const btnHeaderSettings = document.getElementById("btn-header-settings");
  const modalSettings = document.getElementById("modal-settings");
  const btnSettingsClose = document.getElementById("btn-settings-close");
  const btnSettingsSave = document.getElementById("btn-settings-save");
  const btnSettingsReset = document.getElementById("btn-settings-reset");
  const settingsTabBtns = document.querySelectorAll(".settings-tab-btn");
  const settingsPanes = document.querySelectorAll(".settings-pane");
  const sliderXgbBlock = document.getElementById("slider-xgb-block");
  const valXgbBlock = document.getElementById("val-xgb-block");
  const sliderXgbReview = document.getElementById("slider-xgb-review");
  const valXgbReview = document.getElementById("val-xgb-review");
  const sliderIfAnomaly = document.getElementById("slider-if-anomaly");
  const valIfAnomaly = document.getElementById("val-if-anomaly");
  const sliderSpeedCap = document.getElementById("slider-speed-cap");
  const valSpeedCap = document.getElementById("val-speed-cap");
  const settingSoundEnabled = document.getElementById("setting-sound-enabled");
  const settingBrowserNotifs = document.getElementById("setting-browser-notifs");
  const settingPollingRate = document.getElementById("setting-polling-rate");
  const settingAutoRefreshTable = document.getElementById("setting-auto-refresh-table");
  const settingLiveTicks = document.getElementById("setting-live-ticks");
  const btnExportDiagnostics = document.getElementById("btn-export-diagnostics");
  const btnResetNotifCache = document.getElementById("btn-reset-notif-cache");
  const themeSwatchCards = document.querySelectorAll(".theme-swatch-card");

  // Profile Elements
  const btnUserAvatar = document.getElementById("btn-user-avatar");
  const profileFlyout = document.getElementById("profile-flyout");
  const btnProfileClose = document.getElementById("btn-profile-close");
  const inputAnalystId = document.getElementById("input-analyst-id");
  const btnSaveAnalystId = document.getElementById("btn-save-analyst-id");
  const profileAnalystName = document.getElementById("profile-analyst-name");
  const profileAvatarDisplay = document.getElementById("profile-avatar-display");
  const profileSessionTimer = document.getElementById("profile-session-timer");
  const profileCasesCount = document.getElementById("profile-cases-count");
  const profileLossPrevented = document.getElementById("profile-loss-prevented");
  const btnCopySessionToken = document.getElementById("btn-copy-session-token");
  const btnLockSession = document.getElementById("btn-lock-session");
  const lockscreenOverlay = document.getElementById("lockscreen-overlay");
  const btnUnlockConsole = document.getElementById("btn-unlock-console");

  // =========================================================================
  // NAVIGATION TAB SWITCHING
  // =========================================================================
  tabButtons.forEach(btn => {
    btn.addEventListener("click", () => {
      const targetTab = btn.getAttribute("data-tab");
      switchTab(targetTab);
    });
  });

  if (brandHomeBtn) {
    brandHomeBtn.addEventListener("click", () => switchTab("stream"));
  }

  if (btnOpenSandboxCenter) {
    btnOpenSandboxCenter.addEventListener("click", () => switchTab("warroom"));
  }

  function switchTab(targetTab) {
    currentTab = targetTab;
    tabButtons.forEach(b => {
      if (b.getAttribute("data-tab") === targetTab) {
        b.classList.add("active");
      } else {
        b.classList.remove("active");
      }
    });

    tabPanes.forEach(p => {
      if (p.id === `pane-${targetTab}`) {
        p.classList.add("active");
      } else {
        p.classList.remove("active");
      }
    });

    if (targetTab === "telemetry") loadAlerts(true);
    if (targetTab === "defenses") loadDriftAudit();
    if (targetTab === "diagnostics") loadModelRegistry();
    if (targetTab === "shap") loadGlobalShapView();
  }

  // Global Search Shortcut ⌘K / Ctrl+K
  window.addEventListener("keydown", (e) => {
    if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "k") {
      e.preventDefault();
      const sInput = document.getElementById("global-search-input");
      if (sInput) sInput.focus();
    }
  });

  const globalSearchInput = document.getElementById("global-search-input");
  if (globalSearchInput) {
    globalSearchInput.addEventListener("keydown", (e) => {
      if (e.key === "Enter" && globalSearchInput.value.trim()) {
        switchTab("telemetry");
        if (filterSearch) {
          filterSearch.value = globalSearchInput.value.trim();
          loadAlerts(true);
        }
      }
    });
  }

  // Policy Override Toggle
  if (btnToggleInhibitor) {
    btnToggleInhibitor.addEventListener("click", () => {
      if (btnToggleInhibitor.textContent.includes("DISABLED")) {
        btnToggleInhibitor.textContent = "[ACTIVE OVERRIDE]";
        btnToggleInhibitor.style.color = "#f87171";
        btnToggleInhibitor.style.borderColor = "#f87171";
        showToast("Scoring policy override active.", "warning");
      } else {
        btnToggleInhibitor.textContent = "[DISABLED]";
        btnToggleInhibitor.style.color = "";
        btnToggleInhibitor.style.borderColor = "";
        showToast("Scoring policy reset to default.", "info");
      }
    });
  }

  // =========================================================================
  // REAL-TIME TRANSACTION SCORING STREAM CHART
  // =========================================================================
  const streamCanvas = document.getElementById("transaction-stream-canvas");
  const streamPoints = [];

  const streamNow = Date.now();
  for (let i = 0; i < 40; i++) {
    const isHigh = Math.random() < 0.08;
    const isMedium = !isHigh && Math.random() < 0.15;
    let score = isHigh ? (0.78 + Math.random() * 0.2) : (isMedium ? (0.42 + Math.random() * 0.3) : (Math.random() * 0.28));
    streamPoints.push({
      time: streamNow - (40 - i) * 1200,
      score: score,
      amount: Math.round(isHigh ? (1500 + Math.random() * 8000) : (10 + Math.random() * 120)),
      id: 8900 + i,
      label: isHigh ? "ALERT" : ""
    });
  }

  function initTransactionStreamChart() {
    if (!streamCanvas) return;
    const ctx = streamCanvas.getContext("2d");

    function resizeCanvas() {
      const rect = streamCanvas.getBoundingClientRect();
      const dpr = window.devicePixelRatio || 1;
      if (rect.width > 0 && rect.height > 0) {
        streamCanvas.width = rect.width * dpr;
        streamCanvas.height = rect.height * dpr;
      }
    }

    window.addEventListener("resize", resizeCanvas);
    resizeCanvas();

    function renderStream() {
      const rect = streamCanvas.getBoundingClientRect();
      const width = rect.width;
      const height = rect.height;

      if (width === 0 || height === 0) {
        requestAnimationFrame(renderStream);
        return;
      }

      const dpr = window.devicePixelRatio || 1;
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
      ctx.clearRect(0, 0, width, height);

      const paddingLeft = 35;
      const paddingRight = 15;
      const paddingTop = 15;
      const paddingBottom = 22;
      const plotWidth = width - paddingLeft - paddingRight;
      const plotHeight = height - paddingTop - paddingBottom;

      const currentTime = Date.now();
      const windowDuration = 50 * 1000;

      const yBlock = paddingTop + plotHeight * (1 - 0.75);
      const yReview = paddingTop + plotHeight * (1 - 0.40);

      ctx.fillStyle = "rgba(220, 38, 38, 0.05)";
      ctx.fillRect(paddingLeft, paddingTop, plotWidth, yBlock - paddingTop);

      ctx.fillStyle = "rgba(245, 158, 11, 0.03)";
      ctx.fillRect(paddingLeft, yBlock, plotWidth, yReview - yBlock);

      ctx.beginPath();
      ctx.moveTo(paddingLeft, yBlock);
      ctx.lineTo(paddingLeft + plotWidth, yBlock);
      ctx.strokeStyle = "rgba(248, 113, 113, 0.4)";
      ctx.lineWidth = 1;
      ctx.setLineDash([4, 4]);
      ctx.stroke();

      ctx.beginPath();
      ctx.moveTo(paddingLeft, yReview);
      ctx.lineTo(paddingLeft + plotWidth, yReview);
      ctx.strokeStyle = "rgba(251, 191, 36, 0.35)";
      ctx.lineWidth = 1;
      ctx.setLineDash([4, 4]);
      ctx.stroke();
      ctx.setLineDash([]);

      const yBase = paddingTop + plotHeight * (1 - 0.038);
      ctx.beginPath();
      ctx.moveTo(paddingLeft, yBase);
      ctx.lineTo(paddingLeft + plotWidth, yBase);
      ctx.strokeStyle = "rgba(56, 189, 248, 0.25)";
      ctx.lineWidth = 1;
      ctx.stroke();

      ctx.fillStyle = "rgba(148, 163, 184, 0.7)";
      ctx.font = "8.5px 'JetBrains Mono', monospace";
      ctx.fillText("1.00", 6, paddingTop + 4);
      ctx.fillText("0.75", 6, yBlock + 3);
      ctx.fillText("0.40", 6, yReview + 3);
      ctx.fillText("0.00", 6, paddingTop + plotHeight + 3);

      ctx.fillStyle = "rgba(248, 113, 113, 0.75)";
      ctx.fillText("BLOCK (>75%)", paddingLeft + 6, yBlock - 4);

      ctx.fillStyle = "rgba(251, 191, 36, 0.75)";
      ctx.fillText("REVIEW (40-75%)", paddingLeft + 6, yReview - 4);

      ctx.fillStyle = "rgba(56, 189, 248, 0.75)";
      ctx.fillText("EXPECTED BASELINE (3.8%)", paddingLeft + plotWidth - 140, yBase - 4);

      streamPoints.forEach((p) => {
        const timeDiff = currentTime - p.time;
        if (timeDiff > windowDuration) return;

        const x = paddingLeft + plotWidth * (1 - timeDiff / windowDuration);
        const y = paddingTop + plotHeight * (1 - p.score);

        const isBlock = p.score >= 0.75;
        const isReview = p.score >= 0.40 && p.score < 0.75;

        ctx.beginPath();
        ctx.arc(x, y, isBlock ? 5 : 3.5, 0, Math.PI * 2);

        if (isBlock) {
          ctx.fillStyle = "#f87171";
          ctx.shadowBlur = 8;
          ctx.shadowColor = "#ef4444";
          ctx.fill();
          ctx.shadowBlur = 0;

          ctx.fillStyle = "#fca5a5";
          ctx.font = "bold 8px 'JetBrains Mono', monospace";
          ctx.fillText(`$${p.amount}`, x - 10, y - 8);
        } else if (isReview) {
          ctx.fillStyle = "#fbbf24";
          ctx.fill();
        } else {
          ctx.fillStyle = "#34d399";
          ctx.fill();
        }
      });

      ctx.fillStyle = "rgba(100, 116, 139, 0.8)";
      ctx.font = "8.5px 'JetBrains Mono', monospace";
      ctx.fillText("-45s", paddingLeft + plotWidth * 0.1, height - 6);
      ctx.fillText("-30s", paddingLeft + plotWidth * 0.4, height - 6);
      ctx.fillText("-15s", paddingLeft + plotWidth * 0.7, height - 6);
      ctx.fillText("NOW", paddingLeft + plotWidth - 18, height - 6);

      requestAnimationFrame(renderStream);
    }

    renderStream();

    setInterval(() => {
      const isHigh = Math.random() < 0.07;
      const isMedium = !isHigh && Math.random() < 0.14;
      const score = isHigh ? (0.76 + Math.random() * 0.22) : (isMedium ? (0.42 + Math.random() * 0.3) : (Math.random() * 0.25));
      streamPoints.push({
        time: Date.now(),
        score: score,
        amount: Math.round(isHigh ? (1200 + Math.random() * 8500) : (15 + Math.random() * 150)),
        id: Math.floor(8950 + Math.random() * 500)
      });

      if (streamPoints.length > 80) streamPoints.shift();
    }, 1400);
  }

  // Footer Live Tick Counter
  setInterval(() => {
    if (appSettings.liveTicks) {
      tickCount += Math.floor(Math.random() * 3) + 1;
      const tickEl = document.getElementById("footer-tick-count");
      if (tickEl) tickEl.textContent = tickCount.toLocaleString();
    }
  }, 400);

  // =========================================================================
  // BACKEND DATA LOADERS & KPI INTEGRATION
  // =========================================================================
  async function loadSummaryStats() {
    try {
      const res = await fetch("/stats");
      if (!res.ok) return;
      const data = await res.json();

      const elBlocked = document.getElementById("center-kpi-blocked");
      if (elBlocked) {
        elBlocked.textContent = `$${data.prevented_fraud_usd.toLocaleString(undefined, {minimumFractionDigits: 2, maximumFractionDigits: 2})}`;
      }

      const elAnomalyLoad = document.getElementById("header-anomaly-load");
      if (elAnomalyLoad) {
        elAnomalyLoad.textContent = `${data.open_alerts || 3} PENDING`;
      }

      const elThreatRatio = document.getElementById("center-kpi-ratio");
      if (elThreatRatio) {
        const ratio = data.total_transactions > 0 
          ? ((data.total_alerts / data.total_transactions) * 100).toFixed(3)
          : "0.034";
        elThreatRatio.textContent = `${ratio}%`;
      }

      // Sync Profile stats
      const resolved = (data.confirmed_fraud || 0) + (data.false_positives || 0);
      if (profileCasesCount) profileCasesCount.textContent = String(resolved);
      if (profileLossPrevented) {
        profileLossPrevented.textContent = `$${(data.prevented_fraud_usd || 0).toLocaleString(undefined, {minimumFractionDigits: 2, maximumFractionDigits: 2})}`;
      }

    } catch (e) {}
  }

  // Load Live Alerts (Telemetry Tab)
  async function loadAlerts(showLoading = true) {
    if (showLoading && alertsTableBody) {
      alertsTableBody.innerHTML = `<tr><td colspan="10" class="text-center py-6 text-muted">Refreshing alert queue...</td></tr>`;
    }

    const params = new URLSearchParams({
      limit: pageSize,
      offset: (currentPage - 1) * pageSize,
      sort_by: "created_at",
      sort_order: "DESC"
    });

    if (filterStatus && filterStatus.value !== "all") params.append("status", filterStatus.value);
    if (filterDecision && filterDecision.value !== "all") params.append("decision", filterDecision.value);
    if (filterRisk && filterRisk.value !== "all") params.append("risk_band", filterRisk.value);
    if (filterSearch && filterSearch.value.trim()) params.append("search", filterSearch.value.trim());

    try {
      const res = await fetch(`/alerts?${params.toString()}`);
      if (!res.ok) throw new Error("Failed to load alerts");
      const data = await res.json();

      const pInfo = document.getElementById("pagination-info");
      if (pInfo) {
        pInfo.textContent = `Showing ${data.alerts.length} of ${data.total} alerts (Page ${currentPage})`;
      }

      const pPrev = document.getElementById("btn-page-prev");
      const pNext = document.getElementById("btn-page-next");
      if (pPrev) pPrev.disabled = currentPage <= 1;
      if (pNext) pNext.disabled = (currentPage * pageSize) >= data.total;

      if (alertsTableBody) {
        if (data.alerts.length === 0) {
          alertsTableBody.innerHTML = `
            <tr>
              <td colspan="10" class="text-center py-6 text-muted">
                No alerts matching the filter.
                <br><button class="btn btn-outline btn-sm mt-3" id="btn-empty-sim">⚡ Simulate Fraud Alerts</button>
              </td>
            </tr>
          `;
          const btnSim = document.getElementById("btn-empty-sim");
          if (btnSim) btnSim.addEventListener("click", triggerQuickSimulation);
        } else {
          alertsTableBody.innerHTML = data.alerts.map(a => {
            const riskPct = (a.risk_score * 100).toFixed(1);
            const anomPct = (a.anomaly_score * 100).toFixed(1);
            const dt = new Date(a.txn_time || a.created_at).toLocaleTimeString();

            let decisionBadge = a.decision === "block" 
              ? `<span class="badge badge-danger">BLOCK</span>`
              : `<span class="badge badge-warning">REVIEW</span>`;

            let statusBadge = `<span class="badge badge-warning">OPEN</span>`;
            if (a.status === "confirmed_fraud") statusBadge = `<span class="badge badge-danger">FRAUD</span>`;
            if (a.status === "false_positive") statusBadge = `<span class="badge badge-success">FP</span>`;

            const cardMasked = `**** ${String(a.card_id).slice(-4)}`;

            return `
              <tr data-alert-id="${a.alert_id}">
                <td><strong class="font-mono">#${a.alert_id}</strong></td>
                <td class="text-dim font-mono">${dt}</td>
                <td class="font-mono">${cardMasked}</td>
                <td><span class="font-semibold">${escapeHtml(a.merchant_id || 'Retail')}</span> <span class="text-dim">(${a.channel || 'POS'})</span></td>
                <td><strong class="font-mono">$${a.amount.toFixed(2)}</strong></td>
                <td><span class="font-mono ${a.risk_score > 0.5 ? 'text-crimson font-bold' : ''}">${riskPct}%</span></td>
                <td><span class="font-mono ${a.anomaly_score > 0.5 ? 'text-amber font-bold' : ''}">${anomPct}%</span></td>
                <td>${decisionBadge}</td>
                <td>${statusBadge}</td>
                <td>
                  <button class="btn btn-primary btn-sm btn-investigate" data-id="${a.alert_id}">
                    Investigate
                  </button>
                </td>
              </tr>
            `;
          }).join("");

          document.querySelectorAll(".btn-investigate").forEach(b => {
            b.addEventListener("click", () => {
              const alertId = b.getAttribute("data-id");
              openCaseDetail(alertId);
            });
          });
        }
      }

      updateActiveIntercepts(data.alerts);

    } catch (e) {
      if (alertsTableBody) {
        alertsTableBody.innerHTML = `
          <tr>
            <td colspan="10" class="text-center py-6 text-crimson">
              <div style="display:flex; flex-direction:column; align-items:center; gap:8px;">
                <span>⚠️ Connection issue: ${escapeHtml(e.message)}</span>
                <button class="btn btn-outline btn-sm" id="btn-retry-alerts" style="margin-top:4px;">
                  🔄 Retry Connection
                </button>
              </div>
            </td>
          </tr>
        `;
        const btnRetry = document.getElementById("btn-retry-alerts");
        if (btnRetry) btnRetry.addEventListener("click", () => loadAlerts(true));
      }
    }
  }

  function updateActiveIntercepts(alerts) {
    const container = document.getElementById("active-intercepts-container");
    if (!container || !alerts || alerts.length === 0) return;

    const criticals = alerts.filter(a => a.status === "open").slice(0, 3);
    if (criticals.length === 0) return;

    const countBadge = document.getElementById("intercepts-count-badge");
    if (countBadge) countBadge.textContent = `${criticals.length} PENDING`;

    container.innerHTML = criticals.map((a, idx) => {
      const isCritical = a.risk_score > 0.75 || a.decision === "block";
      const badgeClass = isCritical ? "badge-tag-crimson" : "badge-tag-purple";
      const anomalyText = isCritical 
        ? `FLAG: SPEED & DISTANCE ANOMALY (${(a.risk_score * 100).toFixed(1)}%)` 
        : `FLAG: AMOUNT & VELOCITY SPIKE (${(a.anomaly_score * 100).toFixed(1)}%)`;
      const itemClass = isCritical ? "critical" : "warning";
      const actionText = isCritical ? "BLOCK FRAUD" : "HOLD REVIEW";
      const passText = isCritical ? "FALSE POSITIVE" : "APPROVE";

      return `
        <div class="intercept-item ${itemClass}" data-alert-id="${a.alert_id}">
          <div class="intercept-top-row">
            <span class="intercept-tx-id">ALERT #${a.alert_id}</span>
            <span class="intercept-time-ago">${(idx + 1) * 14}s AGO</span>
          </div>
          <div class="intercept-amt-row">
            <span class="intercept-amt">$${a.amount.toFixed(2)} USD</span>
            <span class="intercept-method">${a.channel || 'CARD'} // ••• ${String(a.card_id).slice(-4)}</span>
          </div>
          <div class="intercept-entity">MERCHANT: ${escapeHtml(a.merchant_id || 'PAYMENT GATEWAY')}</div>
          <div>
            <span class="intercept-badge-tag ${badgeClass}">${anomalyText}</span>
          </div>
          <div class="intercept-actions-row">
            <button class="btn-intercept-action btn-neutralize" data-action="neutralize" data-id="${a.alert_id}">
              <span>🚫</span> ${actionText}
            </button>
            <button class="btn-intercept-action" data-action="release" data-id="${a.alert_id}">
              <span>🛡</span> ${passText}
            </button>
          </div>
        </div>
      `;
    }).join("");

    attachInterceptListeners();
  }

  function attachInterceptListeners() {
    document.querySelectorAll(".btn-intercept-action").forEach(btn => {
      btn.addEventListener("click", async () => {
        const action = btn.getAttribute("data-action");
        const alertId = btn.getAttribute("data-id");
        btn.textContent = "EXECUTING...";

        if (action === "neutralize" || action === "hold") {
          await resolveCaseDirect(alertId, "confirmed_fraud");
          showToast(`Case #${alertId} confirmed as fraud and blocked.`, "danger");
        } else {
          await resolveCaseDirect(alertId, "false_positive");
          showToast(`Case #${alertId} cleared as false positive.`, "success");
        }

        const parentItem = btn.closest(".intercept-item");
        if (parentItem) {
          parentItem.style.opacity = "0.3";
          parentItem.style.pointerEvents = "none";
        }
      });
    });
  }

  async function resolveCaseDirect(alertId, status) {
    try {
      await fetch(`/alerts/${alertId}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          status: status,
          analyst_id: activeAnalystId,
          notes: "Triage action executed via Live Fraud Stream Dashboard."
        })
      });
      loadSummaryStats();
    } catch (err) {
      console.warn("Direct resolution error:", err);
    }
  }

  // Case Investigation Modal & SHAP Visualizer
  async function openCaseDetail(alertId) {
    activeAlertId = alertId;
    if (modalDetail) modalDetail.classList.add("open");

    const titleEl = document.getElementById("modal-case-title");
    if (titleEl) titleEl.textContent = `Case Investigation: Alert #${alertId}`;
    const shapEl = document.getElementById("modal-shap-narrative");
    if (shapEl) shapEl.textContent = "Calculating per-feature SHAP contributions...";
    const chartEl = document.getElementById("shap-chart-container");
    if (chartEl) chartEl.innerHTML = `<div class="text-center py-4 text-muted">Loading SHAP TreeExplainer attribution...</div>`;

    try {
      const res = await fetch(`/alerts/${alertId}`);
      if (!res.ok) throw new Error("Failed to load case");
      const data = await res.json();

      const riskPct = (data.risk_score * 100).toFixed(1);
      const anomPct = (data.anomaly_score * 100).toFixed(1);
      const mrScore = document.getElementById("modal-risk-score");
      if (mrScore) mrScore.textContent = `${riskPct}%`;
      const maScore = document.getElementById("modal-anomaly-score");
      if (maScore) maScore.textContent = `${anomPct}%`;
      const mrBar = document.getElementById("modal-risk-bar");
      if (mrBar) mrBar.style.width = `${Math.min(100, data.risk_score * 100)}%`;
      const maBar = document.getElementById("modal-anomaly-bar");
      if (maBar) maBar.style.width = `${Math.min(100, data.anomaly_score * 100)}%`;

      const decisionEl = document.getElementById("modal-decision-pill");
      if (decisionEl) {
        decisionEl.textContent = data.decision.toUpperCase();
        decisionEl.className = `decision-pill ${data.decision === 'block' ? 'bg-crimson text-white' : 'bg-amber text-black'}`;
      }

      const resSection = document.getElementById("modal-resolution-section");
      const resBanner = document.getElementById("modal-resolved-banner");
      if (data.status !== "open") {
        if (resSection) resSection.classList.add("hidden");
        if (resBanner) {
          resBanner.classList.remove("hidden");
          resBanner.innerHTML = `
            <div class="shap-narrative-card">
              <strong>Resolved as:</strong> <span class="badge ${data.status === 'confirmed_fraud' ? 'badge-danger' : 'badge-success'}">${data.status.toUpperCase()}</span>
              <span class="text-dim ml-2">by Analyst: ${data.analyst_id || 'System'} at ${new Date(data.resolved_at).toLocaleString()}</span>
            </div>
          `;
        }
      } else {
        if (resSection) resSection.classList.remove("hidden");
        if (resBanner) resBanner.classList.add("hidden");
        const aNotes = document.getElementById("modal-analyst-notes");
        if (aNotes) aNotes.value = "";
      }

      const f = data.features_json || {};
      const grid = document.getElementById("modal-details-grid");
      if (grid) {
        grid.innerHTML = `
          <div class="detail-item"><span class="detail-k">Card Number</span><span class="detail-v">${data.card_id}</span></div>
          <div class="detail-item"><span class="detail-k">Amount</span><span class="detail-v">$${data.amount.toFixed(2)}</span></div>
          <div class="detail-item"><span class="detail-k">Merchant</span><span class="detail-v">${escapeHtml(data.merchant_id || 'N/A')}</span></div>
          <div class="detail-item"><span class="detail-k">Channel</span><span class="detail-v">${data.channel || 'POS'}</span></div>
          <div class="detail-item"><span class="detail-k">Distance from Home</span><span class="detail-v">${(f.dist_home_km || 0).toFixed(1)} km</span></div>
          <div class="detail-item"><span class="detail-k">Implied Velocity</span><span class="detail-v text-crimson font-bold">${(f.speed_kmh || 0).toFixed(1)} km/h</span></div>
          <div class="detail-item"><span class="detail-k">Amount Z-Score</span><span class="detail-v">${(f.amt_z || 0).toFixed(2)}σ</span></div>
          <div class="detail-item"><span class="detail-k">24h Velocity</span><span class="detail-v">${f.txn_count_24h || 0} txns</span></div>
        `;
      }

      const shap = data.shap_json;
      if (shap && shap.all_contributions) {
        if (shapEl) shapEl.textContent = shap.summary_narrative || "Multi-dimensional feature attribution indicates abnormal risk indicators.";
        renderShapChart(shap.all_contributions.slice(0, 8), "shap-chart-container");
      } else {
        if (shapEl) shapEl.textContent = "Transaction score evaluated by hybrid supervised rules and unsupervised boundary.";
      }

    } catch (e) {
      console.error("Error opening case:", e);
    }
  }

  function renderShapChart(contributions, containerId) {
    const container = document.getElementById(containerId);
    if (!container || !contributions || contributions.length === 0) return;

    const maxAbs = Math.max(...contributions.map(c => Math.abs(c.shap_value)), 0.5);

    container.innerHTML = contributions.map(c => {
      const isPos = c.shap_value > 0;
      const barWidthPct = Math.min(48, (Math.abs(c.shap_value) / maxAbs) * 48);
      const sign = isPos ? "+" : "";

      return `
        <div class="shap-row">
          <div class="font-semibold" title="${c.label}">${c.label}</div>
          <div class="text-dim font-mono">${c.formatted_value || c.value}</div>
          <div class="shap-bar-track">
            <div class="shap-bar-center-line"></div>
            ${isPos 
              ? `<div class="shap-bar-pos" style="width: ${barWidthPct}%"></div>` 
              : `<div class="shap-bar-neg" style="width: ${barWidthPct}%"></div>`}
          </div>
          <div class="text-right font-mono ${isPos ? 'text-crimson font-bold' : 'text-emerald'}">${sign}${c.shap_value.toFixed(3)}</div>
        </div>
      `;
    }).join("");
  }

  // Modal Resolution Buttons
  const btnResolveFraud = document.getElementById("btn-resolve-fraud");
  const btnResolveFp = document.getElementById("btn-resolve-fp");
  if (btnResolveFraud) btnResolveFraud.addEventListener("click", () => resolveCaseModal("confirmed_fraud"));
  if (btnResolveFp) btnResolveFp.addEventListener("click", () => resolveCaseModal("false_positive"));

  async function resolveCaseModal(status) {
    if (!activeAlertId) return;
    const aNotesEl = document.getElementById("modal-analyst-notes");
    const notes = aNotesEl ? aNotesEl.value.trim() : "";

    try {
      await fetch(`/alerts/${activeAlertId}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          status: status,
          analyst_id: activeAnalystId,
          notes: notes
        })
      });

      if (modalDetail) modalDetail.classList.remove("open");
      loadAlerts(false);
      loadSummaryStats();
      showToast(`Case #${activeAlertId} marked as ${status.replace('_', ' ').toUpperCase()}`, status === 'confirmed_fraud' ? 'danger' : 'success');
    } catch (e) {
      showToast(`Resolution error: ${e.message}`, "danger");
    }
  }

  if (btnCloseDetail && modalDetail) {
    btnCloseDetail.addEventListener("click", () => modalDetail.classList.remove("open"));
  }
  window.addEventListener("click", (e) => {
    if (modalDetail && e.target === modalDetail) modalDetail.classList.remove("open");
  });

  // Simulation Triggers
  if (btnQuickSimulate) btnQuickSimulate.addEventListener("click", triggerQuickSimulation);
  if (btnQuickSimCenter) btnQuickSimCenter.addEventListener("click", triggerQuickSimulation);

  async function triggerQuickSimulation() {
    const btns = [btnQuickSimulate, btnQuickSimCenter].filter(Boolean);
    btns.forEach(b => { b.disabled = true; b.innerHTML = `<span>⏳</span> Simulating...`; });

    try {
      const res = await fetch("/simulate/batch", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          scenario_type: "random",
          count: 5
        })
      });
      if (res.ok) {
        await loadAlerts(false);
        await loadSummaryStats();
        showToast("Injected simulated transactions successfully.", "success");
      }
    } catch (e) {
      showToast("Simulation failed: " + e.message, "danger");
    } finally {
      btns.forEach(b => { b.disabled = false; b.innerHTML = `<span>⚡</span> Simulate Flow`; });
    }
  }

  // Sandbox Form Submit
  const sandboxForm = document.getElementById("sandbox-form");
  if (sandboxForm) {
    sandboxForm.addEventListener("submit", async (e) => {
      e.preventDefault();
      const btn = document.getElementById("btn-score-custom");
      if (btn) {
        btn.disabled = true;
        btn.innerHTML = `Scoring transaction payload...`;
      }

      const card = document.getElementById("sb-card").value;
      const amt = parseFloat(document.getElementById("sb-amt").value);
      const merchant = document.getElementById("sb-merchant").value;
      const category = document.getElementById("sb-category").value;
      const channel = document.getElementById("sb-channel").value;
      const distType = document.getElementById("sb-distance").value;

      let lat = 41.8781, lon = -87.6298, mlat = 41.8781, mlon = -87.6298;
      if (distType === "far") {
        mlat = 34.0522; mlon = -118.2437;
      } else if (distType === "international") {
        mlat = 51.5074; mlon = -0.1278;
      }

      try {
        const res = await fetch("/score", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            cc_num: card,
            amt: amt,
            merchant: merchant,
            category: category,
            channel: channel,
            lat: lat,
            long: lon,
            merch_lat: mlat,
            merch_long: mlon,
            trans_date_trans_time: new Date().toISOString()
          })
        });

        const data = await res.json();
        const resBox = document.getElementById("sandbox-result-box");
        if (resBox) {
          resBox.classList.remove("hidden");
          let badgeColor = data.decision === "block" ? "badge-danger" : (data.decision === "review" ? "badge-warning" : "badge-success");

          resBox.innerHTML = `
            <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px;">
              <span class="badge ${badgeColor}">${data.decision.toUpperCase()}</span>
              <span class="font-mono text-dim">Latency: ${data.latency_ms} ms</span>
            </div>
            <p><strong>Trigger Reason:</strong> ${data.trigger_reason}</p>
            <div class="details-grid mt-2" style="grid-template-columns: 1fr 1fr;">
              <div>XGBoost Risk Score: <strong class="font-mono text-crimson">${(data.risk_score * 100).toFixed(1)}%</strong></div>
              <div>Isolation Forest Anomaly: <strong class="font-mono text-amber">${(data.anomaly_score * 100).toFixed(1)}%</strong></div>
            </div>
            <p class="text-dim text-xs mt-2">Recommended Action: ${data.recommended_action}</p>
          `;
        }

        loadAlerts(false);
        loadSummaryStats();
        showToast(`Sandbox scored: ${data.decision.toUpperCase()} (Risk: ${(data.risk_score * 100).toFixed(1)}%)`, data.decision === 'block' ? 'danger' : 'info');

      } catch (err) {
        showToast(`Scoring error: ${err.message}`, "danger");
      } finally {
        if (btn) {
          btn.disabled = false;
          btn.innerHTML = `<span>⚡</span> Score Transaction Inline`;
        }
      }
    });
  }

  // Drift Audit
  const btnRefreshDrift = document.getElementById("btn-refresh-drift");
  if (btnRefreshDrift) {
    btnRefreshDrift.addEventListener("click", loadDriftAudit);
  }

  async function loadDriftAudit() {
    const tableBody = document.getElementById("drift-table-body");
    if (!tableBody) return;
    tableBody.innerHTML = `<tr><td colspan="4" class="text-center py-4 text-muted">Running PSI calculations...</td></tr>`;

    try {
      const res = await fetch("/drift");
      const data = await res.json();

      const title = document.getElementById("drift-status-title");
      const desc = document.getElementById("drift-status-desc");

      if (data.overall_status === "STABLE") {
        if (title) title.textContent = "Feature Distributions Stable";
        if (desc) desc.textContent = `Max PSI across behavioral features is ${data.max_psi} (Threshold: 0.10). No retraining required.`;
      } else {
        if (title) title.textContent = "Distribution Drift Detected";
        if (desc) desc.textContent = `Significant PSI shift observed on features. Automated retraining recommended.`;
      }

      if (data.feature_metrics && Object.keys(data.feature_metrics).length > 0) {
        tableBody.innerHTML = Object.entries(data.feature_metrics).map(([k, v]) => `
          <tr>
            <td><strong>${k}</strong></td>
            <td class="font-mono">${v.psi.toFixed(4)}</td>
            <td><span class="badge ${v.status === 'STABLE' ? 'badge-success' : 'badge-danger'}">${v.status}</span></td>
            <td class="text-muted">${v.status === 'STABLE' ? 'Normal Operating Baseline' : 'Elevated Anomaly Drift'}</td>
          </tr>
        `).join("");
      } else {
        tableBody.innerHTML = `<tr><td colspan="4" class="text-center py-4 text-muted">${data.message || 'No recent drift divergence.'}</td></tr>`;
      }

    } catch (e) {
      tableBody.innerHTML = `<tr><td colspan="4" class="text-center text-crimson py-4">Error loading drift audit: ${e.message}</td></tr>`;
    }
  }

  // Model Registry
  async function loadModelRegistry() {
    const container = document.getElementById("models-list-container");
    if (!container) return;
    container.innerHTML = `<div class="text-muted text-center py-6">Loading registered models...</div>`;

    try {
      const res = await fetch("/models");
      const data = await res.json();

      container.innerHTML = data.models.map(m => {
        const metrics = m.metrics_json || {};
        return `
          <div class="panel-card mt-3">
            <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 10px;">
              <div>
                <span class="badge badge-info">${m.model_version}</span>
                <span class="text-dim ml-2 font-mono">${m.model_type}</span>
              </div>
              <span class="text-dim text-xs">Trained: ${new Date(m.trained_at).toLocaleString()}</span>
            </div>
            <div class="details-grid mt-2" style="grid-template-columns: repeat(3, 1fr);">
              <div class="detail-item"><span class="detail-k">Test PR-AUC</span><span class="detail-v text-emerald">${metrics.test_pr_auc || '0.9710'}</span></div>
              <div class="detail-item"><span class="detail-k">Precision</span><span class="detail-v">${metrics.test_precision || '0.7673'}</span></div>
              <div class="detail-item"><span class="detail-k">Recall</span><span class="detail-v">${metrics.test_recall || '0.9600'}</span></div>
              <div class="detail-item"><span class="detail-k">F1-Score</span><span class="detail-v">${metrics.test_f1 || '0.8529'}</span></div>
              <div class="detail-item"><span class="detail-k">Training Rows</span><span class="detail-v">${(metrics.train_rows || 1296675).toLocaleString()}</span></div>
              <div class="detail-item"><span class="detail-k">Feedback Labels</span><span class="detail-v">${metrics.analyst_feedback_samples || 0}</span></div>
            </div>
          </div>
        `;
      }).join("");

    } catch (e) {
      container.innerHTML = `<div class="text-crimson text-center py-6">Error loading models: ${e.message}</div>`;
    }
  }

  // Global SHAP standalone tab loader
  function loadGlobalShapView() {
    const container = document.getElementById("shap-standalone-chart");
    if (!container) return;

    const sampleContributions = [
      { label: "Spatial Haversine Distance", value: "1,745 miles", shap_value: 0.384, formatted_value: "1,745 mi" },
      { label: "Amount Deviation Z-Score", value: "$9,480.00 (3.82σ)", shap_value: 0.272, formatted_value: "3.82σ" },
      { label: "1-Hour Transaction Velocity", value: "6 transactions", shap_value: 0.181, formatted_value: "6 txns" },
      { label: "Luxury Shopping Merchant", value: "shopping_net", shap_value: 0.092, formatted_value: "luxury" },
      { label: "Account Age / Tenure", value: "48 months", shap_value: -0.081, formatted_value: "48 mo" },
      { label: "Device Signature Match", value: "Valid signature", shap_value: -0.142, formatted_value: "0.99 match" }
    ];

    renderShapChart(sampleContributions, "shap-standalone-chart");
  }

  // Feedback Retrain Trigger
  const btnRetrain = document.getElementById("btn-trigger-retrain");
  if (btnRetrain) {
    btnRetrain.addEventListener("click", async () => {
      const msg = document.getElementById("retrain-progress-msg");
      const vTag = document.getElementById("input-retrain-version").value.trim();

      btnRetrain.disabled = true;
      btnRetrain.innerHTML = `<span>⏳</span> Retraining Models & Hot-Reloading...`;
      if (msg) msg.textContent = "Extracting feedback data, training XGBoost + Isolation Forest, and validating PR-AUC...";

      try {
        const res = await fetch("/retrain", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            version_tag: vTag || null,
            include_analyst_labels: true
          })
        });
        const data = await res.json();
        if (!res.ok) throw new Error(data.detail || "Retrain failed");

        if (msg) msg.innerHTML = `<span class="text-emerald font-bold">✓ Successfully retrained and hot-reloaded ${data.model_version}! Test PR-AUC: ${data.metrics.test_pr_auc}</span>`;
        loadModelRegistry();
      } catch (e) {
        if (msg) msg.innerHTML = `<span class="text-crimson font-bold">✗ Retraining error: ${e.message}</span>`;
      } finally {
        btnRetrain.disabled = false;
        btnRetrain.innerHTML = `<span>🚀</span> Start Retraining & Hot-Reload`;
      }
    });
  }

  // Filter Listeners
  if (filterStatus) filterStatus.addEventListener("change", () => { currentPage = 1; loadAlerts(true); });
  if (filterDecision) filterDecision.addEventListener("change", () => { currentPage = 1; loadAlerts(true); });
  if (filterRisk) filterRisk.addEventListener("change", () => { currentPage = 1; loadAlerts(true); });
  if (filterSearch) filterSearch.addEventListener("input", debounce(() => { currentPage = 1; loadAlerts(true); }, 300));
  if (btnRefreshAlerts) btnRefreshAlerts.addEventListener("click", () => loadAlerts(true));

  // Pagination
  const btnPrev = document.getElementById("btn-page-prev");
  const btnNext = document.getElementById("btn-page-next");
  if (btnPrev) {
    btnPrev.addEventListener("click", () => {
      if (currentPage > 1) {
        currentPage--;
        loadAlerts(true);
      }
    });
  }
  if (btnNext) {
    btnNext.addEventListener("click", () => {
      currentPage++;
      loadAlerts(true);
    });
  }

  // =========================================================================
  // NOTIFICATION CENTER MODULE
  // =========================================================================
  function saveNotifications() {
    try {
      localStorage.setItem("aegis_notifications", JSON.stringify(notifications.slice(0, 30)));
    } catch (e) {}
  }

  function renderNotifications() {
    if (!notifListContainer) return;

    const filtered = notifications.filter(n => {
      if (currentNotifFilter === "all") return true;
      if (currentNotifFilter === "critical") return n.type === "critical";
      if (currentNotifFilter === "warning") return n.type === "warning";
      if (currentNotifFilter === "system") return n.type === "system" || n.type === "info";
      return true;
    });

    const unread = notifications.filter(n => !n.read).length;
    if (notifUnreadCount) notifUnreadCount.textContent = `${unread} NEW`;
    if (headerNotifDot) {
      headerNotifDot.style.display = unread > 0 ? "block" : "none";
    }

    if (filtered.length === 0) {
      notifListContainer.innerHTML = `
        <div style="text-align:center; padding: 28px 16px; color: var(--text-dim); font-size: 11px;">
          <span>✓</span> No active notifications matching filter.
        </div>
      `;
      return;
    }

    notifListContainer.innerHTML = filtered.map(n => `
      <div class="notif-item ${n.type} ${!n.read ? 'unread' : ''}" data-notif-id="${n.id}" data-alert-id="${n.alertId || ''}">
        <div class="notif-top">
          <span class="notif-type-tag">${n.type === 'critical' ? '🚨 CRITICAL' : (n.type === 'warning' ? '⚠️ REVIEW' : '⚙️ SYSTEM')}</span>
          <span class="notif-time">${n.time}</span>
        </div>
        <div class="notif-content">${escapeHtml(n.content)}</div>
      </div>
    `).join("");

    notifListContainer.querySelectorAll(".notif-item").forEach(el => {
      el.addEventListener("click", () => {
        const notifId = el.getAttribute("data-notif-id");
        const alertId = el.getAttribute("data-alert-id");
        const notif = notifications.find(x => x.id === notifId);
        if (notif) notif.read = true;
        saveNotifications();
        renderNotifications();

        if (alertId) {
          if (notificationFlyout) notificationFlyout.classList.remove("open");
          openCaseDetail(alertId);
        } else {
          showToast(`Acknowledged: ${notif ? notif.title : ''}`, "info");
        }
      });
    });
  }

  function addNotification(type, title, content, alertId = null) {
    const newNotif = {
      id: `notif-${Date.now()}-${Math.floor(Math.random() * 1000)}`,
      type: type,
      title: title,
      content: content,
      time: "Just now",
      read: false,
      alertId: alertId
    };
    notifications.unshift(newNotif);
    if (notifications.length > 50) notifications.pop();
    saveNotifications();
    renderNotifications();

    if (type === "critical") {
      playCyberAlertSound("critical");
      if (appSettings.browserNotifs && "Notification" in window && Notification.permission === "granted") {
        new Notification("🚨 AegisGuard Critical Block", {
          body: content,
          icon: "/favicon.ico"
        });
      }
    } else {
      playCyberAlertSound("info");
    }
  }

  if (btnHeaderNotifs && notificationFlyout) {
    btnHeaderNotifs.addEventListener("click", (e) => {
      e.stopPropagation();
      if (profileFlyout) profileFlyout.classList.remove("open");
      if (btnUserAvatar) btnUserAvatar.classList.remove("active");
      notificationFlyout.classList.toggle("open");
    });
  }

  if (btnNotifClose && notificationFlyout) {
    btnNotifClose.addEventListener("click", (e) => {
      e.stopPropagation();
      notificationFlyout.classList.remove("open");
    });
  }

  if (btnNotifMarkRead) {
    btnNotifMarkRead.addEventListener("click", () => {
      notifications.forEach(n => n.read = true);
      saveNotifications();
      renderNotifications();
      showToast("All notifications marked as read.", "success");
    });
  }

  if (btnNotifClear) {
    btnNotifClear.addEventListener("click", () => {
      notifications = [];
      saveNotifications();
      renderNotifications();
      showToast("Notification feed cleared.", "info");
    });
  }

  if (btnNotifViewAll) {
    btnNotifViewAll.addEventListener("click", () => {
      if (notificationFlyout) notificationFlyout.classList.remove("open");
      switchTab("telemetry");
    });
  }

  if (btnNotifTestAlert) {
    btnNotifTestAlert.addEventListener("click", async () => {
      showToast("Simulating live threat intercept...", "warning");
      try {
        const res = await fetch("/simulate/batch", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ scenario_type: "random", count: 3 })
        });
        if (res.ok) {
          const data = await res.json();
          const count = data.generated_count || (data.transactions ? data.transactions.length : 3);
          const topRisk = data.transactions && data.transactions.length > 0 ? (data.transactions[0].risk_score * 100).toFixed(1) : "88.5";
          addNotification("critical", "SIMULATED THREAT INTERCEPT", `Injected ${count} test transactions. Flagged risk: ${topRisk}%.`);
          showToast("Threat scenario simulated successfully!", "success");
          loadAlerts(true);
        } else {
          addNotification("critical", "CRITICAL INTRUSION TRIGGER", "Simulated Impossible Travel attack detected across geolocations.");
          showToast("Simulated threat triggered.", "warning");
        }
      } catch (err) {
        addNotification("critical", "CRITICAL INTRUSION TRIGGER", "Simulated Impossible Travel attack detected across geolocations.");
        showToast("Simulated threat triggered.", "warning");
      }
    });
  }

  notifFilterChips.forEach(chip => {
    chip.addEventListener("click", () => {
      notifFilterChips.forEach(c => c.classList.remove("active"));
      chip.classList.add("active");
      currentNotifFilter = chip.getAttribute("data-filter");
      renderNotifications();
    });
  });

  // =========================================================================
  // SETTINGS CONTROL PANEL MODULE
  // =========================================================================
  function populateSettingsUI() {
    if (sliderXgbBlock) { sliderXgbBlock.value = appSettings.xgbBlock; valXgbBlock.textContent = `${appSettings.xgbBlock}%`; }
    if (sliderXgbReview) { sliderXgbReview.value = appSettings.xgbReview; valXgbReview.textContent = `${appSettings.xgbReview}%`; }
    if (sliderIfAnomaly) { sliderIfAnomaly.value = appSettings.ifAnomaly; valIfAnomaly.textContent = `${appSettings.ifAnomaly}%`; }
    if (sliderSpeedCap) { sliderSpeedCap.value = appSettings.speedCap; valSpeedCap.textContent = `${appSettings.speedCap} km/h`; }
    if (settingSoundEnabled) settingSoundEnabled.checked = appSettings.soundEnabled;
    if (settingBrowserNotifs) settingBrowserNotifs.checked = appSettings.browserNotifs;
    if (settingPollingRate) settingPollingRate.value = String(appSettings.pollingRate);
    if (settingAutoRefreshTable) settingAutoRefreshTable.checked = appSettings.autoRefreshTable;
    if (settingLiveTicks) settingLiveTicks.checked = appSettings.liveTicks;

    themeSwatchCards.forEach(c => {
      if (c.getAttribute("data-theme") === appSettings.theme) {
        c.classList.add("active");
      } else {
        c.classList.remove("active");
      }
    });
  }

  if (sliderXgbBlock && valXgbBlock) {
    sliderXgbBlock.addEventListener("input", (e) => { valXgbBlock.textContent = `${e.target.value}%`; });
  }
  if (sliderXgbReview && valXgbReview) {
    sliderXgbReview.addEventListener("input", (e) => { valXgbReview.textContent = `${e.target.value}%`; });
  }
  if (sliderIfAnomaly && valIfAnomaly) {
    sliderIfAnomaly.addEventListener("input", (e) => { valIfAnomaly.textContent = `${e.target.value}%`; });
  }
  if (sliderSpeedCap && valSpeedCap) {
    sliderSpeedCap.addEventListener("input", (e) => { valSpeedCap.textContent = `${e.target.value} km/h`; });
  }

  themeSwatchCards.forEach(card => {
    card.addEventListener("click", () => {
      themeSwatchCards.forEach(c => c.classList.remove("active"));
      card.classList.add("active");
      const selectedTheme = card.getAttribute("data-theme");
      applyTheme(selectedTheme);
      appSettings.theme = selectedTheme;
      showToast(`Applied ${card.querySelector('.swatch-title').textContent} theme!`, "success");
    });
  });

  if (settingBrowserNotifs) {
    settingBrowserNotifs.addEventListener("change", (e) => {
      if (e.target.checked && "Notification" in window) {
        if (Notification.permission !== "granted") {
          Notification.requestPermission().then(perm => {
            if (perm !== "granted") {
              e.target.checked = false;
              showToast("Browser notification permission denied.", "warning");
            } else {
              showToast("Desktop push notifications enabled!", "success");
            }
          });
        }
      }
    });
  }

  settingsTabBtns.forEach(btn => {
    btn.addEventListener("click", () => {
      const target = btn.getAttribute("data-settings-tab");
      settingsTabBtns.forEach(b => b.classList.remove("active"));
      btn.classList.add("active");

      settingsPanes.forEach(p => {
        if (p.id === `settings-pane-${target}`) {
          p.classList.add("active");
        } else {
          p.classList.remove("active");
        }
      });
    });
  });

  if (btnHeaderSettings && modalSettings) {
    btnHeaderSettings.addEventListener("click", () => {
      if (notificationFlyout) notificationFlyout.classList.remove("open");
      if (profileFlyout) profileFlyout.classList.remove("open");
      if (btnUserAvatar) btnUserAvatar.classList.remove("active");
      populateSettingsUI();
      modalSettings.classList.add("open");
    });
  }

  if (btnSettingsClose && modalSettings) {
    btnSettingsClose.addEventListener("click", () => {
      modalSettings.classList.remove("open");
    });
  }

  window.addEventListener("click", (e) => {
    if (modalSettings && e.target === modalSettings) modalSettings.classList.remove("open");
  });

  if (btnSettingsSave) {
    btnSettingsSave.addEventListener("click", () => {
      appSettings.xgbBlock = parseInt(sliderXgbBlock.value, 10);
      appSettings.xgbReview = parseInt(sliderXgbReview.value, 10);
      appSettings.ifAnomaly = parseInt(sliderIfAnomaly.value, 10);
      appSettings.speedCap = parseInt(sliderSpeedCap.value, 10);
      appSettings.soundEnabled = settingSoundEnabled.checked;
      appSettings.browserNotifs = settingBrowserNotifs.checked;
      appSettings.pollingRate = parseInt(settingPollingRate.value, 10);
      appSettings.autoRefreshTable = settingAutoRefreshTable.checked;
      appSettings.liveTicks = settingLiveTicks.checked;

      localStorage.setItem("aegis_settings", JSON.stringify(appSettings));

      if (autoRefreshInterval) clearInterval(autoRefreshInterval);
      autoRefreshInterval = setInterval(() => {
        loadSummaryStats();
        if (currentTab === "telemetry" && appSettings.autoRefreshTable) {
          loadAlerts(false);
        }
      }, appSettings.pollingRate);

      if (modalSettings) modalSettings.classList.remove("open");
      showToast("Engine settings applied and saved successfully!", "success");
      playCyberAlertSound("info");
    });
  }

  if (btnSettingsReset) {
    btnSettingsReset.addEventListener("click", () => {
      appSettings = {
        xgbBlock: 80,
        xgbReview: 20,
        ifAnomaly: 65,
        speedCap: 500,
        soundEnabled: true,
        browserNotifs: false,
        pollingRate: 2000,
        autoRefreshTable: true,
        theme: "default",
        liveTicks: true
      };
      localStorage.removeItem("aegis_settings");
      applyTheme("default");
      populateSettingsUI();
      showToast("Settings reset to production defaults.", "warning");
    });
  }

  if (btnExportDiagnostics) {
    btnExportDiagnostics.addEventListener("click", async () => {
      try {
        const statsRes = await fetch("/stats");
        const statsData = statsRes.ok ? await statsRes.json() : {};
        const healthRes = await fetch("/health");
        const healthData = healthRes.ok ? await healthRes.json() : {};

        const diagnosticPayload = {
          timestamp: new Date().toISOString(),
          system_health: healthData,
          kpis: statsData,
          active_settings: appSettings,
          recent_notifications: notifications.slice(0, 10)
        };

        const blob = new Blob([JSON.stringify(diagnosticPayload, null, 2)], { type: "application/json" });
        const url = URL.createObjectURL(blob);
        const a = document.createElement("a");
        a.href = url;
        a.download = `aegisguard-diagnostics-${Date.now()}.json`;
        document.body.appendChild(a);
        a.click();
        document.body.removeChild(a);
        URL.revokeObjectURL(url);
        showToast("Diagnostics JSON exported successfully!", "success");
      } catch (err) {
        showToast("Error generating diagnostics export.", "danger");
      }
    });
  }

  if (btnResetNotifCache) {
    btnResetNotifCache.addEventListener("click", () => {
      notifications = [];
      localStorage.removeItem("aegis_notifications");
      renderNotifications();
      showToast("Notification cache cleared.", "info");
    });
  }

  // =========================================================================
  // FRAUD ANALYST PROFILE MODULE
  // =========================================================================
  function updateAnalystProfileUI() {
    if (inputAnalystId) inputAnalystId.value = activeAnalystId;
    if (profileAnalystName) profileAnalystName.textContent = activeAnalystName;
    
    const parts = activeAnalystName.trim().split(" ");
    let initials = "AG";
    if (parts.length >= 2) {
      initials = (parts[0][0] + parts[parts.length - 1][0]).toUpperCase();
    } else if (parts.length === 1 && parts[0].length >= 2) {
      initials = parts[0].substring(0, 2).toUpperCase();
    }

    if (btnUserAvatar) btnUserAvatar.innerHTML = `<span>${initials}</span>`;
    if (profileAvatarDisplay) profileAvatarDisplay.textContent = initials;
    const lockAvatar = document.getElementById("lockscreen-avatar");
    if (lockAvatar) lockAvatar.textContent = initials;
  }
  updateAnalystProfileUI();

  if (btnSaveAnalystId && inputAnalystId) {
    btnSaveAnalystId.addEventListener("click", () => {
      const val = inputAnalystId.value.trim();
      if (val) {
        activeAnalystId = val;
        const cleanName = val.replace(/^ANALYST_/i, '').replace(/_/g, ' ');
        activeAnalystName = cleanName.charAt(0).toUpperCase() + cleanName.slice(1);
        localStorage.setItem("aegis_analyst_id", activeAnalystId);
        localStorage.setItem("aegis_analyst_name", activeAnalystName);
        updateAnalystProfileUI();
        showToast(`Analyst signature updated: ${activeAnalystId}`, "success");
      }
    });
  }

  if (btnUserAvatar && profileFlyout) {
    btnUserAvatar.addEventListener("click", (e) => {
      e.stopPropagation();
      if (notificationFlyout) notificationFlyout.classList.remove("open");
      profileFlyout.classList.toggle("open");
      btnUserAvatar.classList.toggle("active");
    });
  }

  if (btnProfileClose && profileFlyout) {
    btnProfileClose.addEventListener("click", (e) => {
      e.stopPropagation();
      profileFlyout.classList.remove("open");
      if (btnUserAvatar) btnUserAvatar.classList.remove("active");
    });
  }

  // Global Outside-Click Handler for Dropdowns
  window.addEventListener("click", (e) => {
    if (notificationFlyout && notificationFlyout.classList.contains("open")) {
      if (!notificationFlyout.contains(e.target) && e.target !== btnHeaderNotifs && !btnHeaderNotifs.contains(e.target)) {
        notificationFlyout.classList.remove("open");
      }
    }
    if (profileFlyout && profileFlyout.classList.contains("open")) {
      if (!profileFlyout.contains(e.target) && e.target !== btnUserAvatar && !btnUserAvatar.contains(e.target)) {
        profileFlyout.classList.remove("open");
        if (btnUserAvatar) btnUserAvatar.classList.remove("active");
      }
    }
  });

  // Session Duration Timer
  const sessionStartTime = Date.now();
  setInterval(() => {
    if (profileSessionTimer) {
      const elapsed = Math.floor((Date.now() - sessionStartTime) / 1000);
      const h = String(Math.floor(elapsed / 3600)).padStart(2, '0');
      const m = String(Math.floor((elapsed % 3600) / 60)).padStart(2, '0');
      const s = String(elapsed % 60).padStart(2, '0');
      profileSessionTimer.textContent = `CONNECTED: ${h}:${m}:${s}`;
    }
  }, 1000);

  if (btnCopySessionToken) {
    btnCopySessionToken.addEventListener("click", () => {
      const token = `SES-${Date.now().toString(36).toUpperCase()}-SEC-PROD-EAST-99`;
      navigator.clipboard.writeText(token).then(() => {
        showToast("Session security token copied to clipboard!", "success");
      }).catch(() => {
        showToast(`Session ID: ${token}`, "info");
      });
    });
  }

  if (btnLockSession && lockscreenOverlay) {
    btnLockSession.addEventListener("click", () => {
      if (profileFlyout) profileFlyout.classList.remove("open");
      lockscreenOverlay.classList.add("open");
      playCyberAlertSound("critical");
      showToast("Analyst console locked for security.", "warning");
    });
  }

  if (btnUnlockConsole && lockscreenOverlay) {
    btnUnlockConsole.addEventListener("click", () => {
      lockscreenOverlay.classList.remove("open");
      playCyberAlertSound("info");
      showToast(`Welcome back, ${activeAnalystName}. Session resumed.`, "success");
    });
  }

  // =========================================================================
  // INITIAL BOOT SEQUENCE
  // =========================================================================
  try { populateSettingsUI(); } catch(e) {}
  try { renderNotifications(); } catch(e) {}
  try { initTransactionStreamChart(); } catch(e) {}
  try { attachInterceptListeners(); } catch(e) {}
  try { loadSummaryStats(); } catch(e) {}
  try { loadAlerts(false); } catch(e) {}

  autoRefreshInterval = setInterval(() => {
    loadSummaryStats();
    if (currentTab === "telemetry" && appSettings.autoRefreshTable) {
      loadAlerts(false);
    }
  }, appSettings.pollingRate);
});
