// Vriddhi Research Desk - Terminal UI Logic

document.addEventListener("DOMContentLoaded", () => {
  // State
  let analystsList = [];
  let currentAnalystId = "rahul";
  let companiesList = [];

  // Topbar Elements
  const topbarClock = document.getElementById("topbar-ist-clock");
  const btnTriggerCrawl = document.getElementById("btn-trigger-crawl");
  const crawlerStatusBadge = document.getElementById("crawler-status-badge");
  const crawlBtnText = document.getElementById("crawl-btn-text");

  // Metrics Elements
  const statStories = document.getElementById("stat-stories");
  const statFilings = document.getElementById("stat-filings");
  const statAnalysts = document.getElementById("stat-analysts");
  const statHealth = document.getElementById("stat-health");

  // Navigation Items
  const navItems = document.querySelectorAll(".nav-item");
  const workspaceViews = document.querySelectorAll(".workspace-view");

  // Overview Digest Section
  const overviewAnalystSelect = document.getElementById("overview-analyst-select");
  const previewFilenameBadge = document.getElementById("preview-filename-badge");
  const previewStoriesFeed = document.getElementById("preview-stories-feed");
  const btnOpenFullPdf = document.getElementById("btn-open-full-pdf");
  const btnSendTestWa = document.getElementById("btn-send-test-wa");
  const btnSendToAll = document.getElementById("btn-send-to-all");
  const eventLogsContainer = document.getElementById("event-logs-container");

  // Mode & Delivery Controls
  const btnModeSingle = document.getElementById("btn-mode-single");
  const btnModeMultiple = document.getElementById("btn-mode-multiple");
  const singleAnalystWrapper = document.getElementById("single-analyst-wrapper");
  const multiAnalystWrapper = document.getElementById("multi-analyst-wrapper");
  const btnSelectAll = document.getElementById("btn-select-all");
  const btnDeselectAll = document.getElementById("btn-deselect-all");
  const analystCheckboxChips = document.getElementById("analyst-checkbox-chips");
  const btnToggleDeliveryMode = document.getElementById("btn-toggle-delivery-mode");
  const deliveryModeIcon = document.getElementById("delivery-mode-icon");
  const deliveryModeText = document.getElementById("delivery-mode-text");
  const sendWaBtnLabel = document.getElementById("send-wa-btn-label");
  const testWaSubtext = document.getElementById("test-wa-subtext");

  let dispatchMode = "single";
  let selectedAnalystIds = new Set();
  let isTestDeliveryMode = true;

  // Full Digest Tab Elements
  const digestViewAnalystSelect = document.getElementById("digest-view-analyst-select");
  const fullDigestIframe = document.getElementById("full-digest-iframe");
  const btnReloadDigestFrame = document.getElementById("btn-reload-digest-frame");
  const btnDownloadDigestPdf = document.getElementById("btn-download-digest-pdf");
  const btnOpenDigestTab = document.getElementById("btn-open-digest-tab");
  const btnSendSingleWhatsapp = document.getElementById("btn-send-single-whatsapp");
  const btnPrevDigestClient = document.getElementById("btn-prev-digest-client");
  const btnNextDigestClient = document.getElementById("btn-next-digest-client");
  const digestClientPhone = document.getElementById("digest-client-phone");
  const digestClientBaskets = document.getElementById("digest-client-baskets");
  const digestStoriesCount = document.getElementById("digest-stories-count");
  const digestFilingsCount = document.getElementById("digest-filings-count");
  const digestPdfName = document.getElementById("digest-pdf-name");
  const digestSelectedAvatar = document.getElementById("digest-selected-avatar");
  const digestFrameLoader = document.getElementById("digest-frame-loader");
  const digestFrameContainer = document.getElementById("digest-frame-container");

  // Watchlist & Folder Elements
  const watchlistTableBody = document.getElementById("watchlist-table-body");
  const watchlistFolderTabs = document.getElementById("watchlist-folder-tabs");
  const watchlistSearchInput = document.getElementById("watchlist-search-input");
  const btnClearWatchlistSearch = document.getElementById("btn-clear-watchlist-search");
  const watchlistVisibleCount = document.getElementById("watchlist-visible-count");
  const watchlistTotalPill = document.getElementById("watchlist-total-pill");
  const btnOpenAddStock = document.getElementById("btn-open-add-stock");
  const modalAddStock = document.getElementById("modal-add-stock");
  const btnCloseStockModal = document.getElementById("btn-close-stock-modal");
  const btnCancelStockModal = document.getElementById("btn-cancel-stock-modal");
  const formAddStock = document.getElementById("form-add-stock");
  const selectCompFolder = document.getElementById("select-comp-folder");
  const stockAnalystsCheckboxes = document.getElementById("stock-analysts-checkboxes");
  const stockFoldersCheckboxes = document.getElementById("stock-folders-checkboxes");

  // Edit Stock Modal Elements
  const modalEditStock = document.getElementById("modal-edit-stock");
  const btnCloseEditStockModal = document.getElementById("btn-close-edit-stock-modal");
  const btnCancelEditStockModal = document.getElementById("btn-cancel-edit-stock-modal");
  const btnDeleteFromEditModal = document.getElementById("btn-delete-from-edit-modal");
  const formEditStock = document.getElementById("form-edit-stock");
  const editCompId = document.getElementById("edit-comp-id");
  const editCompName = document.getElementById("edit-comp-name");
  const editCompNse = document.getElementById("edit-comp-nse");
  const editStockFoldersCheckboxes = document.getElementById("edit-stock-folders-checkboxes");
  const editStockAnalystsCheckboxes = document.getElementById("edit-stock-analysts-checkboxes");

  const btnOpenAddFolder = document.getElementById("btn-open-add-folder");
  const modalAddFolder = document.getElementById("modal-add-folder");
  const btnCloseFolderModal = document.getElementById("btn-close-folder-modal");
  const btnCancelFolderModal = document.getElementById("btn-cancel-folder-modal");
  const formAddFolder = document.getElementById("form-add-folder");
  const inputFolderName = document.getElementById("input-folder-name");

  let currentWatchlistFolder = "ALL";
  let watchlistSearchQuery = "";
  let availableFolders = ["GAME", "SET", "MATCH"];

  // Clients & Directory Elements
  const analystsTableBody = document.getElementById("analysts-table-body");
  const clientSearchInput = document.getElementById("client-search-input");
  const btnClearClientSearch = document.getElementById("btn-clear-client-search");
  const clientsVisibleCount = document.getElementById("clients-visible-count");
  const clientsTotalPill = document.getElementById("clients-total-pill");
  let clientSearchQuery = "";
  const sourcesListContainer = document.getElementById("sources-list-container");
  const sourcesSearchInput = document.getElementById("sources-search-input");
  const btnClearSourcesSearch = document.getElementById("btn-clear-sources-search");
  const sourcesVisibleCount = document.getElementById("sources-visible-count");
  const sourcesTotalPill = document.getElementById("sources-total-pill");
  const sourcesStreamStatus = document.getElementById("sources-stream-status");
  const btnPingAllSources = document.getElementById("btn-ping-all-sources");
  const btnOpenAddSourceModal = document.getElementById("btn-open-add-source-modal");
  const modalAddSource = document.getElementById("modal-add-source");
  const btnCloseSourceModal = document.getElementById("btn-close-source-modal");
  const btnCancelSourceModal = document.getElementById("btn-cancel-source-modal");
  const formAddSource = document.getElementById("form-add-source");
  const filterCountAll = document.getElementById("filter-count-all");
  const filterCountFiling = document.getElementById("filter-count-filing");
  const filterCountRss = document.getElementById("filter-count-rss");
  const filterCountSearch = document.getElementById("filter-count-search");
  let allSourcesList = [];
  let currentSourceCategory = "ALL";
  let sourcesSearchQuery = "";
  const sourcePingResults = {};

  // 1. Clock Updater (IST)
  function updateClock() {
    const now = new Date();
    const options = { timeZone: "Asia/Kolkata", hour12: false, hour: "2-digit", minute: "2-digit", second: "2-digit" };
    topbarClock.textContent = `${now.toLocaleTimeString("en-GB", options)} IST`;
  }
  setInterval(updateClock, 1000);
  updateClock();

  // 2. Sidebar Navigation
  navItems.forEach(item => {
    item.addEventListener("click", () => {
      navItems.forEach(i => i.classList.remove("active"));
      workspaceViews.forEach(v => v.classList.remove("active"));
      item.classList.add("active");
      const targetId = item.dataset.view;
      const targetView = document.getElementById(targetId);
      if (targetView) targetView.classList.add("active");

      if (targetId === "view-digest") {
        loadFullDigestFrame();
      }
      if (targetId === "view-sources") {
        loadSources();
      }
      if (targetId === "view-settings") {
        loadFullSettings();
      }
    });
  });

  // 3. Toast Notifications
  function showToast(message, isError = false) {
    const banner = document.getElementById("toast-banner");
    const toast = document.createElement("div");
    toast.className = "toast-item";
    if (isError) toast.style.borderColor = "var(--text-red)";
    toast.textContent = message;
    banner.appendChild(toast);
    setTimeout(() => {
      toast.style.opacity = "0";
      setTimeout(() => toast.remove(), 300);
    }, 3500);
  }

  // 4. Fetch Stats
  async function loadStats() {
    try {
      const res = await fetch("/api/stats");
      const data = await res.json();
      if (statStories) statStories.textContent = `${data.total_stories ?? 0} Stories`;
      if (statFilings) statFilings.textContent = `${data.total_filings ?? 0} Filings`;
      if (statAnalysts) statAnalysts.textContent = `${data.total_analysts ?? 0} Clients`;
      const statComp = document.getElementById("stat-companies");
      if (statComp) statComp.textContent = `${data.total_companies ?? 0} Stocks`;
      if (statHealth) statHealth.textContent = "100% Health";

      const lastCrawlEl = document.getElementById("last-crawl-time");
      if (lastCrawlEl) {
        const crawlTs = data.last_crawl && (data.last_crawl.completed_at || data.last_crawl.started_at);
        if (crawlTs) {
          try {
            const d = new Date(crawlTs);
            lastCrawlEl.textContent = `Today, ${d.toLocaleTimeString("en-IN", { hour: "2-digit", minute: "2-digit", hour12: true })}`;
          } catch (e) {
            lastCrawlEl.textContent = "Today, 8:30 AM";
          }
        } else {
          lastCrawlEl.textContent = "Today, 8:30 AM";
        }
      }
    } catch (err) {
      console.error("Stats load failed", err);
    }
  }

  function getCompanyFolders(c) {
    if (!c) return [];
    if (Array.isArray(c.folders) && c.folders.length) {
      return c.folders.map(f => String(f).trim().toUpperCase()).filter(Boolean);
    }
    const raw = String(c.folder || "").trim();
    if (!raw) return [];
    if (raw.startsWith("[")) {
      try {
        const arr = JSON.parse(raw);
        if (Array.isArray(arr)) return arr.map(f => String(f).trim().toUpperCase()).filter(Boolean);
      } catch (e) {}
    }
    if (raw.includes(",")) {
      return raw.split(",").map(f => f.trim().toUpperCase()).filter(Boolean);
    }
    return [raw.toUpperCase()];
  }

  // 5. Fetch Analysts & Populate Select
  function getAnalystCoveredStockCount(analyst) {
    if (!companiesList || !companiesList.length) {
      return (analyst.assigned_companies || []).length;
    }
    const assignedFolders = (analyst.assigned_folders || []).map(f => f.toUpperCase());
    const coveredSet = new Set(analyst.assigned_companies || []);
    companiesList.forEach(c => {
      const cFlds = getCompanyFolders(c);
      if (cFlds.some(f => assignedFolders.includes(f))) {
        coveredSet.add(c.id);
      }
    });
    return coveredSet.size;
  }

  function renderAnalystSelectOptions() {
    if (!analystsList || !analystsList.length) return;
    const currentVal = overviewAnalystSelect.value || currentAnalystId;

    const optionsHtml = analystsList.map(a => {
      const count = getAnalystCoveredStockCount(a);
      const folders = (a.assigned_folders || []).map(f => f.toUpperCase());
      const folderHint = folders.length > 0 ? ` (${folders.join(", ")})` : "";
      return `<option value="${a.id}">${a.name} — Coverage: ${count} Stocks${folderHint} (+91 ${a.phone})</option>`;
    }).join("");

    overviewAnalystSelect.innerHTML = optionsHtml;
    digestViewAnalystSelect.innerHTML = optionsHtml;

    if (currentVal && analystsList.some(a => a.id === currentVal)) {
      overviewAnalystSelect.value = currentVal;
      digestViewAnalystSelect.value = currentVal;
    }
  }

  async function loadAnalysts() {
    try {
      const res = await fetch("/api/analysts");
      analystsList = await res.json();

      renderAnalystSelectOptions();

      // Select all analysts by default in multiple mode
      if (selectedAnalystIds.size === 0) {
        analystsList.forEach(a => selectedAnalystIds.add(a.id));
      }
      renderMultiAnalystChips();

      if (analystsList.length > 0) {
        if (!currentAnalystId || !analystsList.some(a => a.id === currentAnalystId)) {
          currentAnalystId = analystsList[0].id;
        }
        loadAnalystStoriesPreview(currentAnalystId);
      }

      renderAnalystsTable();
      updateActionButtons();
    } catch (err) {
      console.error("Analysts fetch error", err);
    }
  }

  // Search Input Listeners for Clients
  if (clientSearchInput) {
    clientSearchInput.addEventListener("input", (e) => {
      clientSearchQuery = (e.target.value || "").trim().toLowerCase();
      if (btnClearClientSearch) {
        btnClearClientSearch.style.display = clientSearchQuery ? "inline-flex" : "none";
      }
      renderAnalystsTable();
    });
  }

  if (btnClearClientSearch) {
    btnClearClientSearch.addEventListener("click", () => {
      window.clearClientSearch();
    });
  }

  window.clearClientSearch = () => {
    if (clientSearchInput) clientSearchInput.value = "";
    clientSearchQuery = "";
    if (btnClearClientSearch) btnClearClientSearch.style.display = "none";
    renderAnalystsTable();
    if (clientSearchInput) clientSearchInput.focus();
  };

  function renderAnalystsTable() {
    if (!analystsTableBody) return;

    if (clientsTotalPill) {
      clientsTotalPill.textContent = `${analystsList.length} Registered Clients`;
    }

    let filtered = [...analystsList];
    if (clientSearchQuery) {
      filtered = filtered.filter(a => {
        const name = (a.name || "").toLowerCase();
        const phone = (a.phone || "").toLowerCase();
        const email = (a.email || "").toLowerCase();
        const flds = (a.assigned_folders || []).map(f => f.toLowerCase());
        return name.includes(clientSearchQuery) ||
               phone.includes(clientSearchQuery) ||
               email.includes(clientSearchQuery) ||
               flds.some(f => f.includes(clientSearchQuery));
      });
    }

    if (clientsVisibleCount) {
      if (clientSearchQuery) {
        clientsVisibleCount.textContent = `Showing ${filtered.length} of ${analystsList.length} clients (matching "${clientSearchQuery}")`;
      } else {
        clientsVisibleCount.textContent = `Showing ${filtered.length} of ${analystsList.length} clients`;
      }
    }

    if (filtered.length === 0) {
      const msg = clientSearchQuery
        ? `No clients found matching "<strong>${clientSearchQuery}</strong>".`
        : `No clients registered yet. Click "+ Add Client" to add WhatsApp briefing recipients!`;
      
      analystsTableBody.innerHTML = `
        <tr>
          <td colspan="4" style="text-align: center; padding: 40px 20px; color: var(--text-dim);">
            <div style="font-size: 1.6rem; margin-bottom: 8px;">👥</div>
            <div style="font-size: 0.88rem; color: var(--text-secondary);">${msg}</div>
            ${clientSearchQuery ? `<button type="button" class="btn-secondary-micro" onclick="window.clearClientSearch()" style="margin-top: 14px; padding: 6px 16px; border-radius: 8px; cursor: pointer;">Clear Search</button>` : ''}
          </td>
        </tr>
      `;
      return;
    }

    analystsTableBody.innerHTML = filtered.map(a => {
      const folders = a.assigned_folders || [];
      const stockCount = getAnalystCoveredStockCount(a);
      
      // Initials for avatar
      const names = (a.name || "Client").trim().split(" ");
      const initials = names.length > 1
        ? (names[0][0] + names[names.length - 1][0]).toUpperCase()
        : names[0].slice(0, 2).toUpperCase();

      const foldersDisplay = folders.length > 0
        ? folders.map(f => {
            const tagClass = getFolderClass(f);
            return `<span class="folder-tag ${tagClass}">${f}</span>`;
          }).join(" ")
        : `<span class="badge-unassigned" onclick="window.editAnalyst('${a.id}')" title="Click to assign portfolio baskets">+ Assign Baskets</span>`;

      return `
        <tr class="client-row" data-client-id="${a.id}">
          <!-- Column 1: Client / Recipient -->
          <td>
            <div class="client-cell">
              <div class="client-avatar-chip" onclick="window.editAnalyst('${a.id}')" title="Click to edit profile">${initials}</div>
              <div class="client-info">
                <span class="client-name" onclick="window.editAnalyst('${a.id}')" title="Click to edit profile">${a.name}</span>
                <div class="client-meta-row">
                  <span class="client-phone-badge" title="WhatsApp Delivery Number">💬 +91 ${a.phone}</span>
                  ${a.email ? `<span class="client-email-badge" title="Email: ${a.email}">✉️ ${a.email}</span>` : ''}
                </div>
              </div>
            </div>
          </td>

          <!-- Column 2: Portfolio Coverage -->
          <td>
            <div class="client-coverage-cell">
              <div class="client-baskets-row">${foldersDisplay}</div>
              <span class="client-stocks-count-badge">📊 ${stockCount} Stocks Tracked</span>
            </div>
          </td>

          <!-- Column 3: Morning Dispatch Status -->
          <td>
            <div class="client-dispatch-cell">
              <span class="status-badge-ok"><span class="pulse-dot"></span>8:00 AM QUEUED</span>
              <span class="dispatch-cycle-sub">Next: Tomorrow 8 AM</span>
            </div>
          </td>

          <!-- Column 4: Actions -->
          <td style="text-align: right;">
            <div class="row-actions-cell">
              <button type="button" class="btn-client-dispatch" onclick="window.sendBriefToClient('${a.id}')" title="Send WhatsApp briefing right now">
                <span class="action-icon">💬</span>
                <span>Send Brief</span>
              </button>
              <button type="button" class="btn-row-edit" onclick="window.editAnalyst('${a.id}')" title="Edit client details">
                <span class="action-icon">✏️</span>
                <span>Edit</span>
              </button>
              <button type="button" class="btn-row-del" onclick="window.deleteAnalyst('${a.id}')" title="Remove client">
                <span class="action-icon">🗑️</span>
              </button>
            </div>
          </td>
        </tr>
      `;
    }).join("");
  }

  window.sendBriefToClient = async (id) => {
    const a = analystsList.find(x => x.id === id);
    const clientName = a ? a.name : id;
    if (!confirm(`Dispatch morning WhatsApp briefing to ${clientName} now?`)) return;

    try {
      const res = await fetch(`/api/digest/simulate-send/${id}`, { method: "POST" });
      const data = await res.json();
      showToast(data.message || `Briefing sent to ${clientName}!`);
      loadStats();
      loadAnalystStoriesPreview(currentAnalystId);
      loadLogs();
    } catch (err) {
      showToast("Dispatch error", true);
    }
  };

  window.editAnalyst = (id) => {
    const a = analystsList.find(x => x.id === id);
    if (!a) return;
    document.getElementById("analyst-modal-title").textContent = `Edit Client: ${a.name}`;
    document.getElementById("input-analyst-id").value = a.id;
    document.getElementById("input-analyst-name").value = a.name;
    document.getElementById("input-analyst-phone").value = a.phone;
    document.getElementById("input-analyst-email").value = a.email || "";
    renderAnalystFoldersCheckboxes(a.assigned_folders || []);
    modalAddAnalyst.classList.add("open");
  };

  window.deleteAnalyst = async (id) => {
    const a = analystsList.find(x => x.id === id);
    const clientName = a ? a.name : id;
    if (!confirm(`Are you sure you want to remove ${clientName} from the client directory?`)) return;
    try {
      const res = await fetch(`/api/analysts/${id}`, { method: "DELETE" });
      if (res.ok) {
        showToast("Client removed.");
        await loadAnalysts();
        loadStats();
      }
    } catch(err) {
      showToast("Error deleting client", true);
    }
  };

  function renderAnalystFoldersCheckboxes(assigned = []) {
    const container = document.getElementById("analyst-folders-checkboxes");
    if (!container) return;
    if (!availableFolders.length) {
      container.innerHTML = `<span style="font-size:0.78rem; color:var(--text-dim);">No folders available.</span>`;
      return;
    }
    const assignedUpper = (assigned || []).map(f => f.toUpperCase());
    container.innerHTML = availableFolders.map(f => {
      const isChecked = assignedUpper.includes(f.toUpperCase()) ? 'checked' : '';
      let tagClass = "folder-tag-custom";
      if (f === "GAME") tagClass = "folder-tag-game";
      else if (f === "SET") tagClass = "folder-tag-set";
      else if (f === "MATCH") tagClass = "folder-tag-match";

      const stockCount = companiesList.filter(c => getCompanyFolders(c).includes(f.toUpperCase())).length;

      return `
        <label class="folder-checkbox-card">
          <div class="folder-checkbox-left">
            <input type="checkbox" name="assigned_folder" value="${f}" ${isChecked}>
            <span class="folder-tag ${tagClass}">${f}</span>
          </div>
          <span style="font-size:0.75rem; color:var(--text-dim);">${stockCount} stocks</span>
        </label>
      `;
    }).join("");
  }

  // Analyst Modal Logic
  const btnOpenAddAnalyst = document.getElementById("btn-open-add-analyst");
  const modalAddAnalyst = document.getElementById("modal-add-analyst");
  const btnCloseAnalystModal = document.getElementById("btn-close-analyst-modal");
  const btnCancelAnalystModal = document.getElementById("btn-cancel-analyst-modal");
  const formAddAnalyst = document.getElementById("form-add-analyst");

  btnOpenAddAnalyst.addEventListener("click", () => {
    document.getElementById("analyst-modal-title").textContent = "Add New Client";
    formAddAnalyst.reset();
    document.getElementById("input-analyst-id").value = "";
    renderAnalystFoldersCheckboxes([]);
    modalAddAnalyst.classList.add("open");
  });

  btnCloseAnalystModal.addEventListener("click", () => modalAddAnalyst.classList.remove("open"));
  btnCancelAnalystModal.addEventListener("click", () => modalAddAnalyst.classList.remove("open"));

  formAddAnalyst.addEventListener("submit", async (e) => {
    e.preventDefault();
    const id = document.getElementById("input-analyst-id").value.trim();
    const name = document.getElementById("input-analyst-name").value.trim();
    const phone = document.getElementById("input-analyst-phone").value.trim().replace(/\D/g, "");
    const email = document.getElementById("input-analyst-email").value.trim();

    if (phone.length < 10) {
      showToast("Please enter a valid 10-digit WhatsApp number", true);
      return;
    }

    const checkedBoxes = document.querySelectorAll('input[name="assigned_folder"]:checked');
    const assignedFolders = Array.from(checkedBoxes).map(cb => cb.value);

    // Preserve existing directly assigned stocks
    const existing = analystsList.find(x => x.id === id);
    const assignedCompanies = existing ? (existing.assigned_companies || []) : [];

    const payload = {
      id: id || name.toLowerCase().replace(/[^a-z0-9]/g, "").slice(0, 16),
      name,
      phone,
      email,
      assigned_companies: assignedCompanies,
      assigned_folders: assignedFolders
    };

    try {
      const res = await fetch("/api/analysts", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload)
      });
      if (res.ok) {
        showToast(`Saved client: ${name}!`);
        modalAddAnalyst.classList.remove("open");
        formAddAnalyst.reset();
        await loadAnalysts();
        loadStats();
      }
    } catch(err) {
      showToast("Failed to save client", true);
    }
  });

  overviewAnalystSelect.addEventListener("change", (e) => {
    currentAnalystId = e.target.value;
    loadAnalystStoriesPreview(currentAnalystId);
    updateActionButtons();
  });

  digestViewAnalystSelect.addEventListener("change", (e) => {
    currentAnalystId = e.target.value;
    loadFullDigestFrame();
  });

  // Delivery Mode Checker & Toggle
  async function loadDeliveryMode() {
    try {
      const res = await fetch("/api/settings/delivery-mode");
      const data = await res.json();
      isTestDeliveryMode = !!data.test_mode;
      updateDeliveryModeUI(data.test_phone || "7900084773");
    } catch (e) {
      console.error("Delivery mode check error", e);
    }
  }

  function updateDeliveryModeUI(testPhone) {
    if (!btnToggleDeliveryMode) return;
    const headline = document.getElementById("delivery-mode-text");
    const subtext = document.getElementById("delivery-mode-subtext");

    if (isTestDeliveryMode) {
      btnToggleDeliveryMode.className = "delivery-status-card mode-safety";
      if (headline) headline.textContent = `🛡️ Safety Test (To ${testPhone})`;
      if (subtext) subtext.textContent = `Safe Sandbox: All dispatches safely route to ${testPhone}`;
      btnToggleDeliveryMode.title = `Safety Sandbox active: All dispatches redirect to ${testPhone}. Click to switch to Live Direct.`;
    } else {
      btnToggleDeliveryMode.className = "delivery-status-card mode-live";
      if (headline) headline.textContent = `🟢 Live Direct Delivery`;
      if (subtext) subtext.textContent = `Production: Each analyst receives digest directly on their WhatsApp`;
      btnToggleDeliveryMode.title = `Live Mode active: Digests go directly to each analyst's WhatsApp. Click to switch to Safety Sandbox.`;
    }
    updateActionButtons();
  }

  if (btnToggleDeliveryMode) {
    btnToggleDeliveryMode.addEventListener("click", async () => {
      const targetMode = !isTestDeliveryMode;
      const question = targetMode
        ? "Switch to Safety Test Mode?\nAll dispatches will be safely routed to your test number (7900084773)."
        : "Switch to LIVE DIRECT Mode?\nDispatches will be delivered directly to each analyst's registered WhatsApp number!";
      if (!confirm(question)) return;

      try {
        const res = await fetch("/api/settings/delivery-mode", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ test_mode: targetMode })
        });
        const data = await res.json();
        isTestDeliveryMode = !!data.test_mode;
        showToast(isTestDeliveryMode ? "🛡️ Safety Test Mode Active" : "🟢 Live Direct Mode Active!");
        loadDeliveryMode();
      } catch (e) {
        showToast("Error updating delivery mode", true);
      }
    });
  }

  function updateActionButtons() {
    const a = analystsList.find(x => x.id === currentAnalystId) || { name: currentAnalystId, phone: "" };
    const metaBadge = document.getElementById("single-analyst-meta-badge");
    if (metaBadge && a.name) {
      const assignedFolders = (a.assigned_folders || []).map(f => f.toUpperCase());
      const stockCount = companiesList.filter(c => {
        const cFlds = getCompanyFolders(c);
        return cFlds.some(f => assignedFolders.includes(f));
      }).length;
      metaBadge.innerHTML = `
        <span>📱 <strong>+91 ${a.phone || '—'}</strong></span>
        <span>&bull;</span>
        <span>📁 <strong>${assignedFolders.length > 0 ? assignedFolders.join(', ') : 'No Baskets'} (${stockCount} Stocks)</strong></span>
      `;
    }

    if (dispatchMode === "single") {
      if (sendWaBtnLabel) {
        sendWaBtnLabel.textContent = `Send WhatsApp to ${a.name}`;
      }
      if (testWaSubtext) {
        testWaSubtext.textContent = `Direct to WhatsApp: +91 ${a.phone || '—'}`;
      }
    } else {
      const count = selectedAnalystIds.size;
      if (sendWaBtnLabel) {
        sendWaBtnLabel.textContent = `Dispatch to All (${count} Clients)`;
      }
      if (testWaSubtext) {
        testWaSubtext.textContent = `Personalized briefs queued for ${count} clients`;
      }
    }
  }

  function renderMultiAnalystChips() {
    if (!analystCheckboxChips) return;
    if (!analystsList.length) {
      analystCheckboxChips.innerHTML = `<span style="color:var(--text-dim);font-size:0.8rem;">No analysts registered.</span>`;
      return;
    }

    const multiBadge = document.getElementById("multi-selected-count-badge");
    if (multiBadge) {
      multiBadge.textContent = `${selectedAnalystIds.size} of ${analystsList.length} Selected`;
    }

    analystCheckboxChips.innerHTML = analystsList.map(a => {
      const isChecked = selectedAnalystIds.has(a.id);
      const initials = a.name.split(" ").map(w => w[0]).join("").toUpperCase().slice(0, 2);
      const flds = a.assigned_folders || [];
      const fldsStr = flds.length > 0 ? flds.join(", ") : "No Baskets";
      return `
        <div class="analyst-card-item ${isChecked ? 'selected' : ''}" data-id="${a.id}">
          <input type="checkbox" id="chk-${a.id}" value="${a.id}" ${isChecked ? 'checked' : ''}>
          <div class="analyst-avatar-badge">${initials}</div>
          <div class="analyst-info-col">
            <span class="analyst-card-name">${a.name}</span>
            <span class="analyst-card-phone">+91 ${a.phone} &bull; ${fldsStr}</span>
          </div>
        </div>
      `;
    }).join("");

    analystCheckboxChips.querySelectorAll('.analyst-card-item').forEach(card => {
      card.addEventListener("click", (e) => {
        const chk = card.querySelector('input[type="checkbox"]');
        if (e.target !== chk) {
          chk.checked = !chk.checked;
        }
        const aid = chk.value;
        if (chk.checked) {
          selectedAnalystIds.add(aid);
          card.classList.add("selected");
        } else {
          selectedAnalystIds.delete(aid);
          card.classList.remove("selected");
        }
        if (multiBadge) {
          multiBadge.textContent = `${selectedAnalystIds.size} of ${analystsList.length} Selected`;
        }
        updateActionButtons();
      });
    });
  }

  if (btnModeSingle && btnModeMultiple) {
    btnModeSingle.addEventListener("click", () => {
      dispatchMode = "single";
      btnModeSingle.classList.add("active");
      btnModeMultiple.classList.remove("active");
      if (singleAnalystWrapper) singleAnalystWrapper.style.display = "flex";
      if (multiAnalystWrapper) multiAnalystWrapper.style.display = "none";
      updateActionButtons();
      loadAnalystStoriesPreview(currentAnalystId);
    });

    btnModeMultiple.addEventListener("click", () => {
      dispatchMode = "multiple";
      btnModeMultiple.classList.add("active");
      btnModeSingle.classList.remove("active");
      if (singleAnalystWrapper) singleAnalystWrapper.style.display = "none";
      if (multiAnalystWrapper) multiAnalystWrapper.style.display = "flex";
      if (selectedAnalystIds.size === 0) {
        analystsList.forEach(a => selectedAnalystIds.add(a.id));
      }
      renderMultiAnalystChips();
      updateActionButtons();
    });
  }

  if (btnSelectAll) {
    btnSelectAll.addEventListener("click", () => {
      analystsList.forEach(a => selectedAnalystIds.add(a.id));
      renderMultiAnalystChips();
      updateActionButtons();
    });
  }

  if (btnDeselectAll) {
    btnDeselectAll.addEventListener("click", () => {
      selectedAnalystIds.clear();
      renderMultiAnalystChips();
      updateActionButtons();
    });
  }

  // 6. Fetch Unsent Stories for Overview Left Box
  let currentAnalystStories = [];

  function renderStoryCards(stories) {
    if (!stories || stories.length === 0) {
      previewStoriesFeed.innerHTML = `
        <div style="padding: 24px 16px; color: var(--text-muted); font-style: italic; text-align: center;">
          No unsent stories currently queued. Sent ledger is clean!
        </div>
      `;
      return;
    }
    previewStoriesFeed.innerHTML = stories.slice(0, 25).map(item => {
      const isFiling = item.source_type === "filing";
      const cname = item.company_name || "Company";
      const sourcesText = (item.sources || []).map(s => s.name).join(" • ") || item.source_name;

      return `
        <div class="preview-story-card">
          <div class="story-card-top">
            <span class="ticker-badge ${isFiling ? 'badge-filing' : ''}">${isFiling ? '🏛️ ' : ''}${cname.toUpperCase()}</span>
            <span class="story-source-badge">${sourcesText}</span>
          </div>
          <a class="story-card-title" href="${item.url || '#'}" target="_blank" rel="noopener">
            ${item.title}
          </a>
        </div>
      `;
    }).join("");
  }

  const storySearchInput = document.getElementById("preview-story-search");
  if (storySearchInput) {
    storySearchInput.addEventListener("input", (e) => {
      const q = e.target.value.trim().toLowerCase();
      if (!q) {
        renderStoryCards(currentAnalystStories);
        return;
      }
      const filtered = currentAnalystStories.filter(s => {
        const title = (s.title || "").toLowerCase();
        const cname = (s.company_name || "").toLowerCase();
        const ticker = (s.company_id || "").toLowerCase();
        return title.includes(q) || cname.includes(q) || ticker.includes(q);
      });
      renderStoryCards(filtered);
    });
  }

  async function loadAnalystStoriesPreview(analystId) {
    const analyst = analystsList.find(a => a.id === analystId) || { name: analystId };
    const dateStr = new Date().toLocaleDateString("en-GB", { day: "2-digit", month: "short", year: "numeric" }).replace(/ /g, "");
    previewFilenameBadge.textContent = `Live PDF Preview (${analyst.name}_${dateStr}.pdf)`;

    updateActionButtons();

    previewStoriesFeed.innerHTML = `<div class="loading-line">&#9696; Compiling personalized briefing stories...</div>`;

    try {
      const res = await fetch(`/api/stories?limit=80`);
      const all = await res.json();
      
      // Filter for companies assigned to this analyst via folders or direct assignment
      const assignedFolders = (analyst.assigned_folders || []).map(f => f.toUpperCase());
      const assignedSet = new Set(analyst.assigned_companies || []);
      companiesList.forEach(c => {
        const cFlds = getCompanyFolders(c);
        if (cFlds.some(f => assignedFolders.includes(f))) {
          assignedSet.add(c.id);
        }
      });
      currentAnalystStories = all.filter(s => assignedSet.has(s.company_id));

      const countBadge = document.getElementById("preview-stories-count");
      if (countBadge) {
        countBadge.textContent = `${currentAnalystStories.length} Stories`;
      }

      if (storySearchInput) storySearchInput.value = "";
      renderStoryCards(currentAnalystStories);

    } catch (err) {
      previewStoriesFeed.innerHTML = `<div style="color: var(--text-red);">Failed to load preview stories.</div>`;
    }
  }

  // 7. Action Buttons (Right Column)
  btnOpenFullPdf.addEventListener("click", () => {
    // Switch to Daily Digest view
    const digestNav = document.querySelector('[data-view="view-digest"]');
    if (digestNav) digestNav.click();
  });

  btnSendTestWa.addEventListener("click", async () => {
    if (dispatchMode === "single") {
      btnSendTestWa.disabled = true;
      btnSendTestWa.innerHTML = `<span>&#9696; Dispatching...</span>`;

      try {
        const res = await fetch(`/api/digest/simulate-send/${currentAnalystId}`, { method: "POST" });
        const data = await res.json();
        showToast(data.message || `Test dispatch complete!`);
        loadStats();
        loadAnalystStoriesPreview(currentAnalystId);
        loadLogs();
      } catch (err) {
        showToast("Dispatch error", true);
      } finally {
        btnSendTestWa.disabled = false;
        btnSendTestWa.innerHTML = `<span class="btn-icon">&#128242;</span><span id="send-wa-btn-label">Send WA</span>`;
        updateActionButtons();
      }
    } else {
      // Multiple Mode
      if (selectedAnalystIds.size === 0) {
        showToast("Please select at least one analyst above.", true);
        return;
      }
      btnSendTestWa.disabled = true;
      btnSendTestWa.innerHTML = `<span>&#9696; Sending to ${selectedAnalystIds.size} analysts...</span>`;

      try {
        const res = await fetch("/api/digest/send-multiple", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ analyst_ids: Array.from(selectedAnalystIds) })
        });
        const data = await res.json();
        showToast(`Dispatched custom scorecards to ${data.total} selected analysts!`);
        loadStats();
        loadAnalystStoriesPreview(currentAnalystId);
        loadLogs();
      } catch (err) {
        showToast("Multi-dispatch error", true);
      } finally {
        btnSendTestWa.disabled = false;
        btnSendTestWa.innerHTML = `<span class="btn-icon">&#128242;</span><span id="send-wa-btn-label">Send WA to Selected</span>`;
        updateActionButtons();
      }
    }
  });

  btnSendToAll.addEventListener("click", async () => {
    if (!confirm("Dispatch morning digest to all analysts now?")) return;
    btnSendToAll.disabled = true;
    btnSendToAll.textContent = "Sending to all...";

    for (const a of analystsList) {
      try {
        await fetch(`/api/digest/simulate-send/${a.id}`, { method: "POST" });
      } catch (e) {}
    }

    showToast("Morning digests sent to all analysts! Sent ledger updated.");
    loadStats();
    loadAnalystStoriesPreview(currentAnalystId);
    loadLogs();
    btnSendToAll.disabled = false;
    btnSendToAll.innerHTML = `<span class="btn-icon">&#128640;</span><span>Send to All Analysts</span>`;
  });

  // 8. Full Daily Digest Desk & Interactive Workstation
  async function loadFullDigestFrame() {
    if (!digestViewAnalystSelect) return;

    if (digestViewAnalystSelect.value !== currentAnalystId) {
      digestViewAnalystSelect.value = currentAnalystId;
    }

    if (digestFrameLoader) digestFrameLoader.style.display = "flex";

    if (fullDigestIframe) {
      fullDigestIframe.onload = () => {
        if (digestFrameLoader) digestFrameLoader.style.display = "none";
      };
      fullDigestIframe.src = `/api/digest/preview/${currentAnalystId}?t=${Date.now()}`;
    }

    try {
      const res = await fetch(`/api/digest/meta/${currentAnalystId}`);
      if (res.ok) {
        const meta = await res.json();

        if (digestClientPhone) {
          digestClientPhone.textContent = meta.phone ? (meta.phone.startsWith("+") ? meta.phone : `+91 ${meta.phone}`) : "No Phone";
        }

        if (digestClientBaskets) {
          const baskets = meta.assigned_folders && meta.assigned_folders.length > 0
            ? meta.assigned_folders.join(", ")
            : "All Stocks";
          digestClientBaskets.textContent = baskets;
        }

        if (digestStoriesCount) {
          digestStoriesCount.textContent = `${meta.total_stories || 0} Stories`;
        }

        if (digestFilingsCount) {
          digestFilingsCount.textContent = `${meta.total_filings || 0} Filings`;
        }

        if (digestPdfName) {
          digestPdfName.textContent = meta.pdf_name || "Client_Date.pdf";
        }

        if (digestSelectedAvatar) {
          const firstChar = (meta.name || "C").charAt(0).toUpperCase();
          digestSelectedAvatar.textContent = firstChar;
        }
      }
    } catch (err) {
      console.warn("Could not fetch digest meta", err);
    }
  }

  if (btnReloadDigestFrame) {
    btnReloadDigestFrame.addEventListener("click", () => {
      showToast("Recompiling fresh daily briefing preview...");
      loadFullDigestFrame();
    });
  }

  function triggerSilentDownload(url, filename) {
    const a = document.createElement("a");
    a.href = url;
    if (filename) a.download = filename;
    a.style.display = "none";
    document.body.appendChild(a);
    a.click();
    setTimeout(() => a.remove(), 250);
  }

  if (btnDownloadDigestPdf) {
    btnDownloadDigestPdf.addEventListener("click", () => {
      const filename = digestPdfName ? digestPdfName.textContent.trim() : "";
      showToast(`Generating and downloading ${filename || "PDF"}...`);
      triggerSilentDownload(`/api/digest/download/${currentAnalystId}?t=${Date.now()}`, filename);
    });
  }

  if (btnOpenDigestTab) {
    btnOpenDigestTab.addEventListener("click", () => {
      window.open(`/api/digest/preview/${currentAnalystId}?t=${Date.now()}`, "_blank");
    });
  }

  if (btnSendSingleWhatsapp) {
    btnSendSingleWhatsapp.addEventListener("click", async () => {
      btnSendSingleWhatsapp.disabled = true;
      btnSendSingleWhatsapp.innerHTML = `<span class="btn-icon">⏳</span> Sending...`;
      showToast(`Dispatching 8:00 AM briefing to client...`);

      try {
        const res = await fetch(`/api/digest/simulate-send/${currentAnalystId}`, { method: "POST" });
        const data = await res.json();
        if (data.status === "no_op") {
          showToast(data.message || "No unsent stories for this client.", false);
        } else {
          showToast(`Briefing dispatched: ${data.message || 'Sent successfully'}`);
          loadStats();
          loadFullDigestFrame();
          loadAnalystStoriesPreview(currentAnalystId);
        }
      } catch (err) {
        showToast("Error sending briefing to client", true);
      } finally {
        btnSendSingleWhatsapp.disabled = false;
        btnSendSingleWhatsapp.innerHTML = `<span class="btn-icon">🚀</span> Send Brief`;
      }
    });
  }

  if (btnPrevDigestClient) {
    btnPrevDigestClient.addEventListener("click", () => {
      if (!digestViewAnalystSelect || digestViewAnalystSelect.options.length <= 1) return;
      let idx = digestViewAnalystSelect.selectedIndex - 1;
      if (idx < 0) idx = digestViewAnalystSelect.options.length - 1;
      digestViewAnalystSelect.selectedIndex = idx;
      currentAnalystId = digestViewAnalystSelect.value;
      loadFullDigestFrame();
    });
  }

  if (btnNextDigestClient) {
    btnNextDigestClient.addEventListener("click", () => {
      if (!digestViewAnalystSelect || digestViewAnalystSelect.options.length <= 1) return;
      let idx = digestViewAnalystSelect.selectedIndex + 1;
      if (idx >= digestViewAnalystSelect.options.length) idx = 0;
      digestViewAnalystSelect.selectedIndex = idx;
      currentAnalystId = digestViewAnalystSelect.value;
      loadFullDigestFrame();
    });
  }

  document.querySelectorAll(".viewmode-btn").forEach(btn => {
    btn.addEventListener("click", () => {
      document.querySelectorAll(".viewmode-btn").forEach(b => b.classList.remove("active"));
      btn.classList.add("active");
      const mode = btn.dataset.mode;
      if (digestFrameContainer) {
        if (mode === "mobile") {
          digestFrameContainer.classList.add("mobile-mode");
        } else {
          digestFrameContainer.classList.remove("mobile-mode");
        }
      }
    });
  });

  // 9. Live Crawler Logs
  async function loadLogs() {
    try {
      const res = await fetch("/api/logs");
      const logs = await res.json();
      if (logs.length > 0) {
        eventLogsContainer.innerHTML = logs.map(l => `
          <div class="log-line">
            <span class="log-ts">[${l.time}]</span>
            <span class="log-txt ${l.type === 'warn' ? 'log-warn' : ''}">${l.msg}</span>
          </div>
        `).join("");
      }
    } catch (err) {
      console.error("Logs fetch failed", err);
    }
  }

  // 10. Folder & Watchlist Management
  async function loadFolders() {
    try {
      const res = await fetch("/api/folders");
      const data = await res.json();
      if (data.folders && Array.isArray(data.folders)) {
        availableFolders = data.folders;
      }
      renderFolderTabs();
      populateFolderSelect();
    } catch (err) {
      console.error("Folders fetch failed", err);
    }
  }

  function populateFolderSelect() {
    if (!selectCompFolder) return;
    selectCompFolder.innerHTML = `
      <option value="">— None (In ALL only) —</option>
      ${availableFolders.map(f => `<option value="${f}">${f}</option>`).join("")}
    `;
    if (currentWatchlistFolder !== "ALL" && availableFolders.includes(currentWatchlistFolder)) {
      selectCompFolder.value = currentWatchlistFolder;
    }
  }

  function renderFolderTabs() {
    if (!watchlistFolderTabs) return;

    const counts = {};
    availableFolders.forEach(f => { counts[f] = 0; });
    companiesList.forEach(c => {
      const cFlds = getCompanyFolders(c);
      cFlds.forEach(f => {
        if (counts[f] !== undefined) {
          counts[f] = counts[f] + 1;
        }
      });
    });

    const allActive = currentWatchlistFolder === "ALL" ? "active" : "";
    let html = `
      <button class="folder-tab-btn ${allActive}" data-folder="ALL">
        <span>ALL</span>
        <span class="folder-tab-count">${companiesList.length}</span>
      </button>
    `;

    availableFolders.forEach(f => {
      const active = currentWatchlistFolder.toUpperCase() === f.toUpperCase() ? "active" : "";
      const cnt = counts[f] || 0;
      const isCustom = !["GAME", "SET", "MATCH"].includes(f.toUpperCase());
      html += `
        <button class="folder-tab-btn ${active}" data-folder="${f}">
          <span>${f}</span>
          <span class="folder-tab-count">${cnt}</span>
          ${isCustom ? `<span class="folder-tab-del" data-del-folder="${f}" title="Delete folder" style="margin-left: 4px; opacity: 0.6; font-size: 0.75rem;">&times;</span>` : ''}
        </button>
      `;
    });

    watchlistFolderTabs.innerHTML = html;

    watchlistFolderTabs.querySelectorAll(".folder-tab-btn").forEach(btn => {
      btn.addEventListener("click", (e) => {
        const delTarget = e.target.closest("[data-del-folder]");
        if (delTarget) {
          e.stopPropagation();
          const fldName = delTarget.getAttribute("data-del-folder");
          deleteCustomFolder(fldName);
          return;
        }
        currentWatchlistFolder = btn.getAttribute("data-folder");
        renderFolderTabs();
        renderWatchlistTable();
      });
    });
  }

  async function deleteCustomFolder(name) {
    if (!confirm(`Delete folder "${name}"? Stocks inside will remain in the database.`)) return;
    try {
      const res = await fetch(`/api/folders/${encodeURIComponent(name)}`, { method: "DELETE" });
      if (res.ok) {
        showToast(`Folder "${name}" deleted.`);
        if (currentWatchlistFolder.toUpperCase() === name.toUpperCase()) {
          currentWatchlistFolder = "ALL";
        }
        await loadFolders();
        renderWatchlistTable();
      }
    } catch (err) {
      showToast("Failed to delete folder", true);
    }
  }

  async function loadWatchlist() {
    try {
      const res = await fetch("/api/watchlist");
      companiesList = await res.json();
      renderFolderTabs();
      renderWatchlistTable();
      renderAnalystSelectOptions();
      renderMultiAnalystChips();
      updateActionButtons();
    } catch (err) {
      console.error("Watchlist fetch failed", err);
    }
  }

  function getFolderClass(folder) {
    const f = (folder || "").toUpperCase();
    if (f === "GAME") return "folder-tag-game";
    if (f === "SET") return "folder-tag-set";
    if (f === "MATCH") return "folder-tag-match";
    if (f === "DEMO") return "folder-tag-demo";
    if (f === "JUNIOR") return "folder-tag-junior";
    return "folder-tag-custom";
  }

  let activeBasketPickerCompanyId = null;

  window.openBasketPicker = (event, companyId) => {
    event.stopPropagation();
    const comp = companiesList.find(c => c.id === companyId);
    if (!comp) return;

    activeBasketPickerCompanyId = companyId;
    const popover = document.getElementById("basket-picker-popover");
    const popoverItems = document.getElementById("basket-popover-items");
    const popoverCompName = document.getElementById("popover-company-name");
    if (!popover || !popoverItems) return;

    popoverCompName.textContent = `${comp.name} (${comp.nse_symbol || comp.id.toUpperCase()})`;
    const cFolders = getCompanyFolders(comp);

    popoverItems.innerHTML = availableFolders.map(fld => {
      const isAssigned = cFolders.includes(fld.toUpperCase());
      const tagClass = getFolderClass(fld);
      return `
        <div class="popover-basket-item ${isAssigned ? 'assigned' : ''}" onclick="window.toggleStockBasket('${comp.id}', '${fld}')">
          <div class="popover-basket-left">
            <span class="popover-checkbox">${isAssigned ? '✓' : ''}</span>
            <span class="folder-tag ${tagClass}">${fld}</span>
          </div>
          <span class="popover-basket-status">${isAssigned ? 'Assigned' : 'Click to add'}</span>
        </div>
      `;
    }).join("");

    // Position popover relative to clicked button
    const btn = event.currentTarget;
    const rect = btn.getBoundingClientRect();
    popover.style.display = "block";

    const popoverWidth = 245;
    let left = rect.left + window.scrollX;
    if (left + popoverWidth > window.innerWidth - 20) {
      left = window.innerWidth - popoverWidth - 20;
    }
    let top = rect.bottom + window.scrollY + 6;
    popover.style.left = `${left}px`;
    popover.style.top = `${top}px`;
  };

  window.toggleStockBasket = async (companyId, folder) => {
    const comp = companiesList.find(c => c.id === companyId);
    if (!comp) return;
    const cFolders = getCompanyFolders(comp);
    const isAssigned = cFolders.includes(folder.toUpperCase());

    if (isAssigned) {
      await window.removeStockFolder(companyId, folder);
    } else {
      await window.addStockFolder(companyId, folder);
    }

    // Refresh popover content if still open
    if (activeBasketPickerCompanyId === companyId) {
      const updatedComp = companiesList.find(c => c.id === companyId);
      if (updatedComp) {
        const updatedFolders = getCompanyFolders(updatedComp);
        const popoverItems = document.getElementById("basket-popover-items");
        if (popoverItems) {
          popoverItems.innerHTML = availableFolders.map(fld => {
            const assigned = updatedFolders.includes(fld.toUpperCase());
            const tagClass = getFolderClass(fld);
            return `
              <div class="popover-basket-item ${assigned ? 'assigned' : ''}" onclick="window.toggleStockBasket('${companyId}', '${fld}')">
                <div class="popover-basket-left">
                  <span class="popover-checkbox">${assigned ? '✓' : ''}</span>
                  <span class="folder-tag ${tagClass}">${fld}</span>
                </div>
                <span class="popover-basket-status">${assigned ? 'Assigned' : 'Click to add'}</span>
              </div>
            `;
          }).join("");
        }
      }
    }
  };

  // Close popover when clicking close button or anywhere outside
  const btnCloseBasketPopover = document.getElementById("btn-close-basket-popover");
  if (btnCloseBasketPopover) {
    btnCloseBasketPopover.addEventListener("click", () => {
      const popover = document.getElementById("basket-picker-popover");
      if (popover) popover.style.display = "none";
    });
  }

  const btnPopoverNewFolder = document.getElementById("btn-popover-new-folder");
  if (btnPopoverNewFolder) {
    btnPopoverNewFolder.addEventListener("click", () => {
      const popover = document.getElementById("basket-picker-popover");
      if (popover) popover.style.display = "none";
      if (modalAddFolder) modalAddFolder.classList.add("open");
    });
  }

  document.addEventListener("click", (e) => {
    const popover = document.getElementById("basket-picker-popover");
    if (!popover || popover.style.display === "none") return;
    if (!popover.contains(e.target) && !e.target.closest(".btn-add-basket-trigger")) {
      popover.style.display = "none";
    }
  });

  // Search Input Listeners for Watchlist
  if (watchlistSearchInput) {
    watchlistSearchInput.addEventListener("input", (e) => {
      watchlistSearchQuery = (e.target.value || "").trim().toLowerCase();
      if (btnClearWatchlistSearch) {
        btnClearWatchlistSearch.style.display = watchlistSearchQuery ? "inline-flex" : "none";
      }
      renderWatchlistTable();
    });
  }

  if (btnClearWatchlistSearch) {
    btnClearWatchlistSearch.addEventListener("click", () => {
      window.clearWatchlistSearch();
    });
  }

  window.clearWatchlistSearch = () => {
    if (watchlistSearchInput) watchlistSearchInput.value = "";
    watchlistSearchQuery = "";
    if (btnClearWatchlistSearch) btnClearWatchlistSearch.style.display = "none";
    renderWatchlistTable();
    if (watchlistSearchInput) watchlistSearchInput.focus();
  };

  function renderWatchlistTable() {
    if (!watchlistTableBody) return;

    if (watchlistTotalPill) {
      watchlistTotalPill.textContent = `${companiesList.length} Monitored Stocks`;
    }

    // 1. Filter by Basket / Folder
    let filtered = currentWatchlistFolder === "ALL"
      ? [...companiesList]
      : companiesList.filter(c => getCompanyFolders(c).includes(currentWatchlistFolder.toUpperCase()));

    // 2. Filter by Search Query (Name, Symbol, BSE Code, or Aliases)
    if (watchlistSearchQuery) {
      filtered = filtered.filter(c => {
        const name = (c.name || "").toLowerCase();
        const nse = (c.nse_symbol || "").toLowerCase();
        const bse = (c.bse_code || "").toLowerCase();
        const cid = (c.id || "").toLowerCase();
        const aliases = (c.aliases || []).map(a => String(a).toLowerCase());
        return name.includes(watchlistSearchQuery) ||
               nse.includes(watchlistSearchQuery) ||
               bse.includes(watchlistSearchQuery) ||
               cid.includes(watchlistSearchQuery) ||
               aliases.some(a => a.includes(watchlistSearchQuery));
      });
    }

    // Update visible count badge
    if (watchlistVisibleCount) {
      if (watchlistSearchQuery) {
        watchlistVisibleCount.textContent = `Showing ${filtered.length} of ${companiesList.length} stocks (matching "${watchlistSearchQuery}")`;
      } else if (currentWatchlistFolder !== "ALL") {
        watchlistVisibleCount.textContent = `Showing ${filtered.length} stocks in ${currentWatchlistFolder}`;
      } else {
        watchlistVisibleCount.textContent = `Showing ${filtered.length} of ${companiesList.length} stocks`;
      }
    }

    if (filtered.length === 0) {
      const msg = watchlistSearchQuery
        ? `No stocks found matching "<strong>${watchlistSearchQuery}</strong>" in basket <strong>${currentWatchlistFolder}</strong>.`
        : `No stocks currently in <strong>${currentWatchlistFolder}</strong> basket. Click "+ Add Stock" or assign a stock using the + Basket button!`;
      
      watchlistTableBody.innerHTML = `
        <tr>
          <td colspan="4" style="text-align: center; padding: 40px 20px; color: var(--text-dim);">
            <div style="font-size: 1.6rem; margin-bottom: 8px;">🔍</div>
            <div style="font-size: 0.88rem; color: var(--text-secondary);">${msg}</div>
            ${watchlistSearchQuery ? `<button type="button" class="btn-secondary-micro" onclick="window.clearWatchlistSearch()" style="margin-top: 14px; padding: 6px 16px; border-radius: 8px; cursor: pointer;">Clear Search</button>` : ''}
          </td>
        </tr>
      `;
      return;
    }

    watchlistTableBody.innerHTML = filtered.map(c => {
      const cFolders = getCompanyFolders(c);
      const symbol = (c.nse_symbol || c.id || "STK").toUpperCase();

      // Render pills for each assigned basket with dot and "x" to remove
      const pillsHtml = cFolders.map(fld => {
        const tagClass = getFolderClass(fld);
        return `
          <span class="folder-pill-removable folder-tag ${tagClass}">
            <span class="pill-dot"></span>
            <span>${fld}</span>
            <span class="tag-remove-x" title="Remove from ${fld}" onclick="window.removeStockFolder('${c.id}', '${fld}')">&times;</span>
          </span>
        `;
      }).join("");

      // Sleek + Basket button that triggers the floating glass popover
      const addTriggerHtml = `
        <button type="button" class="btn-add-basket-trigger" onclick="window.openBasketPicker(event, '${c.id}')" title="Assign to baskets">
          <span class="plus-icon">+</span> Basket
        </button>
      `;

      const folderCellHtml = `
        <div class="multi-basket-cell">
          ${pillsHtml}
          ${addTriggerHtml}
        </div>
      `;

      // Analysts who track this stock (via any matching basket or direct assignment)
      const assigned = analystsList
        .filter(a => {
          const aFlds = (a.assigned_folders || []).map(x => x.toUpperCase());
          const hasFolderOverlap = cFolders.some(f => aFlds.includes(f));
          return hasFolderOverlap || (a.assigned_companies || []).includes(c.id);
        })
        .map(a => `<span class="analyst-pill" title="Morning brief recipient">👤 ${a.name}</span>`);
      
      const assignedDisplay = assigned.length > 0
        ? `<div class="analyst-pill-wrap">${assigned.join("")}</div>`
        : `<span class="badge-unassigned" onclick="window.openEditStockModal('${c.id}')" title="Click to assign clients">+ Assign Client</span>`;

      return `
        <tr class="watchlist-row" data-stock-id="${c.id}">
          <!-- Column 1: Asset / Company -->
          <td>
            <div class="asset-cell">
              <div class="asset-symbol-chip" onclick="window.openEditStockModal('${c.id}')" title="Click to edit stock">${symbol.slice(0, 10)}</div>
              <div class="asset-info">
                <span class="asset-name" onclick="window.openEditStockModal('${c.id}')" title="Click to edit stock details">${c.name}</span>
                <div class="asset-sub-meta">
                  ${c.nse_symbol ? `<span class="exchange-tag nse">NSE: <strong>${c.nse_symbol}</strong></span>` : ''}
                </div>
              </div>
            </div>
          </td>

          <!-- Column 2: Basket / Portfolio -->
          <td>
            ${folderCellHtml}
          </td>

          <!-- Column 3: Client Coverage -->
          <td>
            ${assignedDisplay}
          </td>

          <!-- Column 4: Actions -->
          <td style="text-align: right;">
            <div class="row-actions-cell">
              <button type="button" class="btn-row-edit" onclick="window.openEditStockModal('${c.id}')" title="Edit stock tickers & coverage">
                <span class="action-icon">✏️</span>
                <span>Edit</span>
              </button>
              <button type="button" class="btn-row-del" onclick="deleteStock('${c.id}')" title="Remove stock from watchlist">
                <span class="action-icon">🗑️</span>
              </button>
            </div>
          </td>
        </tr>
      `;
    }).join("");
  }

  window.addStockFolder = async (id, folder) => {
    try {
      const res = await fetch(`/api/watchlist/${id}/add-folder`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ folder })
      });
      if (res.ok) {
        showToast(`Added to ${folder} basket`);
        await loadWatchlist();
        await loadAnalysts();
      } else {
        showToast("Error adding basket", true);
      }
    } catch (err) {
      showToast("Network error adding basket", true);
    }
  };

  window.removeStockFolder = async (id, folder) => {
    try {
      const res = await fetch(`/api/watchlist/${id}/remove-folder`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ folder })
      });
      if (res.ok) {
        showToast(`Removed from ${folder}`);
        await loadWatchlist();
        await loadAnalysts();
      } else {
        showToast("Error removing basket", true);
      }
    } catch (err) {
      showToast("Network error removing basket", true);
    }
  };

  window.changeStockFolder = async (id, newFolder) => {
    try {
      const res = await fetch(`/api/watchlist/${id}/folder`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ folder: newFolder })
      });
      if (res.ok) {
        showToast(newFolder ? `Assigned to ${newFolder} basket` : "Moved to unassigned (ALL only)");
        await loadWatchlist();
        await loadAnalysts();
      } else {
        showToast("Error updating folder", true);
      }
    } catch (err) {
      showToast("Network error updating folder", true);
    }
  };

  window.deleteStock = async (id) => {
    if (!confirm("Remove this company from the watchlist?")) return;
    try {
      const res = await fetch(`/api/watchlist/${id}`, { method: "DELETE" });
      if (res.ok) {
        showToast("Stock removed.");
        await loadWatchlist();
        loadStats();
      }
    } catch (e) {
      showToast("Delete failed", true);
    }
  };

  // Add Folder Modal Events
  if (btnOpenAddFolder) {
    btnOpenAddFolder.addEventListener("click", () => {
      if (formAddFolder) formAddFolder.reset();
      if (modalAddFolder) modalAddFolder.classList.add("open");
    });
  }
  if (btnCloseFolderModal) {
    btnCloseFolderModal.addEventListener("click", () => modalAddFolder.classList.remove("open"));
  }
  if (btnCancelFolderModal) {
    btnCancelFolderModal.addEventListener("click", () => modalAddFolder.classList.remove("open"));
  }

  if (formAddFolder) {
    formAddFolder.addEventListener("submit", async (e) => {
      e.preventDefault();
      const folderName = (inputFolderName.value || "").trim().toUpperCase();
      if (!folderName) {
        showToast("Please enter a folder name", true);
        return;
      }

      try {
        const res = await fetch("/api/folders", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ name: folderName })
        });
        if (res.ok) {
          showToast(`Created folder "${folderName}"!`);
          modalAddFolder.classList.remove("open");
          formAddFolder.reset();
          currentWatchlistFolder = folderName;
          await loadFolders();
          renderWatchlistTable();
        } else {
          const err = await res.json();
          showToast(err.detail || "Error creating folder", true);
        }
      } catch (err) {
        showToast("Network error creating folder", true);
      }
    });
  }

  // Add Stock Modal Events
  function renderStockFoldersCheckboxes(selected = []) {
    if (!stockFoldersCheckboxes) return;
    if (!availableFolders.length) {
      stockFoldersCheckboxes.innerHTML = `<span style="font-size:0.75rem; color:var(--text-dim); padding:4px;">No folders created yet.</span>`;
      return;
    }
    const selUpper = (selected || []).map(f => f.toUpperCase());
    stockFoldersCheckboxes.innerHTML = availableFolders.map(f => {
      const isChecked = selUpper.includes(f.toUpperCase()) ? 'checked' : '';
      let tagClass = "folder-tag-custom";
      if (f === "GAME") tagClass = "folder-tag-game";
      else if (f === "SET") tagClass = "folder-tag-set";
      else if (f === "MATCH") tagClass = "folder-tag-match";
      return `
        <label class="folder-checkbox-tag">
          <input type="checkbox" name="stock_folder" value="${f}" ${isChecked}>
          <span class="folder-tag ${tagClass}" style="margin:0;">${f}</span>
        </label>
      `;
    }).join("");
  }

  btnOpenAddStock.addEventListener("click", () => {
    let initialFolders = [];
    if (currentWatchlistFolder !== "ALL" && availableFolders.includes(currentWatchlistFolder)) {
      initialFolders = [currentWatchlistFolder];
    } else if (availableFolders.includes("GAME")) {
      initialFolders = ["GAME"];
    }
    renderStockFoldersCheckboxes(initialFolders);

    // Populate manual analyst checkboxes (UNCHECKED by default - 100% manual control)
    if (stockAnalystsCheckboxes) {
      if (!analystsList.length) {
        stockAnalystsCheckboxes.innerHTML = `<span style="font-size:0.75rem; color:var(--text-dim); padding:4px;">No analysts registered yet.</span>`;
      } else {
        stockAnalystsCheckboxes.innerHTML = analystsList.map(a => `
          <label class="checkbox-item" style="padding: 4px 6px;">
            <input type="checkbox" name="stock_assigned_analyst" value="${a.id}">
            <span><strong>${a.name}</strong> <span style="color:var(--text-dim); font-size:0.72rem;">(+91 ${a.phone})</span></span>
          </label>
        `).join("");
      }
    }
    modalAddStock.classList.add("open");
  });

  btnCloseStockModal.addEventListener("click", () => modalAddStock.classList.remove("open"));
  btnCancelStockModal.addEventListener("click", () => modalAddStock.classList.remove("open"));

  formAddStock.addEventListener("submit", async (e) => {
    e.preventDefault();
    const name = document.getElementById("input-comp-name").value.trim();
    const nse = document.getElementById("input-comp-nse").value.trim().toUpperCase();
    const bse = document.getElementById("input-comp-bse").value.trim();
    const aliases = document.getElementById("input-comp-aliases").value.split(",").map(s => s.trim()).filter(Boolean);
    
    // Checked baskets
    const checkedFolderBoxes = document.querySelectorAll('input[name="stock_folder"]:checked');
    const folders = Array.from(checkedFolderBoxes).map(cb => cb.value.trim().toUpperCase()).filter(Boolean);

    // Manually checked analysts (None checked by default)
    const checkedBoxes = document.querySelectorAll('input[name="stock_assigned_analyst"]:checked');
    const assignedAnalystIds = Array.from(checkedBoxes).map(cb => cb.value);

    const payload = {
      id: name.toLowerCase().replace(/[^a-z0-9]/g, "").slice(0, 16),
      name,
      nse_symbol: nse,
      bse_code: "",
      aliases: [name, nse].filter(Boolean),
      search_queries: [`"${name}"`],
      folder: folders.join(", "),
      folders: folders,
      assigned_analyst_ids: assignedAnalystIds
    };

    try {
      const res = await fetch("/api/watchlist", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload)
      });
      if (res.ok) {
        showToast(`Added ${name} to baskets: ${folders.join(", ") || "ALL"}!`);
        modalAddStock.classList.remove("open");
        formAddStock.reset();
        await loadAnalysts(); // Keep analysts' stock lists synchronized
        await loadWatchlist();
        loadStats();
      } else {
        showToast("Error adding stock", true);
      }
    } catch (err) {
      showToast("Error adding company", true);
    }
  });

  // Edit Stock Modal Events
  window.openEditStockModal = (companyId) => {
    const comp = companiesList.find(c => c.id === companyId);
    if (!comp) return;

    if (editCompId) editCompId.value = comp.id;
    if (editCompName) editCompName.value = comp.name;
    if (editCompNse) editCompNse.value = comp.nse_symbol || "";

    const modalTitle = document.getElementById("edit-stock-modal-title");
    if (modalTitle) modalTitle.textContent = `Edit Stock: ${comp.name}`;

    // Render Baskets
    const cFolders = getCompanyFolders(comp);
    if (editStockFoldersCheckboxes) {
      if (!availableFolders.length) {
        editStockFoldersCheckboxes.innerHTML = `<span style="font-size:0.75rem; color:var(--text-dim); padding:4px;">No folders available.</span>`;
      } else {
        editStockFoldersCheckboxes.innerHTML = availableFolders.map(f => {
          const isChecked = cFolders.includes(f.toUpperCase()) ? 'checked' : '';
          const tagClass = getFolderClass(f);
          return `
            <label class="folder-checkbox-tag">
              <input type="checkbox" name="edit_stock_folder" value="${f}" ${isChecked}>
              <span class="folder-tag ${tagClass}" style="margin:0;">${f}</span>
            </label>
          `;
        }).join("");
      }
    }

    // Render Analyst Coverage Checkboxes
    if (editStockAnalystsCheckboxes) {
      if (!analystsList.length) {
        editStockAnalystsCheckboxes.innerHTML = `<span style="font-size:0.75rem; color:var(--text-dim); padding:4px;">No analysts registered.</span>`;
      } else {
        editStockAnalystsCheckboxes.innerHTML = analystsList.map(a => {
          const isAssigned = (a.assigned_companies || []).includes(comp.id);
          return `
            <label class="checkbox-item" style="padding: 4px 6px;">
              <input type="checkbox" name="edit_stock_assigned_analyst" value="${a.id}" ${isAssigned ? 'checked' : ''}>
              <span><strong>${a.name}</strong> <span style="color:var(--text-dim); font-size:0.72rem;">(+91 ${a.phone})</span></span>
            </label>
          `;
        }).join("");
      }
    }

    if (modalEditStock) modalEditStock.classList.add("open");
  };

  if (btnCloseEditStockModal) {
    btnCloseEditStockModal.addEventListener("click", () => modalEditStock.classList.remove("open"));
  }
  if (btnCancelEditStockModal) {
    btnCancelEditStockModal.addEventListener("click", () => modalEditStock.classList.remove("open"));
  }

  if (btnDeleteFromEditModal) {
    btnDeleteFromEditModal.addEventListener("click", async () => {
      const cid = editCompId.value;
      if (!cid) return;
      modalEditStock.classList.remove("open");
      await window.deleteStock(cid);
    });
  }

  if (formEditStock) {
    formEditStock.addEventListener("submit", async (e) => {
      e.preventDefault();
      const id = editCompId.value;
      const comp = companiesList.find(c => c.id === id);
      const name = editCompName.value.trim();
      const nse = (editCompNse.value || "").trim().toUpperCase();

      const checkedFolderBoxes = document.querySelectorAll('input[name="edit_stock_folder"]:checked');
      const folders = Array.from(checkedFolderBoxes).map(cb => cb.value.trim().toUpperCase()).filter(Boolean);

      const checkedAnalystBoxes = document.querySelectorAll('input[name="edit_stock_assigned_analyst"]:checked');
      const assignedAnalystIds = Array.from(checkedAnalystBoxes).map(cb => cb.value);

      const payload = {
        id,
        name,
        nse_symbol: nse,
        bse_code: comp ? (comp.bse_code || "") : "",
        aliases: comp ? (comp.aliases || [name, nse].filter(Boolean)) : [name, nse].filter(Boolean),
        search_queries: [`"${name}"`],
        folder: folders.join(", "),
        folders,
        assigned_analyst_ids: assignedAnalystIds
      };

      try {
        const res = await fetch("/api/watchlist", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(payload)
        });
        if (res.ok) {
          showToast(`Updated ${name} successfully!`);
          modalEditStock.classList.remove("open");
          await loadAnalysts();
          await loadWatchlist();
          loadStats();
        } else {
          showToast("Error updating stock", true);
        }
      } catch (err) {
        showToast("Network error updating stock", true);
      }
    });
  }

  // 11. Data Sources Feeds & Feed Radar
  function escapeHtml(str) {
    if (!str) return "";
    return String(str)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;")
      .replace(/'/g, "&#039;");
  }

  async function loadSources() {
    try {
      const res = await fetch("/api/sources");
      const dbSources = await res.json();

      const googleSearchRadar = {
        id: "sys-google-news-radar",
        name: "Google News Financial Radar",
        url: "https://news.google.com/rss/search?q=india+stock+market",
        type: "search",
        keep_pattern: null,
        language: "en-IN",
        body_check: 1,
        is_active: 1,
        is_system: true,
        status: "OK",
        items_count: 0
      };

      allSourcesList = [googleSearchRadar, ...dbSources];

      const totalAll = allSourcesList.length;
      const totalFiling = allSourcesList.filter(s => s.type === "filing").length;
      const totalRss = allSourcesList.filter(s => s.type === "rss" || s.type === "sitemap").length;
      const totalSearch = allSourcesList.filter(s => s.type === "search").length;

      if (filterCountAll) filterCountAll.textContent = totalAll;
      if (filterCountFiling) filterCountFiling.textContent = totalFiling;
      if (filterCountRss) filterCountRss.textContent = totalRss;
      if (filterCountSearch) filterCountSearch.textContent = totalSearch;
      if (sourcesTotalPill) sourcesTotalPill.textContent = `${totalAll} Feeds Connected`;

      renderSourcesGrid();
    } catch (err) {
      console.error("Sources fetch error", err);
      if (sourcesListContainer) {
        sourcesListContainer.innerHTML = `<div style="grid-column: 1/-1; padding: 30px; text-align: center; color: var(--text-muted);">Failed to load data feeds. Please retry.</div>`;
      }
    }
  }

  function renderSourcesGrid() {
    if (!sourcesListContainer) return;

    const filtered = allSourcesList.filter(s => {
      if (currentSourceCategory === "filing" && s.type !== "filing") return false;
      if (currentSourceCategory === "rss" && s.type !== "rss" && s.type !== "sitemap") return false;
      if (currentSourceCategory === "search" && s.type !== "search") return false;

      if (sourcesSearchQuery) {
        const q = sourcesSearchQuery.toLowerCase();
        const matchesName = (s.name || "").toLowerCase().includes(q);
        const matchesUrl = (s.url || "").toLowerCase().includes(q);
        const matchesType = (s.type || "").toLowerCase().includes(q);
        if (!matchesName && !matchesUrl && !matchesType) return false;
      }
      return true;
    });

    if (sourcesVisibleCount) {
      sourcesVisibleCount.textContent = `Showing ${filtered.length} of ${allSourcesList.length} feeds`;
    }

    if (filtered.length === 0) {
      sourcesListContainer.innerHTML = `
        <div style="grid-column: 1/-1; padding: 48px 24px; text-align: center; background: rgba(15,23,42,0.4); border: 1px dashed var(--border-subtle); border-radius: 12px;">
          <div style="font-size: 2.2rem; margin-bottom: 8px;">📡</div>
          <div style="font-size: 1.05rem; font-weight: 700; color: #fff;">No Feeds Matched</div>
          <div style="font-size: 0.82rem; color: var(--text-muted); margin-top: 4px;">Try searching with different keywords or change the category filter above.</div>
        </div>
      `;
      return;
    }

    sourcesListContainer.innerHTML = filtered.map(s => {
      const isPaused = !s.is_active;
      const type = (s.type || "rss").toLowerCase();

      let avatarIcon = "📰";
      let typeLabel = "RSS 2.0 Feed";
      let typeClass = "rss";
      let formatVal = "XML / RSS";

      if (type === "filing") {
        avatarIcon = "🏛️";
        typeLabel = "Exchange Filing";
        typeClass = "filing";
        formatVal = "HTML / JSON";
      } else if (type === "search") {
        avatarIcon = "⚡";
        typeLabel = "Search Radar";
        typeClass = "search";
        formatVal = "Search API";
      } else if (type === "sitemap") {
        avatarIcon = "🗺️";
        typeLabel = "Publisher Sitemap";
        typeClass = "rss";
        formatVal = "XML Sitemap";
      }

      const ping = sourcePingResults[s.id];
      let pingHtml = `<span class="source-ping-badge ${isPaused ? '' : 'ok'}"><span class="source-pulse-dot" style="${isPaused ? 'background: #64748b; box-shadow: none;' : ''}"></span> ${isPaused ? 'PAUSED' : 'ACTIVE'}</span>`;

      if (ping) {
        if (ping.status === "testing") {
          pingHtml = `<span class="source-ping-badge" style="color: var(--accent-emerald);"><span class="source-pulse-dot"></span> Pinging...</span>`;
        } else if (ping.status === "online") {
          pingHtml = `<span class="source-ping-badge ok" title="${ping.msg}">✓ ${ping.http_code} OK (${ping.latency_ms}ms)</span>`;
        } else if (ping.status === "warning") {
          pingHtml = `<span class="source-ping-badge warn" title="${ping.msg}">⚠ HTTP ${ping.http_code} (${ping.latency_ms}ms)</span>`;
        } else {
          pingHtml = `<span class="source-ping-badge err" title="${ping.msg}">✕ Error (${ping.latency_ms}ms)</span>`;
        }
      }

      const bodyCheckVal = s.body_check ? "Full Article" : "Headline Only";
      const intervalVal = type === "filing" ? "Every 15m" : "Every 30m";
      const isSystemFeed = s.is_system || type === "filing";

      return `
        <div class="source-feed-card ${isPaused ? 'is-paused' : ''}" data-feed-id="${s.id}">
          <div class="source-feed-card-header">
            <div class="source-brand-wrap">
              <div class="source-brand-avatar ${typeClass}">${avatarIcon}</div>
              <div class="source-feed-info">
                <div class="source-feed-title" title="${escapeHtml(s.name)}">${escapeHtml(s.name)}</div>
                <div class="source-feed-type-tag ${typeClass}">
                  <span>${typeLabel}</span>
                </div>
              </div>
            </div>
            <label class="switch-toggle" title="${isPaused ? 'Click to Activate feed' : 'Click to Pause feed'}">
              <input type="checkbox" class="source-toggle-input" data-id="${s.id}" ${s.is_active ? 'checked' : ''}>
              <span class="switch-slider"></span>
            </label>
          </div>

          <div class="source-url-bar">
            <span class="source-url-text" title="${escapeHtml(s.url)}">${escapeHtml(s.url)}</span>
            <div class="source-url-actions">
              <button class="btn-icon-micro btn-copy-feed-url" data-url="${escapeHtml(s.url)}" title="Copy Feed URL">📋</button>
              <a href="${escapeHtml(s.url)}" target="_blank" rel="noopener noreferrer" class="btn-icon-micro" title="Open URL in New Tab">↗</a>
            </div>
          </div>

          <div class="source-specs-grid">
            <div class="source-spec-item">
              <span class="source-spec-label">Format</span>
              <span class="source-spec-val">${formatVal}</span>
            </div>
            <div class="source-spec-item">
              <span class="source-spec-label">Body Check</span>
              <span class="source-spec-val" style="color: ${s.body_check ? '#34d399' : 'var(--text-muted)'};">${bodyCheckVal}</span>
            </div>
            <div class="source-spec-item">
              <span class="source-spec-label">Poll Cycle</span>
              <span class="source-spec-val">${intervalVal}</span>
            </div>
          </div>

          <div class="source-card-footer">
            <div id="source-ping-container-${s.id}">
              ${pingHtml}
            </div>
            <div class="source-card-btns">
              <button class="btn-ping-feed" data-id="${s.id}" data-url="${escapeHtml(s.url)}">
                <span>⚡</span> Ping
              </button>
              ${!isSystemFeed ? `
                <button class="btn-delete-feed" data-id="${s.id}" data-name="${escapeHtml(s.name)}" title="Remove Feed">
                  🗑️
                </button>
              ` : ''}
            </div>
          </div>
        </div>
      `;
    }).join("");
  }

  // Category filter tabs
  document.querySelectorAll(".source-filter-btn").forEach(btn => {
    btn.addEventListener("click", () => {
      document.querySelectorAll(".source-filter-btn").forEach(b => b.classList.remove("active"));
      btn.classList.add("active");
      currentSourceCategory = btn.dataset.type;
      renderSourcesGrid();
    });
  });

  // Sources search input & clear button
  if (sourcesSearchInput) {
    sourcesSearchInput.addEventListener("input", (e) => {
      sourcesSearchQuery = e.target.value.trim();
      if (btnClearSourcesSearch) {
        btnClearSourcesSearch.style.display = sourcesSearchQuery ? "block" : "none";
      }
      renderSourcesGrid();
    });
  }

  if (btnClearSourcesSearch) {
    btnClearSourcesSearch.addEventListener("click", () => {
      sourcesSearchInput.value = "";
      sourcesSearchQuery = "";
      btnClearSourcesSearch.style.display = "none";
      renderSourcesGrid();
    });
  }

  // Sources list container delegated events: toggle, copy, ping, delete
  if (sourcesListContainer) {
    sourcesListContainer.addEventListener("change", async (e) => {
      if (e.target.classList.contains("source-toggle-input")) {
        const id = e.target.dataset.id;
        const isChecked = e.target.checked;
        const feedCard = e.target.closest(".source-feed-card");
        if (feedCard) {
          feedCard.classList.toggle("is-paused", !isChecked);
        }

        const src = allSourcesList.find(s => String(s.id) === String(id));
        if (src) src.is_active = isChecked ? 1 : 0;

        if (id === "sys-google-news-radar") {
          showToast(`Google News Radar ${isChecked ? "activated" : "paused"}`);
          return;
        }

        try {
          const res = await fetch(`/api/sources/${id}/toggle`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ is_active: isChecked })
          });
          if (res.ok) {
            showToast(`${src ? src.name : "Feed"} ${isChecked ? "activated" : "paused"}`);
          } else {
            showToast("Failed to update feed state", true);
          }
        } catch (err) {
          showToast("Network error updating feed state", true);
        }
      }
    });

    sourcesListContainer.addEventListener("click", async (e) => {
      const copyBtn = e.target.closest(".btn-copy-feed-url");
      if (copyBtn) {
        const url = copyBtn.dataset.url;
        if (url) {
          navigator.clipboard.writeText(url).then(() => {
            showToast("Feed URL copied to clipboard");
          }).catch(() => {
            showToast("Copied: " + url);
          });
        }
        return;
      }

      const pingBtn = e.target.closest(".btn-ping-feed");
      if (pingBtn) {
        const id = pingBtn.dataset.id;
        const url = pingBtn.dataset.url;
        await testFeedPing(id, url, pingBtn);
        return;
      }

      const delBtn = e.target.closest(".btn-delete-feed");
      if (delBtn) {
        const id = delBtn.dataset.id;
        const name = delBtn.dataset.name;
        if (confirm(`Are you sure you want to remove "${name}" from data feeds?`)) {
          try {
            const res = await fetch(`/api/sources/${id}`, { method: "DELETE" });
            if (res.ok) {
              showToast(`Feed removed: ${name}`);
              loadSources();
            } else {
              showToast("Failed to remove feed", true);
            }
          } catch (err) {
            showToast("Network error removing feed", true);
          }
        }
      }
    });
  }

  async function testFeedPing(id, url, pingBtn) {
    if (pingBtn) {
      pingBtn.disabled = true;
      pingBtn.innerHTML = `<span>⏳</span> Pinging...`;
    }
    sourcePingResults[id] = { status: "testing" };
    renderSourcesGrid();

    try {
      const res = await fetch("/api/sources/ping", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ url: url })
      });
      const data = await res.json();
      sourcePingResults[id] = data;
      if (data.status === "online") {
        showToast(`✓ Ping successful: ${data.msg}`);
      } else {
        showToast(`Feed Ping notice: ${data.msg}`, true);
      }
    } catch (err) {
      sourcePingResults[id] = { status: "error", latency_ms: 0, http_code: 0, msg: "Network error" };
      showToast("Feed ping timeout or network failure", true);
    } finally {
      renderSourcesGrid();
    }
  }

  // Ping All Feeds button
  if (btnPingAllSources) {
    btnPingAllSources.addEventListener("click", async () => {
      btnPingAllSources.disabled = true;
      btnPingAllSources.innerHTML = `<span class="btn-icon">⏳</span> Pinging Feeds...`;
      showToast("Testing connectivity across all active feeds...");

      const activeFeeds = allSourcesList.filter(s => s.is_active);
      let successCount = 0;

      for (const feed of activeFeeds) {
        sourcePingResults[feed.id] = { status: "testing" };
      }
      renderSourcesGrid();

      await Promise.all(activeFeeds.map(async (feed) => {
        try {
          const res = await fetch("/api/sources/ping", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ url: feed.url })
          });
          const data = await res.json();
          sourcePingResults[feed.id] = data;
          if (data.status === "online") successCount++;
        } catch (err) {
          sourcePingResults[feed.id] = { status: "error", latency_ms: 0, http_code: 0, msg: "Network error" };
        }
      }));

      btnPingAllSources.disabled = false;
      btnPingAllSources.innerHTML = `<span class="btn-icon">⚡</span> Ping All Feeds`;
      renderSourcesGrid();
      showToast(`Ping completed: ${successCount} of ${activeFeeds.length} feeds verified online!`);
    });
  }

  // Add Source Modal handling
  if (btnOpenAddSourceModal) {
    btnOpenAddSourceModal.addEventListener("click", () => {
      if (modalAddSource) modalAddSource.classList.add("active");
    });
  }

  function closeAddSourceModal() {
    if (modalAddSource) modalAddSource.classList.remove("active");
    if (formAddSource) formAddSource.reset();
  }

  if (btnCloseSourceModal) btnCloseSourceModal.addEventListener("click", closeAddSourceModal);
  if (btnCancelSourceModal) btnCancelSourceModal.addEventListener("click", closeAddSourceModal);

  if (formAddSource) {
    formAddSource.addEventListener("submit", async (e) => {
      e.preventDefault();
      const name = document.getElementById("input-source-name").value.trim();
      const url = document.getElementById("input-source-url").value.trim();
      const type = document.getElementById("input-source-type").value;
      const bodyCheck = document.getElementById("input-source-bodycheck").checked;

      if (!name || !url) {
        showToast("Please provide feed name and endpoint URL", true);
        return;
      }

      const submitBtn = document.getElementById("btn-submit-source");
      if (submitBtn) {
        submitBtn.disabled = true;
        submitBtn.textContent = "Verifying & Saving...";
      }

      try {
        const res = await fetch("/api/sources", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            name: name,
            url: url,
            type: type,
            body_check: bodyCheck ? 1 : 0,
            is_active: 1
          })
        });

        if (res.ok) {
          showToast(`Feed connected: ${name}`);
          closeAddSourceModal();
          loadSources();
        } else {
          const errData = await res.json();
          showToast(`Error: ${errData.detail || 'Could not save feed'}`, true);
        }
      } catch (err) {
        showToast("Network error connecting feed", true);
      } finally {
        if (submitBtn) {
          submitBtn.disabled = false;
          submitBtn.textContent = "Save & Activate Feed";
        }
      }
    });
  }

  // 12. Run Crawl Trigger Button
  btnTriggerCrawl.addEventListener("click", async () => {
    btnTriggerCrawl.disabled = true;
    crawlerStatusBadge.textContent = "CRAWLING";
    crawlerStatusBadge.style.color = "var(--text-amber)";
    crawlBtnText.textContent = "Crawling Market...";
    showToast("Starting market sweep (BSE, NSE, Publishers, Google News)...");

    try {
      const res = await fetch("/api/crawl/run", { method: "POST" });
      const data = await res.json();
      showToast(`Crawl finished: Found ${data.items_found} items, stored ${data.stories_saved} stories.`);
      loadStats();
      loadAnalystStoriesPreview(currentAnalystId);
      loadLogs();
    } catch (err) {
      showToast("Crawl error or network timeout", true);
    } finally {
      btnTriggerCrawl.disabled = false;
      crawlerStatusBadge.textContent = "IDLE";
      crawlerStatusBadge.style.color = "var(--text-green)";
      crawlBtnText.textContent = "Run Crawl Now";
    }
  });

  // 13. Interactive KPI Drilldown Quick-View Modal
  function initKpiDrilldowns() {
    const modal = document.getElementById("modal-kpi-drilldown");
    if (!modal) return;

    const btnClose = document.getElementById("btn-close-drilldown-modal");
    const btnDismiss = document.getElementById("btn-dismiss-drilldown");
    const modalIcon = document.getElementById("drilldown-modal-icon");
    const modalTitle = document.getElementById("drilldown-modal-title");
    const modalSubtitle = document.getElementById("drilldown-modal-subtitle");
    const modalBody = document.getElementById("drilldown-modal-body");
    const searchInput = document.getElementById("drilldown-search-input");
    const countBadge = document.getElementById("drilldown-count-badge");

    let currentItems = [];
    let currentRenderFn = null;

    function closeModal() {
      modal.classList.remove("open");
      if (searchInput) searchInput.value = "";
    }

    if (btnClose) btnClose.addEventListener("click", closeModal);
    if (btnDismiss) btnDismiss.addEventListener("click", closeModal);
    modal.addEventListener("click", (e) => {
      if (e.target === modal) closeModal();
    });

    if (searchInput) {
      searchInput.addEventListener("input", (e) => {
        const q = e.target.value.trim().toLowerCase();
        if (!currentRenderFn) return;
        if (!q) {
          currentRenderFn(currentItems);
          return;
        }
        const filtered = currentItems.filter(item => {
          const str = JSON.stringify(item).toLowerCase();
          return str.includes(q);
        });
        currentRenderFn(filtered);
      });
    }

    function openModalWithConfig(icon, title, subtitle) {
      modalIcon.textContent = icon;
      modalTitle.textContent = title;
      modalSubtitle.textContent = subtitle;
      if (searchInput) searchInput.value = "";
      modalBody.innerHTML = `<div class="loading-line">&#9696; Loading details...</div>`;
      modal.classList.add("open");
    }

    // 1. Stories Curated Drilldown
    const cardStories = document.getElementById("kpi-card-stories");
    if (cardStories) {
      cardStories.addEventListener("click", async () => {
        openModalWithConfig("📰", "Curated Stories Today", "All live news stories curated across tracked watchlist companies");
        try {
          const res = await fetch("/api/stories?limit=300");
          const stories = await res.json();
          currentItems = stories;
          
          currentRenderFn = (items) => {
            countBadge.textContent = `${items.length} stories found`;
            if (!items.length) {
              modalBody.innerHTML = `<div style="padding: 24px; text-align: center; color: var(--text-muted);">No stories matching your search.</div>`;
              return;
            }
            modalBody.innerHTML = items.slice(0, 100).map(s => {
              const isFiling = s.source_type === "filing";
              const cname = s.company_name || s.company_id || "Company";
              const sources = (s.sources || []).map(x => x.name).join(" • ") || s.source_name || "News";
              return `
                <div class="drilldown-item-card">
                  <div style="display: flex; justify-content: space-between; align-items: center; gap: 8px;">
                    <span class="ticker-badge ${isFiling ? 'badge-filing' : ''}">${isFiling ? '🏛️ ' : ''}${cname.toUpperCase()}</span>
                    <span style="font-size: 0.72rem; color: var(--text-muted); font-family: var(--font-mono);">${sources}</span>
                  </div>
                  <a href="${s.url || '#'}" target="_blank" rel="noopener" style="color: #f1f5f9; font-size: 0.88rem; font-weight: 600; text-decoration: none; line-height: 1.4;">
                    ${s.title}
                  </a>
                </div>
              `;
            }).join("");
          };

          currentRenderFn(currentItems);
        } catch (e) {
          modalBody.innerHTML = `<div style="color: var(--rose);">Failed to load stories details.</div>`;
        }
      });
    }

    // 2. Exchange Filings Drilldown
    const cardFilings = document.getElementById("kpi-card-filings");
    if (cardFilings) {
      cardFilings.addEventListener("click", async () => {
        openModalWithConfig("🏛️", "Exchange Filings (BSE & NSE)", "Official disclosures, financial results & regulatory announcements");
        try {
          const res = await fetch("/api/stories?source_type=filing&limit=150");
          const filings = await res.json();
          currentItems = filings;

          currentRenderFn = (items) => {
            countBadge.textContent = `${items.length} filings found`;
            if (!items.length) {
              modalBody.innerHTML = `<div style="padding: 24px; text-align: center; color: var(--text-muted);">No exchange filings found.</div>`;
              return;
            }
            modalBody.innerHTML = items.map(f => {
              const cname = f.company_name || f.company_id || "Disclosure";
              return `
                <div class="drilldown-item-card" style="border-left: 3px solid #f59e0b;">
                  <div style="display: flex; justify-content: space-between; align-items: center; gap: 8px;">
                    <span class="ticker-badge badge-filing">🏛️ ${cname.toUpperCase()}</span>
                    <span style="font-size: 0.72rem; color: #fbbf24; font-family: var(--font-mono); font-weight: 600;">Official Filing</span>
                  </div>
                  <a href="${f.url || '#'}" target="_blank" rel="noopener" style="color: #f1f5f9; font-size: 0.88rem; font-weight: 600; text-decoration: none; line-height: 1.4;">
                    ${f.title}
                  </a>
                  <div style="font-size: 0.74rem; color: var(--text-muted); display: flex; gap: 12px; margin-top: 2px;">
                    <span>Source: ${f.source_name || 'Stock Exchange'}</span>
                    <span>•</span>
                    <a href="${f.url || '#'}" target="_blank" rel="noopener" style="color: var(--sky); text-decoration: underline;">View Announcement PDF ↗</a>
                  </div>
                </div>
              `;
            }).join("");
          };

          currentRenderFn(currentItems);
        } catch (e) {
          modalBody.innerHTML = `<div style="color: var(--rose);">Failed to load filings details.</div>`;
        }
      });
    }

    // 3. Active Clients Drilldown
    const cardClients = document.getElementById("kpi-card-clients");
    if (cardClients) {
      cardClients.addEventListener("click", () => {
        openModalWithConfig("👥", "Active Clients & Subscribers", "Investors receiving customized morning market intelligence briefings");
        currentItems = analystsList;

        currentRenderFn = (items) => {
          countBadge.textContent = `${items.length} clients registered`;
          if (!items.length) {
            modalBody.innerHTML = `<div style="padding: 24px; text-align: center; color: var(--text-muted);">No clients registered.</div>`;
            return;
          }
          modalBody.innerHTML = items.map(a => {
            const stockCount = getAnalystCoveredStockCount(a);
            const folders = (a.assigned_folders || []).map(f => `<span class="folder-tag folder-tag-custom" style="font-size: 0.7rem;">${f}</span>`).join(" ");
            return `
              <div class="drilldown-item-card" style="flex-direction: row; justify-content: space-between; align-items: center;">
                <div style="display: flex; align-items: center; gap: 12px;">
                  <div class="analyst-avatar-badge" style="background: linear-gradient(135deg, #6366f1, #4338ca);">${a.name.slice(0, 2).toUpperCase()}</div>
                  <div>
                    <div style="font-size: 0.92rem; font-weight: 700; color: #fff;">${a.name}</div>
                    <div style="font-size: 0.76rem; color: var(--text-secondary); font-family: var(--font-mono);">📱 +91 ${a.phone} ${a.email ? '&bull; ' + a.email : ''}</div>
                  </div>
                </div>
                <div style="text-align: right;">
                  <div style="display: flex; gap: 4px; justify-content: flex-end; margin-bottom: 4px;">${folders || '<span style="font-size: 0.72rem; color: var(--text-muted);">All Baskets</span>'}</div>
                  <span style="font-size: 0.74rem; color: var(--text-muted); font-weight: 600;">${stockCount} Covered Stocks</span>
                </div>
              </div>
            `;
          }).join("");
        };

        currentRenderFn(currentItems);
      });
    }

    // 4. Active Companies Drilldown
    const cardCompanies = document.getElementById("kpi-card-companies");
    if (cardCompanies) {
      cardCompanies.addEventListener("click", () => {
        openModalWithConfig("🏢", "Monitored Watchlist Stocks", "All company tickers tracked in your database across BSE & NSE");
        currentItems = companiesList;

        currentRenderFn = (items) => {
          countBadge.textContent = `${items.length} stocks tracked`;
          if (!items.length) {
            modalBody.innerHTML = `<div style="padding: 24px; text-align: center; color: var(--text-muted);">No stocks currently in watchlist.</div>`;
            return;
          }
          modalBody.innerHTML = items.map(c => {
            const flds = getCompanyFolders(c).map(f => `<span class="folder-tag folder-tag-custom" style="font-size: 0.68rem;">${f}</span>`).join(" ");
            return `
              <div class="drilldown-item-card" style="flex-direction: row; justify-content: space-between; align-items: center;">
                <div style="display: flex; align-items: center; gap: 10px;">
                  <span class="ticker-badge" style="font-size: 0.78rem;">${(c.nse_symbol || c.id).toUpperCase()}</span>
                  <div>
                    <div style="font-size: 0.9rem; font-weight: 600; color: #fff;">${c.name}</div>
                    <div style="font-size: 0.72rem; color: var(--text-muted); font-family: var(--font-mono);">BSE: ${c.bse_code || '—'}</div>
                  </div>
                </div>
                <div>${flds || '<span style="font-size: 0.7rem; color: var(--text-muted);">General</span>'}</div>
              </div>
            `;
          }).join("");
        };

        currentRenderFn(currentItems);
      });
    }

    // 5. Stream Health Drilldown
    const cardHealth = document.getElementById("kpi-card-health");
    if (cardHealth) {
      cardHealth.addEventListener("click", async () => {
        openModalWithConfig("⚡", "Ingestion Stream Feeds", "Live status of all news sources, stock exchanges, and crawlers");
        try {
          const res = await fetch("/api/sources");
          const sources = await res.json();
          currentItems = sources;

          currentRenderFn = (items) => {
            countBadge.textContent = `${items.length} active feeds`;
            if (!items.length) {
              modalBody.innerHTML = `<div style="padding: 24px; text-align: center; color: var(--text-muted);">No feeds found.</div>`;
              return;
            }
            modalBody.innerHTML = items.map(s => {
              return `
                <div class="drilldown-item-card" style="flex-direction: row; justify-content: space-between; align-items: center;">
                  <div>
                    <div style="font-size: 0.9rem; font-weight: 700; color: #fff;">${s.name}</div>
                    <div style="font-size: 0.72rem; color: var(--text-muted); font-family: var(--font-mono); max-width: 480px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;">${s.url}</div>
                  </div>
                  <div style="text-align: right;">
                    <span class="status-badge-ok" style="font-size: 0.72rem;">● ${s.status || 'ACTIVE'}</span>
                    <div style="font-size: 0.72rem; color: var(--text-muted); margin-top: 3px;">${s.items_count || 0} items ingested</div>
                  </div>
                </div>
              `;
            }).join("");
          };

          currentRenderFn(currentItems);
        } catch (e) {
          modalBody.innerHTML = `<div style="color: var(--rose);">Failed to load stream feeds status.</div>`;
        }
      });
    }
  }

  // 12. Full System Settings & Infrastructure Controls
  async function loadFullSettings() {
    try {
      const res = await fetch("/api/settings/full");
      if (!res.ok) return;
      const data = await res.json();

      const toggleTestMode = document.getElementById("setting-toggle-testmode");
      const deliveryLabel = document.getElementById("settings-delivery-label");
      const testPhoneInput = document.getElementById("setting-test-phone");
      const interaktKeyInput = document.getElementById("setting-interakt-key");
      const interaktTemplateInput = document.getElementById("setting-interakt-template");
      const geminiKeyInput = document.getElementById("setting-gemini-key");
      const dbSizeEl = document.getElementById("settings-db-size");
      const dbRecordsEl = document.getElementById("settings-db-records");

      if (toggleTestMode) {
        toggleTestMode.checked = !!data.test_mode;
      }
      if (deliveryLabel) {
        deliveryLabel.textContent = data.test_mode ? "TEST MODE" : "LIVE PRODUCTION";
        deliveryLabel.className = data.test_mode ? "setting-status-pill warn" : "setting-status-pill ok";
      }
      if (testPhoneInput) {
        testPhoneInput.value = data.test_phone || "";
      }
      if (interaktKeyInput) {
        interaktKeyInput.value = data.interakt_key_masked || "";
      }
      if (interaktTemplateInput) {
        interaktTemplateInput.value = data.interakt_template || "vriddhi_daily_digest_49";
      }
      if (geminiKeyInput) {
        geminiKeyInput.value = data.gemini_key_masked || "";
      }
      if (dbSizeEl) {
        dbSizeEl.textContent = data.db_size_formatted || "2.4 MB";
      }
      if (dbRecordsEl && data.counts) {
        dbRecordsEl.textContent = `${data.counts.stories || 0} Stories • ${data.counts.companies || 0} Stocks`;
      }

      isTestDeliveryMode = !!data.test_mode;
      updateDeliveryModeUI(data.test_phone || "7900084773");
    } catch (err) {
      console.error("Settings fetch failed", err);
    }
  }

  // Toggle Delivery Mode switch in Settings
  const settingToggleTestMode = document.getElementById("setting-toggle-testmode");
  if (settingToggleTestMode) {
    settingToggleTestMode.addEventListener("change", async (e) => {
      const isChecked = e.target.checked;
      const deliveryLabel = document.getElementById("settings-delivery-label");
      if (deliveryLabel) {
        deliveryLabel.textContent = isChecked ? "TEST MODE" : "LIVE PRODUCTION";
        deliveryLabel.className = isChecked ? "setting-status-pill warn" : "setting-status-pill ok";
      }

      try {
        const res = await fetch("/api/settings/delivery-mode", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ test_mode: isChecked })
        });
        const data = await res.json();
        isTestDeliveryMode = !!data.test_mode;
        showToast(isTestDeliveryMode ? "🛡️ Safety Test Mode Active" : "🟢 Live Production Delivery Active!");
        loadDeliveryMode();
      } catch (err) {
        showToast("Error updating delivery mode", true);
      }
    });
  }

  // Save Settings Main Button
  const btnSaveSettingsMain = document.getElementById("btn-save-settings-main");
  if (btnSaveSettingsMain) {
    btnSaveSettingsMain.addEventListener("click", async () => {
      btnSaveSettingsMain.disabled = true;
      btnSaveSettingsMain.innerHTML = `<span class="btn-icon">⏳</span> Saving...`;

      const testMode = document.getElementById("setting-toggle-testmode")?.checked ?? true;
      const testPhone = document.getElementById("setting-test-phone")?.value.trim() ?? "";
      const interaktTemplate = document.getElementById("setting-interakt-template")?.value.trim() ?? "";

      try {
        const res = await fetch("/api/settings/save", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            test_mode: testMode,
            test_phone: testPhone,
            interakt_template: interaktTemplate,
          })
        });

        if (res.ok) {
          showToast("Settings updated & persistent to .env");
          loadFullSettings();
        } else {
          showToast("Failed to save settings", true);
        }
      } catch (err) {
        showToast("Network error saving settings", true);
      } finally {
        btnSaveSettingsMain.disabled = false;
        btnSaveSettingsMain.innerHTML = `<span class="btn-icon">✓</span> Save Changes`;
      }
    });
  }

  // Test WhatsApp Gateway
  const btnTestWhatsAppGateway = document.getElementById("btn-test-whatsapp-gateway");
  if (btnTestWhatsAppGateway) {
    btnTestWhatsAppGateway.addEventListener("click", async () => {
      btnTestWhatsAppGateway.disabled = true;
      btnTestWhatsAppGateway.innerHTML = `<span>⏳</span> Testing...`;
      showToast("Pinging Interakt WhatsApp Business Gateway...");

      try {
        const res = await fetch("/api/settings/test-whatsapp", { method: "POST" });
        const data = await res.json();
        if (data.status === "online") {
          showToast(`✓ ${data.message}`);
        } else {
          showToast(`WhatsApp Gateway: ${data.message}`, true);
        }
      } catch (err) {
        showToast("WhatsApp Gateway ping timeout", true);
      } finally {
        btnTestWhatsAppGateway.disabled = false;
        btnTestWhatsAppGateway.innerHTML = `⚡ Ping API`;
      }
    });
  }

  // Test Gemini AI Engine
  const btnTestGeminiApi = document.getElementById("btn-test-gemini-api");
  if (btnTestGeminiApi) {
    btnTestGeminiApi.addEventListener("click", async () => {
      btnTestGeminiApi.disabled = true;
      btnTestGeminiApi.innerHTML = `<span>⏳</span> Testing...`;
      showToast("Testing Google Gemini AI summarization engine...");

      try {
        const res = await fetch("/api/settings/test-ai", { method: "POST" });
        const data = await res.json();
        showToast(data.message, data.status !== "online");
      } catch (err) {
        showToast("AI test error or timeout", true);
      } finally {
        btnTestGeminiApi.disabled = false;
        btnTestGeminiApi.innerHTML = `⚡ Test AI`;
      }
    });
  }

  // Backup SQLite Database
  const triggerDbBackup = () => {
    showToast("Downloading binary snapshot of crawler.db...");
    triggerSilentDownload(`/api/settings/backup?t=${Date.now()}`);
  };
  const btnBackupSqlite = document.getElementById("btn-backup-sqlite");
  if (btnBackupSqlite) btnBackupSqlite.addEventListener("click", triggerDbBackup);
  const btnQuickBackupDb = document.getElementById("btn-quick-backup-db");
  if (btnQuickBackupDb) btnQuickBackupDb.addEventListener("click", triggerDbBackup);

  // Clean & Vacuum Database
  const triggerDbClean = async () => {
    if (!confirm("Vacuum SQLite database and prune legacy crawl runs?")) return;
    showToast("Vacuuming database and defragmenting disk pages...");
    try {
      const res = await fetch("/api/settings/clean-db", { method: "POST" });
      const data = await res.json();
      showToast(`✓ ${data.message || 'Database vacuumed successfully'}`);
      loadFullSettings();
    } catch (err) {
      showToast("Error vacuuming database", true);
    }
  };
  const btnCleanSqlite = document.getElementById("btn-clean-sqlite");
  if (btnCleanSqlite) btnCleanSqlite.addEventListener("click", triggerDbClean);
  const btnQuickCleanDb = document.getElementById("btn-quick-clean-db");
  if (btnQuickCleanDb) btnQuickCleanDb.addEventListener("click", triggerDbClean);

  // Credential Show/Hide Toggles
  const btnToggleInteraktKey = document.getElementById("btn-toggle-interakt-key");
  if (btnToggleInteraktKey) {
    btnToggleInteraktKey.addEventListener("click", () => {
      const inp = document.getElementById("setting-interakt-key");
      if (inp) {
        inp.type = inp.type === "password" ? "text" : "password";
      }
    });
  }
  const btnToggleGeminiKey = document.getElementById("btn-toggle-gemini-key");
  if (btnToggleGeminiKey) {
    btnToggleGeminiKey.addEventListener("click", () => {
      const inp = document.getElementById("setting-gemini-key");
      if (inp) {
        inp.type = inp.type === "password" ? "text" : "password";
      }
    });
  }

  // Initial Load
  async function initDashboard() {
    loadStats();
    loadDeliveryMode();
    await loadFolders();
    await loadWatchlist();
    await loadAnalysts();
    loadSources();
    loadLogs();
    loadFullSettings();
    initKpiDrilldowns();
  }
  initDashboard();
});
