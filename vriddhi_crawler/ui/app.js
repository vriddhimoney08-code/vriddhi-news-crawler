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

  // Full Digest Tab
  const digestViewAnalystSelect = document.getElementById("digest-view-analyst-select");
  const fullDigestIframe = document.getElementById("full-digest-iframe");
  const btnReloadDigestFrame = document.getElementById("btn-reload-digest-frame");

  // Watchlist & Folder Elements
  const watchlistTableBody = document.getElementById("watchlist-table-body");
  const watchlistFolderTabs = document.getElementById("watchlist-folder-tabs");
  const btnOpenAddStock = document.getElementById("btn-open-add-stock");
  const modalAddStock = document.getElementById("modal-add-stock");
  const btnCloseStockModal = document.getElementById("btn-close-stock-modal");
  const btnCancelStockModal = document.getElementById("btn-cancel-stock-modal");
  const formAddStock = document.getElementById("form-add-stock");
  const selectCompFolder = document.getElementById("select-comp-folder");
  const stockAnalystsCheckboxes = document.getElementById("stock-analysts-checkboxes");
  const stockFoldersCheckboxes = document.getElementById("stock-folders-checkboxes");

  const btnOpenAddFolder = document.getElementById("btn-open-add-folder");
  const modalAddFolder = document.getElementById("modal-add-folder");
  const btnCloseFolderModal = document.getElementById("btn-close-folder-modal");
  const btnCancelFolderModal = document.getElementById("btn-cancel-folder-modal");
  const formAddFolder = document.getElementById("form-add-folder");
  const inputFolderName = document.getElementById("input-folder-name");

  let currentWatchlistFolder = "ALL";
  let availableFolders = ["GAME", "SET", "MATCH"];

  // Analysts & Sources
  const analystsTableBody = document.getElementById("analysts-table-body");
  const sourcesListContainer = document.getElementById("sources-list-container");

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

  function renderAnalystsTable() {
    analystsTableBody.innerHTML = analystsList.map(a => {
      const folders = a.assigned_folders || [];
      const stockCount = getAnalystCoveredStockCount(a);
      const foldersDisplay = folders.length > 0
        ? folders.map(f => {
            let cls = "folder-tag-custom";
            if (f === "GAME") cls = "folder-tag-game";
            else if (f === "SET") cls = "folder-tag-set";
            else if (f === "MATCH") cls = "folder-tag-match";
            return `<span class="folder-tag ${cls}">${f}</span>`;
          }).join(" ")
        : '<span style="color:var(--text-dim);font-style:italic;">None (No Baskets)</span>';

      return `
      <tr>
        <td><strong>${a.name}</strong></td>
        <td><code>+91 ${a.phone}</code></td>
        <td>${a.email || '—'}</td>
        <td>${foldersDisplay} <span style="font-size:0.75rem; color:var(--text-dim); margin-left:6px; font-weight:600;">(${stockCount} Stocks)</span></td>
        <td><span class="status-badge-ok">8:00 AM QUEUED</span></td>
        <td>
          <button class="btn-edit-action" onclick="editAnalyst('${a.id}')">Edit</button>
          <button class="btn-cancel" style="padding: 3px 8px; font-size: 0.72rem;" onclick="deleteAnalyst('${a.id}')">Delete</button>
        </td>
      </tr>
      `;
    }).join("");
  }

  window.editAnalyst = (id) => {
    const a = analystsList.find(x => x.id === id);
    if (!a) return;
    document.getElementById("analyst-modal-title").textContent = `Edit Analyst: ${a.name}`;
    document.getElementById("input-analyst-id").value = a.id;
    document.getElementById("input-analyst-name").value = a.name;
    document.getElementById("input-analyst-phone").value = a.phone;
    document.getElementById("input-analyst-email").value = a.email || "";
    renderAnalystFoldersCheckboxes(a.assigned_folders || []);
    modalAddAnalyst.classList.add("open");
  };

  window.deleteAnalyst = async (id) => {
    if (!confirm("Are you sure you want to remove this analyst?")) return;
    try {
      const res = await fetch(`/api/analysts/${id}`, { method: "DELETE" });
      if (res.ok) {
        showToast("Analyst removed.");
        await loadAnalysts();
        loadStats();
      }
    } catch(err) {
      showToast("Error deleting analyst", true);
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
    document.getElementById("analyst-modal-title").textContent = "Add New Analyst";
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

    const payload = {
      id: id || name.toLowerCase().replace(/[^a-z0-9]/g, "").slice(0, 16),
      name,
      phone,
      email,
      assigned_companies: [],
      assigned_folders: assignedFolders
    };

    try {
      const res = await fetch("/api/analysts", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload)
      });
      if (res.ok) {
        showToast(`Saved analyst: ${name}!`);
        modalAddAnalyst.classList.remove("open");
        formAddAnalyst.reset();
        await loadAnalysts();
        loadStats();
      }
    } catch(err) {
      showToast("Failed to save analyst", true);
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

  // 8. Full Digest Iframe
  function loadFullDigestFrame() {
    digestViewAnalystSelect.value = currentAnalystId;
    fullDigestIframe.src = `/api/digest/preview/${currentAnalystId}?t=${Date.now()}`;
  }
  btnReloadDigestFrame.addEventListener("click", loadFullDigestFrame);

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

  function renderWatchlistTable() {
    if (!watchlistTableBody) return;

    const filtered = currentWatchlistFolder === "ALL"
      ? companiesList
      : companiesList.filter(c => getCompanyFolders(c).includes(currentWatchlistFolder.toUpperCase()));

    if (filtered.length === 0) {
      watchlistTableBody.innerHTML = `
        <tr>
          <td colspan="8" style="text-align: center; padding: 28px; color: var(--text-dim); font-style: italic;">
            No stocks currently in <strong>${currentWatchlistFolder}</strong> basket. Click "+ Add New Stock" or assign a stock using the + Basket button!
          </td>
        </tr>
      `;
      return;
    }

    watchlistTableBody.innerHTML = filtered.map(c => {
      const cFolders = getCompanyFolders(c);

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
        .map(a => `<span class="analyst-pill">👤 ${a.name}</span>`);
      
      const assignedDisplay = assigned.length > 0
        ? assigned.join(" ")
        : `<span class="badge-unassigned">Unassigned</span>`;

      return `
        <tr>
          <td><strong style="color:#f8fafc; font-weight:600;">${c.name}</strong></td>
          <td>${c.nse_symbol ? `<span class="code-pill">${c.nse_symbol}</span>` : '<span class="empty-cell-dash">—</span>'}</td>
          <td>${c.bse_code ? `<span class="code-pill" style="opacity:0.8;">${c.bse_code}</span>` : '<span class="empty-cell-dash">—</span>'}</td>
          <td>${folderCellHtml}</td>
          <td>${(c.aliases || []).length > 0 ? `<span style="font-size:0.75rem; color:var(--text-dim);">${c.aliases.slice(0, 2).join(", ")}</span>` : '<span class="empty-cell-dash">—</span>'}</td>
          <td>${assignedDisplay}</td>
          <td><span class="status-pill-active"><span class="pulse-dot"></span>ACTIVE</span></td>
          <td>
            <button class="btn-table-del" onclick="deleteStock('${c.id}')">Delete</button>
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
      bse_code: bse,
      aliases,
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

  // 11. Sources Feeds
  async function loadSources() {
    try {
      const res = await fetch("/api/sources");
      const sources = await res.json();
      sourcesListContainer.innerHTML = sources.map(s => `
        <div class="source-item-card">
          <div style="display: flex; justify-content: space-between; align-items: center;">
            <strong>${s.name}</strong>
            <span class="status-badge-ok">ACTIVE</span>
          </div>
          <code style="font-size: 0.72rem; color: var(--text-dim);">${s.url}</code>
          <div style="font-size: 0.75rem; color: var(--text-muted); display: flex; justify-content: space-between; margin-top: 4px;">
            <span>TYPE: ${s.type.toUpperCase()}</span>
            <span>BODY CHECK: ${s.body_check ? 'YES' : 'NO'}</span>
          </div>
        </div>
      `).join("");
    } catch (err) {
      console.error("Sources fetch error", err);
    }
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

  // Initial Load
  async function initDashboard() {
    loadStats();
    loadDeliveryMode();
    await loadFolders();
    await loadWatchlist();
    await loadAnalysts();
    loadSources();
    loadLogs();
  }
  initDashboard();
});
