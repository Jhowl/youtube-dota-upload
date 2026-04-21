const listEl = document.getElementById("videos");
const statsEl = document.getElementById("stats");
const refreshBtn = document.getElementById("refresh");
const searchInput = document.getElementById("search");
const statusFiltersEl = document.getElementById("status-filters");
const detailPanelEl = document.getElementById("detail-panel");
const youtubePanelEl = document.getElementById("youtube-panel");
const flashEl = document.getElementById("flash");
const youtubeNavBtn = document.getElementById("youtube-nav-btn");
const tableCountEl = document.getElementById("table-count");

const summaryEls = {
  pending: document.getElementById("summary-pending"),
  uploading: document.getElementById("summary-uploading"),
  error: document.getElementById("summary-error"),
  uploaded: document.getElementById("summary-uploaded"),
};

let videos = [];
let selectedId = null;
let currentFilter = "all";
let youtubeStatus = null;
let flashTimer = null;
let detailCache = new Map();

const statusLabels = {
  all: "All",
  pending: "Pending",
  uploading: "Uploading",
  uploaded: "Uploaded",
  error: "Error",
  skipped: "Skipped",
};

const statusOrder = ["all", "pending", "uploading", "error", "uploaded", "skipped"];

const applySequenceToTitle = (title, seq) => {
  const cleaned = title.replace(/\s+#\d+\s*(?:🧙‍♂️)?\s*$/, "").trim();
  return `${cleaned} #${seq} 🧙‍♂️`.trim();
};

const showFlash = (message, isError = false) => {
  flashEl.textContent = message || "";
  flashEl.className = `hint${isError ? " error-text" : ""}`;
  if (flashTimer) clearTimeout(flashTimer);
  if (message) {
    flashTimer = setTimeout(() => {
      flashEl.textContent = "";
      flashEl.className = "hint";
    }, 5000);
  }
};

const formatDate = (value) => {
  if (!value) return "-";
  const d = new Date(value);
  if (Number.isNaN(d.getTime())) return value;
  return d.toLocaleString();
};

const getCounts = () =>
  videos.reduce(
    (acc, item) => {
      acc[item.status] = (acc[item.status] || 0) + 1;
      return acc;
    },
    { pending: 0, uploading: 0, uploaded: 0, error: 0, skipped: 0 }
  );

const selectedVideo = () => videos.find((video) => video.id === selectedId) || null;

const filteredVideos = () => {
  const query = (searchInput.value || "").trim().toLowerCase();
  return videos.filter((video) => {
    if (currentFilter !== "all" && video.status !== currentFilter) return false;
    if (!query) return true;
    const haystack = [video.filename, video.title, video.video_path, video.match_id]
      .filter(Boolean)
      .join(" ")
      .toLowerCase();
    return haystack.includes(query);
  });
};

const renderStats = () => {
  const counts = getCounts();
  statsEl.innerHTML = "";
  ["pending", "uploading", "error", "uploaded", "skipped"].forEach((status) => {
    const tile = document.createElement("div");
    tile.className = "stat-tile";
    tile.innerHTML = `<span>${statusLabels[status]}</span><strong>${counts[status] || 0}</strong>`;
    statsEl.appendChild(tile);
  });
  Object.entries(summaryEls).forEach(([status, el]) => {
    if (el) el.textContent = String(counts[status] || 0);
  });
};

const renderStatusFilters = () => {
  statusFiltersEl.innerHTML = "";
  statusOrder.forEach((status) => {
    const btn = document.createElement("button");
    btn.className = `pill ${currentFilter === status ? "active" : ""}`;
    btn.textContent = statusLabels[status];
    btn.onclick = () => {
      currentFilter = status;
      render();
    };
    statusFiltersEl.appendChild(btn);
  });
};

const fetchVideoDetail = async (id) => {
  if (detailCache.has(id)) return detailCache.get(id);
  const res = await fetch(`/api/videos/${id}`);
  const data = await res.json();
  detailCache.set(id, data);
  return data;
};

const invalidateDetail = (id) => {
  if (id) detailCache.delete(id);
};

const renderList = () => {
  const rows = filteredVideos();
  listEl.innerHTML = "";
  tableCountEl.textContent = `${rows.length} video${rows.length === 1 ? "" : "s"}`;

  if (!rows.length) {
    listEl.innerHTML = '<div class="empty-state">No matching videos right now.</div>';
    return;
  }

  rows.forEach((video) => {
    const row = document.createElement("div");
    row.className = `video-row ${selectedId === video.id ? "selected" : ""}`;
    row.innerHTML = `
      <div class="video-stack">
        <span class="status ${video.status}">${statusLabels[video.status] || video.status}</span>
        <div class="video-stack-meta">
          <div class="video-seq">#${video.sequence ?? "-"}</div>
          <div class="video-match">Match ${video.match_id ?? "-"}</div>
        </div>
      </div>
      <div class="video-main">
        <div class="video-row-title">${video.filename || "Unnamed video"}</div>
        <div class="video-row-sub">${video.title || "No title yet"}</div>
        <div class="video-row-sub">${video.video_path || ""}</div>
      </div>
      <div>
        <div class="row-actions">
          <button class="btn subtle btn-xs" data-action="review">Review</button>
          <button class="btn btn-xs" data-action="upload" ${["uploading", "uploaded", "skipped"].includes(video.status) ? "disabled" : ""}>Upload</button>
          <button class="btn ghost btn-xs" data-action="skip" ${["uploaded", "skipped"].includes(video.status) ? "disabled" : ""}>Skip</button>
        </div>
      </div>
    `;

    row.addEventListener("click", async (event) => {
      if (event.target.closest("button")) return;
      selectedId = video.id;
      render();
    });

    row.querySelector('[data-action="review"]').onclick = async () => {
      selectedId = video.id;
      render();
    };

    row.querySelector('[data-action="upload"]').onclick = async () => {
      await post(`/api/videos/${video.id}/upload`);
      showFlash(`Upload started for ${video.filename}`);
    };

    row.querySelector('[data-action="skip"]').onclick = async () => {
      await post(`/api/videos/${video.id}/skip`);
      invalidateDetail(video.id);
      showFlash(`Skipped ${video.filename}`);
      await fetchVideos();
    };

    listEl.appendChild(row);
  });
};

const createField = (labelText, type) => {
  const field = document.createElement("div");
  field.className = "field";
  const label = document.createElement("label");
  label.textContent = labelText;
  const control = document.createElement(type);
  field.appendChild(label);
  field.appendChild(control);
  return { field, control };
};

const renderDetail = () => {
  const video = selectedVideo();
  if (!video) {
    detailPanelEl.innerHTML = '<div class="empty-state">Select a video from the list to manage it.</div>';
    return;
  }

  detailPanelEl.scrollTop = 0;
  detailPanelEl.innerHTML = "";

  const top = document.createElement("div");
  top.className = "detail-top";
  top.innerHTML = `
    <div>
      <div class="eyebrow">Focused Editor</div>
      <div class="detail-title">${video.filename}</div>
      <div class="meta-row mono">
        <span>ID ${video.id}</span>
        <span>Match ${video.match_id ?? "-"}</span>
        <span>Updated ${formatDate(video.updated_at)}</span>
      </div>
    </div>
    <span class="status ${video.status}">${statusLabels[video.status] || video.status}</span>
  `;

  const layout = document.createElement("div");
  layout.className = "editor-layout";

  const form = document.createElement("div");
  form.className = "detail-form";

  const titleField = createField("Title", "input");
  titleField.control.value = video.title || "";

  const seqField = createField("Sequence", "input");
  seqField.control.type = "number";
  seqField.control.min = "1";
  seqField.control.value = video.sequence ?? "";

  const matchField = createField("Match ID", "input");
  matchField.control.type = "number";
  matchField.control.min = "1";
  matchField.control.value = video.match_id ?? "";

  const tagsField = createField("Tags", "input");
  tagsField.control.value = video.tags || "";

  const descField = createField("Description", "textarea");
  descField.control.value = video.description || "";

  seqField.control.addEventListener("input", () => {
    const seqValue = Number(seqField.control.value);
    if (!Number.isNaN(seqValue) && seqValue > 0) {
      titleField.control.value = applySequenceToTitle(titleField.control.value, seqValue);
    }
  });

  [titleField.field, seqField.field, matchField.field, tagsField.field, descField.field].forEach((el) => form.appendChild(el));

  const actions = document.createElement("div");
  actions.className = "actions sticky-toolbar";
  actions.innerHTML = `
    <button class="btn subtle">Save Changes</button>
    <button class="btn" ${["uploading", "uploaded", "skipped"].includes(video.status) ? "disabled" : ""}>Upload Video</button>
    <button class="btn ghost" ${["uploaded", "skipped"].includes(video.status) ? "disabled" : ""}>Skip</button>
    <button class="btn danger">Delete</button>
    <button class="btn ghost">Recalculate Numbers</button>
  `;

  const [saveBtn, uploadBtn, skipBtn, deleteBtn, reseqBtn] = actions.querySelectorAll("button");

  saveBtn.onclick = async () => {
    await patchVideo(video.id, {
      title: titleField.control.value,
      description: descField.control.value,
      tags: tagsField.control.value,
      sequence: Number(seqField.control.value) || null,
      match_id: Number(matchField.control.value) || null,
    });
    invalidateDetail(video.id);
    showFlash(`Saved changes for ${video.filename}`);
    await fetchVideos();
  };

  uploadBtn.onclick = async () => {
    await post(`/api/videos/${video.id}/upload`);
    showFlash(`Upload started for ${video.filename}`);
  };

  skipBtn.onclick = async () => {
    await post(`/api/videos/${video.id}/skip`);
    invalidateDetail(video.id);
    showFlash(`Skipped ${video.filename}`);
    await fetchVideos();
  };

  deleteBtn.onclick = async () => {
    await fetch(`/api/videos/${video.id}`, { method: "DELETE" });
    invalidateDetail(video.id);
    selectedId = null;
    showFlash(`Deleted record for ${video.filename}`);
    await fetchVideos();
  };

  reseqBtn.onclick = async () => {
    await post('/api/videos/resequence');
    detailCache.clear();
    showFlash('Recalculated video sequence numbers');
    await fetchVideos();
  };

  form.appendChild(actions);

  const side = document.createElement('div');
  side.className = 'side-panels';

  const promptPanel = document.createElement('div');
  promptPanel.className = 'info-panel';
  promptPanel.innerHTML = `<div class="section-subtitle">Thumbnail Prompt</div><div class="section-helper">Copy and use this for thumbnail generation.</div>`;
  const promptBox = document.createElement('div');
  promptBox.className = 'raw-box';
  promptBox.textContent = video.thumbnail_prompt || 'No prompt available';
  const copyPromptBtn = document.createElement('button');
  copyPromptBtn.className = 'btn ghost';
  copyPromptBtn.textContent = 'Copy Prompt';
  copyPromptBtn.onclick = async () => {
    if (navigator.clipboard && video.thumbnail_prompt) {
      await navigator.clipboard.writeText(video.thumbnail_prompt);
      showFlash('Thumbnail prompt copied');
    }
  };
  promptPanel.appendChild(promptBox);
  promptPanel.appendChild(copyPromptBtn);

  const rawPanel = document.createElement('div');
  rawPanel.className = 'info-panel';
  rawPanel.innerHTML = `<div class="section-subtitle">OpenDota Raw Data</div><div class="section-helper">Raw match payload for debugging and metadata checks.</div>`;
  const rawBox = document.createElement('div');
  rawBox.className = 'raw-box';
  rawBox.textContent = 'Loading raw match data…';
  rawPanel.appendChild(rawBox);

  side.appendChild(promptPanel);
  side.appendChild(rawPanel);

  layout.appendChild(form);
  layout.appendChild(side);

  detailPanelEl.appendChild(top);
  detailPanelEl.appendChild(layout);

  if (video.youtube_url) {
    const youtubeLink = document.createElement("a");
    youtubeLink.className = "youtube-link";
    youtubeLink.href = video.youtube_url;
    youtubeLink.target = "_blank";
    youtubeLink.rel = "noreferrer";
    youtubeLink.textContent = `Open uploaded YouTube video → ${video.youtube_video_id}`;
    detailPanelEl.appendChild(youtubeLink);
  }

  if (video.error) {
    const errorBox = document.createElement("div");
    errorBox.className = "error-box";
    errorBox.textContent = video.error;
    detailPanelEl.appendChild(errorBox);
  }

  fetchVideoDetail(video.id)
    .then((detail) => {
      if (selectedId !== video.id) return;
      rawBox.textContent = detail.opendota_match_raw
        ? JSON.stringify(detail.opendota_match_raw, null, 2)
        : (detail.opendota_match_raw_error || 'No raw OpenDota data available');
    })
    .catch((err) => {
      if (selectedId !== video.id) return;
      rawBox.textContent = `Failed to load raw data: ${err.message || err}`;
    });
};

const renderYoutubePanel = () => {
  youtubePanelEl.innerHTML = "";
  const status = youtubeStatus || { connected: false, token_status: "missing" };

  youtubePanelEl.innerHTML = `
    <div class="sidebar-title">YouTube</div>
    <div class="detail-title">${status.connected ? (status.channel_title || "Connected") : "Not connected"}</div>
    <div class="youtube-subtext">${status.google_account_email || "Generate the Google login link here, approve it, then paste the authorization code below."}</div>
    <div class="meta-row mono">
      <span>Source: ${status.source || "none"}</span>
      <span>Status: ${status.token_status || "missing"}</span>
    </div>
  `;

  const actions = document.createElement("div");
  actions.className = "actions";

  const connectBtn = document.createElement("button");
  connectBtn.className = "btn";
  connectBtn.textContent = status.connected ? "Generate New Login Link" : "Generate Login Link";
  connectBtn.onclick = async () => {
    const res = await post("/api/youtube/login-link");
    if (res.auth_url) {
      window.open(res.auth_url, "_blank", "noopener,noreferrer");
      showFlash("Opened Google login page. After approval, paste the returned code below.");
    }
  };
  actions.appendChild(connectBtn);

  const legacyWrap = document.createElement("div");
  legacyWrap.className = "field";
  const legacyLabel = document.createElement("label");
  legacyLabel.textContent = "Paste authorization code";
  const legacyInput = document.createElement("textarea");
  legacyInput.placeholder = "Paste the Google authorization code here";
  legacyInput.style.minHeight = "90px";
  const legacySubmit = document.createElement("button");
  legacySubmit.className = "btn subtle";
  legacySubmit.textContent = "Save Login";
  legacySubmit.onclick = async () => {
    const code = legacyInput.value.trim();
    if (!code) {
      showFlash("Paste the authorization code first.", true);
      return;
    }
    const res = await post("/api/youtube/login-complete", { code });
    showFlash(`YouTube connected: ${res.channel_title || res.google_account_email || "ok"}`);
    legacyInput.value = "";
    await fetchYoutubeStatus();
  };
  legacyWrap.appendChild(legacyLabel);
  legacyWrap.appendChild(legacyInput);
  youtubePanelEl.appendChild(actions);
  youtubePanelEl.appendChild(legacyWrap);
  youtubePanelEl.appendChild(legacySubmit);

  if (status.connected) {
    const testBtn = document.createElement("button");
    testBtn.className = "btn subtle";
    testBtn.textContent = "Test Connection";
    testBtn.onclick = async () => {
      const res = await post("/api/youtube/refresh-test");
      showFlash(`Connected to ${res.channel_title || res.google_account_email || res.source}`);
      await fetchYoutubeStatus();
    };
    actions.appendChild(testBtn);

    const disconnectBtn = document.createElement("button");
    disconnectBtn.className = "btn ghost";
    disconnectBtn.textContent = "Disconnect";
    disconnectBtn.onclick = async () => {
      await post("/api/youtube/disconnect");
      showFlash("Disconnected stored YouTube account");
      await fetchYoutubeStatus();
    };
    actions.appendChild(disconnectBtn);
  }

  if (status.error) {
    const errorBox = document.createElement("div");
    errorBox.className = "error-box";
    errorBox.textContent = status.error;
    youtubePanelEl.appendChild(errorBox);
  }
};

const render = () => {
  renderStats();
  renderStatusFilters();
  renderYoutubePanel();

  const rows = filteredVideos();
  if (!selectedVideo() && rows.length) {
    selectedId = rows[0].id;
  }

  renderList();
  renderDetail();
};

const fetchVideos = async () => {
  const res = await fetch("/api/videos");
  const data = await res.json();
  videos = data.items || [];
  render();
};

const fetchYoutubeStatus = async () => {
  const res = await fetch("/api/youtube/status");
  youtubeStatus = await res.json();
  renderYoutubePanel();
};

const patchVideo = async (id, payload) => {
  const body = { ...payload };
  if (!body.sequence) delete body.sequence;
  await fetch(`/api/videos/${id}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
};

const post = async (url, body) => {
  const res = await fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: body ? JSON.stringify(body) : undefined,
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) {
    const message = data.detail || `Request failed: ${res.status}`;
    showFlash(message, true);
    throw new Error(message);
  }
  return data;
};

const initEvents = () => {
  const source = new EventSource("/api/events");
  source.onmessage = () => fetchVideos();
  source.onerror = () => {
    source.close();
    setTimeout(initEvents, 5000);
  };
};

refreshBtn.addEventListener("click", async () => {
  detailCache.clear();
  await Promise.all([fetchVideos(), fetchYoutubeStatus()]);
  showFlash("Dashboard refreshed");
});

searchInput.addEventListener("input", render);

youtubeNavBtn?.addEventListener("click", () => {
  youtubePanelEl.scrollIntoView({ behavior: "smooth", block: "start" });
});

Promise.all([fetchVideos(), fetchYoutubeStatus()]);
initEvents();
