const UNSPECIFIED = "指定なし";

const GENDER_LABEL = {
  male: "男性",
  female: "女性",
  any: "不問",
};

const SECONDS_LABEL = {
  10: "10秒",
  20: "20秒",
  30: "30秒",
};

const BADGE = {
  dialogue: "セリフ",
  narration: "ナレーション",
};

const state = {
  lines: [],
  favorites: new Set(),
  history: [],
  current: null,
};

const els = {
  seconds: document.querySelector("#seconds"),
  gender: document.querySelector("#gender"),
  category: document.querySelector("#category"),
  tag: document.querySelector("#tag"),
  tone: document.querySelector("#tone"),
  badge: document.querySelector("#badge"),
  direction: document.querySelector("#direction"),
  body: document.querySelector("#body"),
  meta: document.querySelector("#meta"),
  favorite: document.querySelector("#favorite"),
  recent: document.querySelector("#recent"),
  status: document.querySelector("#status"),
};

document.querySelectorAll('input[name="kind"]').forEach((input) => {
  input.addEventListener("change", () => {
    fillCategory();
    updateStatus();
  });
});
els.seconds.addEventListener("change", updateStatus);
els.gender.addEventListener("change", updateStatus);
els.category.addEventListener("change", updateStatus);
els.tag.addEventListener("change", updateStatus);
els.tone.addEventListener("change", updateStatus);
document.querySelector("#draw").addEventListener("click", () => draw());
document.querySelector("#copy").addEventListener("click", copyCurrent);
document.querySelector("#favorite").addEventListener("click", toggleFavorite);
document.querySelector("#reload").addEventListener("click", () => reload(false));

reload(true);

async function reload(drawFirst) {
  try {
    const data = await api("/api/lines");
    // 選択肢の並びを id 順の初出順にそろえる（台本が複数ファイルでも順序が安定する）
    state.lines = [...data.lines].sort((a, b) => a.id.localeCompare(b.id));
    fillFilters();
    await loadFavorites();
    renderRecent();
    updateStatus();
    if (drawFirst) {
      await draw();
    } else if (state.current) {
      const still = state.lines.find((line) => line.id === state.current.id);
      if (still) showLine(still);
    }
  } catch (error) {
    fail(error.message);
  }
}

async function loadFavorites() {
  try {
    const data = await api("/api/favorites");
    state.favorites = new Set(data.ids);
    syncFavorite();
  } catch (error) {
    state.favorites = new Set();
    syncFavorite();
    setStatus(error.message);
  }
}

async function draw() {
  if (state.lines.length === 0) {
    fail("台本を読めませんでした。読み直すと、もう一度試せます。");
    return;
  }
  try {
    const data = await api("/api/draw", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ ...criteria(), avoid_ids: state.history.slice(0, 5) }),
    });
    state.history.unshift(data.line.id);
    state.history = state.history.slice(0, 30);
    showLine(data.line);
    renderRecent();
    updateStatus();
  } catch (error) {
    fail(error.message);
  }
}

function showLine(line) {
  state.current = line;
  els.badge.textContent = BADGE[line.kind] || line.kind;
  els.badge.classList.remove("quiet");
  els.direction.textContent = directionText(line);
  els.body.textContent = line.text;
  els.meta.textContent = metaText(line);
  syncFavorite();
}

function fail(message) {
  state.current = null;
  els.badge.textContent = "お知らせ";
  els.badge.classList.add("quiet");
  els.direction.textContent = "";
  els.body.textContent = message;
  els.meta.textContent = "";
  syncFavorite();
  setStatus(message);
}

function currentKind() {
  return document.querySelector('input[name="kind"]:checked').value;
}

function criteria() {
  const kind = currentKind();
  const seconds = chosen(els.seconds);
  return {
    kind: kind || null,
    tag: chosen(els.tag),
    tone: chosen(els.tone),
    seconds: seconds ? Number(seconds) : null,
    gender: chosen(els.gender),
    category: chosen(els.category),
  };
}

function chosen(select) {
  return select.value === "" ? null : select.value;
}

function filteredLines() {
  const current = criteria();
  return state.lines.filter((line) => {
    if (current.kind && line.kind !== current.kind) return false;
    if (current.tag && !line.tags.includes(current.tag)) return false;
    if (current.tone && line.tone !== current.tone) return false;
    if (current.seconds && line.seconds !== current.seconds) return false;
    if (current.gender && line.gender !== current.gender) return false;
    if (current.category && line.category !== current.category) return false;
    return true;
  });
}

