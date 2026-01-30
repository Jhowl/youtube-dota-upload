const listEl = document.getElementById("videos");
const statsEl = document.getElementById("stats");
const refreshBtn = document.getElementById("refresh");

let videos = [];

const statusLabels = {
  pending: "Pending",
  uploading: "Uploading",
  uploaded: "Uploaded",
  error: "Error",
  skipped: "Skipped",
};

const statusOrder = ["pending", "uploading", "error", "uploaded", "skipped"];

const applySequenceToTitle = (title, seq) => {
  const cleaned = title.replace(/\s+#\d+\s*$/, "").trim();
  return `${cleaned} #${seq}`.trim();
};

const fetchVideos = async () => {
  const res = await fetch("/api/videos");
  const data = await res.json();
  videos = data.items || [];
  render();
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
  statusOrder.forEach((status) => {
    const div = document.createElement("div");
    div.className = "stat";
    div.innerHTML = `<strong>${counts[status] || 0}</strong><span>${statusLabels[status]}</span>`;
    statsEl.appendChild(div);
  });
};

const render = () => {
  updateStats();
  listEl.innerHTML = "";
  if (!videos.length) {
    const empty = document.createElement("div");
    empty.className = "card";
    empty.innerHTML = "<p>No videos queued yet. Drop a file into the watch folder.</p>";
    listEl.appendChild(empty);
    return;
  }

  videos.forEach((video) => {
    listEl.appendChild(renderCard(video));
  });
};

const renderCard = (video) => {
  const card = document.createElement("div");
  card.className = "card";

  const statusText = statusLabels[video.status] || video.status;

  const header = document.createElement("div");
  header.className = "card-header";
  header.innerHTML = `
    <div>
      <div class="path">${video.video_path}</div>
      <div class="meta">
        <span>ID: ${video.id}</span>
        <span>Seq: ${video.sequence ?? "-"}</span>
        <span>Match: ${video.match_id ?? "-"}</span>
      </div>
    </div>
    <div class="status ${video.status}">${statusText}</div>
  `;

  const grid = document.createElement("div");
  grid.className = "grid";

  const titleField = createField("Title", "input");
  const titleInput = titleField.querySelector("input");
  titleInput.value = video.title || "";

  const seqField = createField("Sequence", "input");
  const seqInput = seqField.querySelector("input");
  seqInput.type = "number";
  seqInput.min = "1";
  seqInput.value = video.sequence ?? "";

  const tagsField = createField("Tags (comma separated)", "input");
  const tagsInput = tagsField.querySelector("input");
  tagsInput.value = video.tags || "";

  const descField = createField("Description", "textarea");
  const descInput = descField.querySelector("textarea");
  descInput.value = video.description || "";

  seqInput.addEventListener("input", () => {
    const seqValue = Number(seqInput.value);
    if (!Number.isNaN(seqValue) && seqValue > 0) {
      titleInput.value = applySequenceToTitle(titleInput.value, seqValue);
    }
  });

  grid.appendChild(titleField);
  grid.appendChild(seqField);
  grid.appendChild(tagsField);
  grid.appendChild(descField);

  const actions = document.createElement("div");
  actions.className = "actions";

  const saveBtn = document.createElement("button");
  saveBtn.className = "btn subtle";
  saveBtn.textContent = "Save";
  saveBtn.onclick = async () => {
    await patchVideo(video.id, {
      title: titleInput.value,
      description: descInput.value,
      tags: tagsInput.value,
      sequence: Number(seqInput.value) || null,
    });
  };

  const uploadBtn = document.createElement("button");
  uploadBtn.className = "btn";
  uploadBtn.textContent = "Upload";
  uploadBtn.disabled = ["uploading", "uploaded", "skipped"].includes(video.status);
  uploadBtn.onclick = async () => {
    await fetch(`/api/videos/${video.id}/upload`, { method: "POST" });
  };

  const skipBtn = document.createElement("button");
  skipBtn.className = "btn ghost";
  skipBtn.textContent = "Skip";
  skipBtn.disabled = ["uploaded", "skipped"].includes(video.status);
  skipBtn.onclick = async () => {
    await fetch(`/api/videos/${video.id}/skip`, { method: "POST" });
  };

  actions.appendChild(saveBtn);
  actions.appendChild(uploadBtn);
  actions.appendChild(skipBtn);

  card.appendChild(header);
  card.appendChild(grid);
  card.appendChild(actions);

  if (video.error) {
    const errorBox = document.createElement("div");
    errorBox.className = "error-box";
    errorBox.textContent = video.error;
    card.appendChild(errorBox);
  }

  return card;
};

const createField = (labelText, type) => {
  const field = document.createElement("div");
  field.className = "field";
  const label = document.createElement("label");
  label.textContent = labelText;
  const control = document.createElement(type);
  field.appendChild(label);
  field.appendChild(control);
  return field;
};

const patchVideo = async (id, payload) => {
  const body = { ...payload };
  if (!body.sequence) {
    delete body.sequence;
  }
  await fetch(`/api/videos/${id}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
};

const initEvents = () => {
  const source = new EventSource("/api/events");
  source.onmessage = () => fetchVideos();
  source.onerror = () => {
    source.close();
    setTimeout(initEvents, 5000);
  };
};

refreshBtn.addEventListener("click", fetchVideos);

fetchVideos();
initEvents();
