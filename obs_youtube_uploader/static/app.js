const listEl = document.getElementById("videos");
const statsEl = document.getElementById("stats");
const refreshBtn = document.getElementById("refresh");
const searchInput = document.getElementById("search");
const statusFiltersEl = document.getElementById("status-filters");
const detailPanelEl = document.getElementById("detail-panel");
const youtubePanelEl = document.getElementById("youtube-panel");
const flashEl = document.getElementById("flash");

let videos = [];
let selectedId = null;
let currentFilter = "all";
let youtubeStatus = null;
let flashTimer = null;

const statusLabels = {
  pending: "Pending",
  uploading: "Uploading",
  uploaded: "Uploaded",
  error: "Error",
  skipped: "Skipped",
  all: "All",
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

const updateStats = () => {
  const counts = videos.reduce(
    (acc, item) => {
      acc[item.status] = (acc[item.status] || 0) + 1;
      return acc;
    },
    { pending: 0, uploading: 0, uploaded: 0, error: 0, skipped: 0 }
  );

  statsEl.innerHTML = "";
  ["pending", "uploading", "error", "uploaded", "skipped"].forEach((status) => {
    const div = document.createElement("div");
    div.className = "stat";
    div.innerHTML = `<strong>${counts[status] || 0}</strong><span>${statusLabels[status]}</span>`;
    statsEl.appendChild(div);
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

const renderTable = () => {
  const rows = filteredVideos();
  listEl.innerHTML = "";

  if (!rows.length) {
    const tr = document.createElement("tr");
    tr.innerHTML = `<td colspan="7"><div class="empty-state small">No matching videos right now.</div></td>`;
    listEl.appendChild(tr);
    return;
  }

  rows.forEach((video) => {
    const tr = document.createElement("tr");
    tr.className = selectedId === video.id ? "selected" : "";
    tr.innerHTML = `
      <td><span class="status ${video.status}">${statusLabels[video.status] || video.status}</span></td>
      <td class="mono">${video.sequence ?? "-"}</td>
      <td>
        <div class="primary-cell">${video.filename || "-"}</div>
        <div class="secondary-cell mono">${video.video_path}</div>
      </td>
      <td>${video.title || "-"}</td>
      <td class="mono">${video.match_id ?? "-"}</td>
      <td>${formatDate(video.updated_at)}</td>
      <td>
        <div class="row-actions">
          <button class="btn subtle btn-xs" data-action="review">Review</button>
          <button class="btn btn-xs" data-action="upload" ${["uploading", "uploaded", "skipped"].includes(video.status) ? "disabled" : ""}>Upload</button>
          <button class="btn ghost btn-xs" data-action="skip" ${["uploaded", "skipped"].includes(video.status) ? "disabled" : ""}>Skip</button>
        </div>
      </td>
    `;

    tr.addEventListener("click", (event) => {
      if (event.target.closest("button")) return;
      selectedId = video.id;
      render();
    });

    tr.querySelector('[data-action="review"]').onclick = () => {
      selectedId = video.id;
      render();
    };

    tr.querySelector('[data-action="upload"]').onclick = async () => {
      await post(`/api/videos/${video.id}/upload`);
      showFlash(`Upload started for ${video.filename}`);
    };

    tr.querySelector('[data-action="skip"]').onclick = async () => {
      await post(`/api/videos/${video.id}/skip`);
      showFlash(`Skipped ${video.filename}`);
      await fetchVideos();
    };

    listEl.appendChild(tr);
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
    detailPanelEl.innerHTML = '<div class="empty-state">Select a video to review and edit.</div>';
    return;
  }

  detailPanelEl.innerHTML = "";

  const top = document.createElement("div");
  top.className = "detail-top";
  top.innerHTML = `
    <div>
      <div class="section-title">Review Video</div>
      <div class="detail-title">${video.filename}</div>
      <div class="meta-row mono">
        <span>ID ${video.id}</span>
        <span>Match ${video.match_id ?? "-"}</span>
        <span>${formatDate(video.updated_at)}</span>
      </div>
    </div>
    <span class="status ${video.status}">${statusLabels[video.status] || video.status}</span>
  `;

  const form = document.createElement("div");
  form.className = "detail-form";

  const titleField = createField("Title", "input");
  titleField.control.value = video.title || "";

  const seqField = createField("Sequence", "input");
  seqField.control.type = "number";
  seqField.control.min = "1";
  seqField.control.value = video.sequence ?? "";

  const tagsField = createField("Tags", "input");
  tagsField.control.value = video.tags || "";

  const descField = createField("Description", "textarea");
  descField.control.value = video.description || "";

  const promptField = createField("Thumbnail Prompt", "textarea");
  promptField.control.value = video.thumbnail_prompt || "";
  promptField.control.readOnly = true;

  seqField.control.addEventListener("input", () => {
    const seqValue = Number(seqField.control.value);
    if (!Number.isNaN(seqValue) && seqValue > 0) {
      titleField.control.value = applySequenceToTitle(titleField.control.value, seqValue);
    }
  });

  [titleField.field, seqField.field, tagsField.field, descField.field, promptField.field].forEach((el) => form.appendChild(el));

  const actions = document.createElement("div");
  actions.className = "actions";
  actions.innerHTML = `
    <button class="btn subtle">Save</button>
    <button class="btn" ${["uploading", "uploaded", "skipped"].includes(video.status) ? "disabled" : ""}>Upload</button>
    <button class="btn ghost" ${["uploaded", "skipped"].includes(video.status) ? "disabled" : ""}>Skip</button>
    <button class="btn ghost">Copy Prompt</button>
  `;

  const [saveBtn, uploadBtn, skipBtn, copyBtn] = actions.querySelectorAll("button");

  saveBtn.onclick = async () => {
    await patchVideo(video.id, {
      title: titleField.control.value,
      description: descField.control.value,
      tags: tagsField.control.value,
      sequence: Number(seqField.control.value) || null,
    });
    showFlash(`Saved changes for ${video.filename}`);
    await fetchVideos();
  };

  uploadBtn.onclick = async () => {
    await post(`/api/videos/${video.id}/upload`);
    showFlash(`Upload started for ${video.filename}`);
  };

  skipBtn.onclick = async () => {
    await post(`/api/videos/${video.id}/skip`);
    showFlash(`Skipped ${video.filename}`);
    await fetchVideos();
  };

  copyBtn.onclick = async () => {
    if (navigator.clipboard && promptField.control.value) {
      await navigator.clipboard.writeText(promptField.control.value);
      showFlash("Thumbnail prompt copied");
    }
  };

  detailPanelEl.appendChild(top);
  detailPanelEl.appendChild(form);
  detailPanelEl.appendChild(actions);

  if (video.youtube_url) {
    const youtubeLink = document.createElement("a");
    youtubeLink.className = "youtube-link";
    youtubeLink.href = video.youtube_url;
    youtubeLink.target = "_blank";
    youtubeLink.rel = "noreferrer";
    youtubeLink.textContent = `Open YouTube video → ${video.youtube_video_id}`;
    detailPanelEl.appendChild(youtubeLink);
  }

  if (video.error) {
    const errorBox = document.createElement("div");
    errorBox.className = "error-box";
    errorBox.textContent = video.error;
    detailPanelEl.appendChild(errorBox);
  }
};

const renderYoutubePanel = () => {
  youtubePanelEl.innerHTML = "";
  const status = youtubeStatus || { connected: false, token_status: "missing" };
  const wrap = document.createElement("div");
  wrap.innerHTML = `
    <div class="section-title">YouTube Connection</div>
    <div class="youtube-status-row">
      <div>
        <div class="detail-title">${status.connected ? (status.channel_title || "Connected") : "Not connected"}</div>
        <div class="muted-line">
          ${status.google_account_email || "Connect your channel in the browser so uploads can refresh automatically."}
        </div>
        <div class="meta-row mono compact">
          <span>Source: ${status.source || "none"}</span>
          <span>Status: ${status.token_status || "missing"}</span>
          <span>${status.last_refreshed_at ? `Last refresh ${formatDate(status.last_refreshed_at)}` : "No refresh yet"}</span>
        </div>
      </div>
      <span class="status ${status.connected ? "uploaded" : "skipped"}">${status.connected ? "Connected" : "Missing"}</span>
    </div>
  `;

  const actions = document.createElement("div");
  actions.className = "actions";

  const connectBtn = document.createElement("button");
  connectBtn.className = "btn";
  connectBtn.textContent = status.connected ? "Reconnect YouTube" : "Connect YouTube";
  connectBtn.onclick = async () => {
    const res = await post("/api/youtube/connect/start", { redirect_path: "/" });
    if (res.auth_url) window.location.href = res.auth_url;
  };

  const testBtn = document.createElement("button");
  testBtn.className = "btn subtle";
  testBtn.textContent = "Test Refresh";
  testBtn.onclick = async () => {
    const res = await post("/api/youtube/refresh-test");
    showFlash(`Connected to ${res.channel_title || res.google_account_email || res.source}`);
    await fetchYoutubeStatus();
  };

  actions.appendChild(connectBtn);

  if (status.connected) {
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

  wrap.appendChild(actions);

  if (status.error) {
    const errorBox = document.createElement("div");
    errorBox.className = "error-box";
    errorBox.textContent = status.error;
    wrap.appendChild(errorBox);
  }

  youtubePanelEl.appendChild(wrap);
};

const render = () => {
  updateStats();
  renderStatusFilters();
  renderYoutubePanel();

  const rows = filteredVideos();
  if (!selectedVideo() && rows.length) {
    selectedId = rows[0].id;
  }

  renderTable();
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

const handleQueryFeedback = () => {
  const params = new URLSearchParams(window.location.search);
  const youtube = params.get("youtube");
  const message = params.get("message");
  if (youtube === "connected") showFlash("YouTube connected successfully.");
  if (youtube === "error") showFlash(message || "YouTube connection failed.", true);
  if (youtube) {
    const cleanUrl = `${window.location.pathname}`;
    window.history.replaceState({}, "", cleanUrl);
  }
};

refreshBtn.addEventListener("click", async () => {
  await Promise.all([fetchVideos(), fetchYoutubeStatus()]);
  showFlash("Dashboard refreshed");
});
searchInput.addEventListener("input", renderTable);
searchInput.addEventListener("input", renderDetail);

Promise.all([fetchVideos(), fetchYoutubeStatus()]).then(handleQueryFeedback);
initEvents();