function updateStatus() {
  if (state.lines.length === 0) return;
  setStatus(`${filteredLines().length}件から引けます`);
}

function fillFilters() {
  fillCategory();
  fillSelect(els.tag, UNSPECIFIED, unique(state.lines.flatMap((line) => line.tags)));
  fillSelect(els.tone, UNSPECIFIED, unique(state.lines.map((line) => line.tone)));
}

function fillCategory() {
  const kind = currentKind();
  const values = kind
    ? unique(state.lines.filter((line) => line.kind === kind).map((line) => line.category))
    : [];
  fillSelect(els.category, UNSPECIFIED, values);
}

function fillSelect(select, placeholder, values, labelOf = (value) => value) {
  const previous = select.value;
  select.replaceChildren();
  select.append(option("", placeholder));
  values.forEach((value) => select.append(option(value, labelOf(value))));
  select.value = values.includes(previous) ? previous : "";
}

function option(value, label) {
  const node = document.createElement("option");
  node.value = value;
  node.textContent = label;
  return node;
}

function unique(values) {
  const seen = new Set();
  const result = [];
  values.forEach((value) => {
    if (!value || seen.has(value)) return;
    seen.add(value);
    result.push(value);
  });
  return result;
}

async function copyCurrent() {
  if (!state.current) {
    setStatus("まだコピーできる台本がありません。");
    return;
  }
  const text = copyText(state.current);
  try {
    await navigator.clipboard.writeText(text);
  } catch (_error) {
    const area = document.createElement("textarea");
    area.value = text;
    document.body.append(area);
    area.select();
    document.execCommand("copy");
    area.remove();
  }
  setStatus("コピーしました。");
}

async function toggleFavorite() {
  if (!state.current) {
    setStatus("お気に入りにする台本が、まだありません。");
    return;
  }
  try {
    const data = await api("/api/favorites", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ id: state.current.id }),
    });
    state.favorites = new Set(data.ids);
    syncFavorite();
    updateStatus();
  } catch (error) {
    setStatus(error.message);
  }
}

function syncFavorite() {
  const starred = state.current && state.favorites.has(state.current.id);
  els.favorite.textContent = starred ? "★ お気に入り" : "☆ お気に入り";
}

function renderRecent() {
  els.recent.replaceChildren();
  const ids = state.history.slice(0, 8);
  if (ids.length === 0) {
    const empty = document.createElement("p");
    empty.className = "empty";
    empty.textContent = "まだありません";
    els.recent.append(empty);
    return;
  }
  ids.forEach((id) => {
    const line = state.lines.find((item) => item.id === id) || state.current;
    const button = document.createElement("button");
    button.type = "button";
    button.textContent = recentLabel(line, id);
    button.addEventListener("click", () => {
      const found = state.lines.find((item) => item.id === id);
      if (!found) {
        setStatus("その台本は見つかりませんでした。");
        return;
      }
      showLine(found);
      updateStatus();
    });
    els.recent.append(button);
  });
}

function recentLabel(line, id) {
  if (!line || line.id !== id) return clip(id, 12);
  const head = line.situation ? `${line.situation} ` : "";
  return clip(`${head}${line.text}`, 16);
}

function clip(text, limit) {
  if (text.length <= limit) return text;
  return `${text.slice(0, limit - 1)}…`;
}

function metaText(line) {
  const parts = [];
  if (line.seconds) parts.push(SECONDS_LABEL[line.seconds] || `${line.seconds}秒`);
  if (line.gender) parts.push(GENDER_LABEL[line.gender] || line.gender);
  if (line.category) parts.push(line.category);
  if (line.tags.length > 0) parts.push(line.tags.map((tag) => `#${tag}`).join("  "));
  return parts.join("    ");
}

function directionText(line) {
  const parts = [];
  if (line.tone) parts.push(`読み方：${line.tone}`);
  if (line.situation) parts.push(`状況：${line.situation}`);
  return parts.join("\n");
}

function copyText(line) {
  return line.text;
}

function setStatus(text) {
  els.status.textContent = text;
}

async function api(path, options) {
  let response;
  try {
    response = await fetch(path, options);
  } catch (_error) {
    throw new Error("このページは py -3 main.py --web から開いてください。");
  }
  const data = await response.json().catch(() => ({}));
  if (!response.ok) {
    throw new Error(data.error || "うまく読めませんでした。");
  }
  return data;
}
