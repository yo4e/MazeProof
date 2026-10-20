import { createBatchUI } from "/batch.js";

const $ = (id) => document.getElementById(id);
const clone = (value) => structuredClone(value);
let token =
  location.hash.slice(1) || sessionStorage.getItem("mazeproof-token") || "";
if (location.hash) {
  sessionStorage.setItem("mazeproof-token", token);
  history.replaceState(null, "", "/");
}
let state = null,
  source = "problem",
  tool = "wall",
  image = null,
  undo = [],
  redo = [];
let unsaved = false;
let batchUI = null;
let imageLoadSerial = 0;
let serial = 0,
  controller = null,
  busy = false,
  dirty = false,
  selected = null,
  unknownPage = 0;
const labels = {
  reachability: "入口から出口",
  uniqueness: "唯一解",
  routeValidity: "解答の合法性",
  mazeIdentity: "問題・解答の一致",
  renderedAgreement: "構造JSONとの一致",
};
const errors = {
  LOCAL_SESSION_REQUIRED: "起動時に表示された専用URLから開き直してください。",
  BUSY: "処理中です。少し待って、もう一度実行してください。",
  UNRESOLVED_OBSERVATIONS: "橙色の境界と赤線の確認を完了してください。",
  FIX_MODEL_BEFORE_APPROVAL:
    "入口・出口や余分な開口など、モデルの不正を先に修正してください。",
  STALE_REVISION: "状態を同期しました。もう一度実行してください。",
  SESSION_EXPIRED:
    "セッションが終了しました。保存した作業か原画像を開き直してください。",
  CELL_TOO_SMALL: "1セル8ピクセル以上になる格子を指定してください。",
  CROP_RANGE: "切り出し枠を画像の範囲内に指定してください。",
  GRID_LIMIT: "行と列は1〜250の整数で指定してください。",
  IMAGE_DECODE_FAILED: "画像を読み込めません。別のPNG/JPEGで試してください。",
  PNG_JPEG_PDF_REQUIRED: "PNG、JPEG、PDFを選択してください。",
  FORMAT_MISMATCH: "拡張子とファイルの実際の形式が一致していません。",
  WORKER_TIMEOUT:
    "処理時間の上限に達しました。小さな画像かページでやり直してください。",
  MEMORY_LIMIT: "メモリ上限に達しました。画像サイズを小さくしてください。",
  PIXEL_LIMIT:
    "画像は2,000万画素以下にしてください。PDFは144dpiでの描画サイズが上限を超えました。",
  BYTE_LIMIT: "1ファイル25MiB以下にしてください。",
  PDF_PAGE_LIMIT: "PDFは20ページ以内に分割してください。",
  PDF_PAGE_RANGE: "指定されたPDFページがありません。",
  ENCRYPTED_PDF: "暗号化PDFには対応していません。",
  PDF_DECODE_FAILED:
    "このPDFは読み込めません。暗号化・破損や未対応形式の可能性があります。",
  GEOMETRY_NUMBER: "切り出し枠の数値を確認してください。",
  WORKSPACE_LIMIT:
    "保持できる作業量の上限です。一括作業を保存して件数を分けるか、不要な行を除いて再試行してください。",
};
function message(text) {
  $("message").textContent = text;
  $("message").hidden = false;
  clearTimeout(message.timer);
  message.timer = setTimeout(() => ($("message").hidden = true), 9000);
}
function fail(error) {
  message(error.message || "処理に失敗しました。もう一度お試しください。");
}
async function api(path, body, signal) {
  const response = await fetch("/api/" + path, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Authorization: "Bearer " + token,
    },
    body: JSON.stringify(body),
    signal,
  });
  const data = await response.json();
  if (!response.ok) {
    const error = new Error(
      errors[data.error] || `処理を完了できませんでした (${data.error})`,
    );
    error.code = data.error;
    error.result = data.result;
    throw error;
  }
  return data;
}
function setBusy(value, cancellable = true) {
  busy = value;
  $("busy").hidden = !value;
  $("cancel").hidden = !cancellable;
  $("welcome").inert = value;
  $("workbench").inert = value;
  $("reset").disabled = value;
  batchUI?.setBusy(value);
}
async function confirmAction(title, text) {
  $("dialog-title").textContent = title;
  $("dialog-text").textContent = text;
  return new Promise((resolve) => {
    const finish = (v) => {
      $("confirm-dialog").close();
      resolve(v);
    };
    $("dialog-no").onclick = () => finish(false);
    $("dialog-yes").onclick = () => finish(true);
    $("confirm-dialog").oncancel = (e) => {
      e.preventDefault();
      finish(false);
    };
    $("confirm-dialog").showModal();
  });
}
function invalidate() {
  state.result = null;
  state.approved = false;
  dirty = true;
  unsaved = true;
  $("confirm-review").checked = false;
  batchUI?.changed(state);
  renderResult();
}
function remember() {
  undo.push(
    clone({ edits: state.edits, uniqueRequired: state.uniqueRequired }),
  );
  if (undo.length > 60) undo.shift();
  redo = [];
}
function change(action) {
  if (busy || !state) return;
  remember();
  action();
  invalidate();
  renderControls();
  draw();
}
async function display(next) {
  state = next;
  dirty = false;
  unsaved = true;
  tool = "wall";
  undo = [];
  redo = [];
  selected = null;
  unknownPage = 0;
  source = "problem";
  $("welcome").hidden = true;
  $("workbench").hidden = false;
  batchUI?.displayed(next);
  $("confirm-review").checked = false;
  $("zoom").value = 100;
  $("work-title").textContent = "壁と解答を確かめる";
  renderControls();
  renderResult();
  await loadImage();
}
async function importWork(path, body) {
  const generation = ++serial;
  controller = new AbortController();
  setBusy(true, true);
  try {
    if (state) {
      invalidate();
      await api(
        "revoke",
        { id: state.id, revision: state.revision },
        controller.signal,
      );
    }
    const next = await api(path, body, controller.signal);
    if (generation !== serial) return;
    const old = state;
    await display(next);
    if (old)
      api("close", { id: old.id, revision: old.revision }).catch(() => {});
    return true;
  } catch (error) {
    if (error.name !== "AbortError") fail(error);
    return false;
  } finally {
    if (generation === serial) {
      setBusy(false);
      controller = null;
    }
  }
}
$("cancel").onclick = () => {
  serial++;
  controller?.abort();
  controller = null;
  setBusy(false);
  message("読み込みを取り消しました。前の作業は残っています。");
};
async function readFile(file) {
  if (file.size > 25 * 1024 * 1024) throw new Error(errors.BYTE_LIMIT);
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(reader.result.split(",")[1]);
    reader.onerror = () => reject(new Error("ファイルを読み込めません。"));
    reader.readAsDataURL(file);
  });
}
$("import-form").onsubmit = async (event) => {
  event.preventDefault();
  try {
    const sources = {};
    for (const role of ["problem", "solution"]) {
      const file = $(role + "-file").files[0];
      if (!file) continue;
      sources[role] = { name: file.name, data: await readFile(file) };
      if (file.name.toLowerCase().endsWith(".pdf"))
        sources[role].page = Number($(role + "-page").value);
    }
    const reference = $("reference-file").files[0];
    if (reference && reference.size > 25 * 1024 * 1024)
      throw new Error(errors.BYTE_LIMIT);
    await importWork("import", {
      sources,
      ...(reference ? { reference: JSON.parse(await reference.text()) } : {}),
    });
  } catch (error) {
    fail(error);
  }
};
$("demo").onclick = () => importWork("demo", {});
$("project-file").onchange = async () => {
  try {
    const file = $("project-file").files[0];
    if (!file) return;
    if (file.size > 72 * 1024 * 1024)
      throw new Error("作業ファイルが大きすぎます。");
    if (await importWork("restore", { project: JSON.parse(await file.text()) }))
      message("作業を復元しました。承認は再度行ってください。");
  } catch (error) {
    fail(error);
  } finally {
    $("project-file").value = "";
  }
};
$("reset").onclick = async () => {
  if (await batchUI?.reset()) return;
  if (
    state &&
    !(await confirmAction(
      "新しい検品をはじめますか？",
      "保存していない作業はこの画面から消えます。必要なら先に「作業を保存」を使ってください。",
    ))
  )
    return;
  const old = state;
  state = null;
  image = null;
  dirty = false;
  undo = [];
  redo = [];
  serial++;
  if (old) api("close", { id: old.id, revision: old.revision }).catch(() => {});
  $("workbench").hidden = true;
  $("welcome").hidden = false;
  $("import-form").reset();
};
async function loadImage() {
  const expected = source,
    workspaceId = state.id,
    generation = ++imageLoadSerial;
  const picture = new Image();
  image = null;
  $("canvas")
    .getContext("2d")
    .clearRect(0, 0, $("canvas").width, $("canvas").height);
  updateApprovalButton();
  picture.src = "data:image/png;base64," + state.observations[source].image;
  await picture.decode();
  if (
    source !== expected ||
    state?.id !== workspaceId ||
    generation !== imageLoadSerial
  )
    return;
  image = picture;
  draw();
  updateApprovalButton();
}
async function switchSource(role) {
  if (!state.observations[role]) return;
  source = role;
  if (role === "problem" && tool === "route") tool = "wall";
  selected = null;
  unknownPage = 0;
  renderControls();
  await loadImage();
}
$("tab-problem").onclick = () => switchSource("problem");
$("tab-solution").onclick = () => switchSource("solution");
function pendingCount() {
  return Object.entries(state.observations).reduce(
    (n, [role, obs]) =>
      n +
      obs.unknowns.filter((u) => !state.edits[role].resolved.includes(u.id))
        .length +
      (!state.edits[role].routeReviewed ? 1 : 0),
    0,
  );
}
function renderControls() {
  if (!state) return;
  const obs = state.observations[source],
    edit = state.edits[source];
  $("tab-solution").disabled = !state.observations.solution;
  $("tab-problem").classList.toggle("active", source === "problem");
  $("tab-solution").classList.toggle("active", source === "solution");
  $("source-name").textContent = obs.name + " · " + obs.imageSize.join(" × ");
  for (const [key, value] of Object.entries(obs.geometry)) $(key).value = value;
  for (const button of $("tools").querySelectorAll("button")) {
    button.classList.toggle("active", button.dataset.tool === tool);
    button.disabled = button.dataset.tool === "route" && source !== "solution";
  }
  $("route-controls").hidden = source !== "solution";
  $("route-reviewed").checked = edit.routeReviewed;
  $("unique-required").checked = state.uniqueRequired;
  $("undo").disabled = !undo.length;
  $("redo").disabled = !redo.length;
  const unknown = obs.unknowns.filter((u) => !edit.resolved.includes(u.id));
  $("unknown-count").textContent = unknown.length;
  $("unknown-list").replaceChildren();
  if (unknownPage >= unknown.length) unknownPage = 0;
  for (const item of unknown.slice(unknownPage, unknownPage + 40)) {
    const button = document.createElement("button");
    button.textContent = `${item.field === "horizontalWalls" ? "水平" : "垂直"} [${item.row}, ${item.col}] · ${item.reason === "RED_OCCLUSION" ? "赤線の下" : "壁が不鮮明"}`;
    button.onclick = () => {
      selected = item;
      tool = "resolve";
      $("edge-field").value = item.field;
      $("edge-row").value = item.row;
      $("edge-col").value = item.col;
      draw();
      renderTools();
      message(
        "選択した境界を拡大して確認し、「座標で境界を編集」の確認または画面上の境界をクリックしてください。",
      );
    };
    $("unknown-list").append(button);
  }
  $("more-unknown").hidden = unknown.length <= 40;
  $("observation-notes").textContent =
    obs.notices
      .map(
        (n) =>
          ({
            HUMAN_REVIEW_REQUIRED: "認識結果は必ず原画像と照合してください。",
            GRID_ESTIMATE_UNCERTAIN:
              "格子の自動推定が不確かです。行列数と外周枠を確認してください。",
            CHOOSE_TWO_OPENINGS:
              "外周開口を入口・出口の2つに修正してください。",
            RED_ROUTE_UNCERTAIN:
              "赤線が不鮮明・不連続です。必要なら解答を描き直してください。",
          })[n] || n,
      )
      .join(" ") +
    (obs.transform.format === "PDF"
      ? " PDFの描画結果のみを検査します。ベクター構造との一致は未検査です。"
      : "");
  renderTools();
  updateApprovalButton();
}
function renderTools() {
  const text = {
    wall: "境界をクリックすると壁と通路を切り替え、確認済みにします。",
    resolve: "原画像を見て境界をクリックすると、推定のまま確認済みにします。",
    entrance:
      "外周の境界をクリックして入口に指定します。壁の開閉は別に修正してください。",
    exit: "外周の境界をクリックして出口に指定します。壁の開閉は別に修正してください。",
    route:
      "入口から出口までセル中心を順にクリック。最後のセルをクリックすると一歩戻ります。",
  };
  $("tool-help").textContent = text[tool];
  for (const b of $("tools").querySelectorAll("button"))
    b.classList.toggle("active", b.dataset.tool === tool);
}
$("tools").onclick = (e) => {
  if (e.target.dataset.tool) {
    tool = e.target.dataset.tool;
    renderTools();
  }
};
$("more-unknown").onclick = () => {
  unknownPage += 40;
  renderControls();
};
function resolveEdge(field, row, col, toggle) {
  const model = state.edits[source].model;
  if (!model[field]?.[row] || typeof model[field][row][col] !== "boolean") {
    message("境界の座標が範囲外です。");
    return;
  }
  change(() => {
    if (toggle) model[field][row][col] = !model[field][row][col];
    const id = `${field}:${row}:${col}`;
    if (
      state.observations[source].unknowns.some((u) => u.id === id) &&
      !state.edits[source].resolved.includes(id)
    )
      state.edits[source].resolved.push(id);
  });
}
$("edge-toggle").onclick = () =>
  resolveEdge(
    $("edge-field").value,
    +$("edge-row").value,
    +$("edge-col").value,
    true,
  );
$("edge-resolve").onclick = () =>
  resolveEdge(
    $("edge-field").value,
    +$("edge-row").value,
    +$("edge-col").value,
    false,
  );
$("canvas").onclick = (e) => {
  if (!state || busy || !image) return;
  const canvas = $("canvas"),
    rect = canvas.getBoundingClientRect();
  const x = ((e.clientX - rect.left) * canvas.width) / rect.width,
    y = ((e.clientY - rect.top) * canvas.height) / rect.height;
  const g = state.observations[source].geometry;
  const gx = ((x - g.x0) / (g.x1 - g.x0)) * g.cols,
    gy = ((y - g.y0) / (g.y1 - g.y0)) * g.rows;
  if (gx < -0.15 || gy < -0.15 || gx > g.cols + 0.15 || gy > g.rows + 0.15)
    return;
  const model = state.edits[source].model;
  if (tool === "route") {
    if (source !== "solution") return;
    const row = Math.floor(gy),
      col = Math.floor(gx);
    if (row < 0 || row >= g.rows || col < 0 || col >= g.cols) return;
    change(() => {
      const route = model.route || (model.route = []),
        last = route.at(-1);
      if (last?.row === row && last?.col === col) route.pop();
      else if (route.length < g.rows * g.cols) route.push({ row, col });
      state.edits[source].routeReviewed = false;
    });
    return;
  }
  const horizontal =
    Math.abs(gy - Math.round(gy)) <= Math.abs(gx - Math.round(gx));
  const field = horizontal ? "horizontalWalls" : "verticalWalls",
    row = horizontal ? Math.round(gy) : Math.floor(gy),
    col = horizontal ? Math.floor(gx) : Math.round(gx);
  if (!model[field]?.[row] || typeof model[field][row][col] !== "boolean")
    return;
  selected = { field, row, col };
  $("edge-field").value = field;
  $("edge-row").value = row;
  $("edge-col").value = col;
  if (tool === "wall" || tool === "resolve") {
    resolveEdge(field, row, col, tool === "wall");
    return;
  }
  let point = null;
  if (horizontal && row === 0) point = { row: 0, col, side: "N" };
  if (horizontal && row === g.rows) point = { row: g.rows - 1, col, side: "S" };
  if (!horizontal && col === 0) point = { row, col: 0, side: "W" };
  if (!horizontal && col === g.cols)
    point = { row, col: g.cols - 1, side: "E" };
  if (point) change(() => (model[tool] = point));
  else message("入口・出口は外周の境界を選んでください。");
};
function draw() {
  if (!image || !state) return;
  const canvas = $("canvas"),
    ctx = canvas.getContext("2d");
  canvas.width = image.width;
  canvas.height = image.height;
  const available = Math.max(250, $("viewport").clientWidth - 52),
    base = Math.min(
      available,
      (Math.max(250, $("viewport").clientHeight - 52) * image.width) /
        image.height,
    );
  canvas.style.width = base * (+$("zoom").value / 100) + "px";
  canvas.style.height = "auto";
  $("zoom-value").textContent = $("zoom").value + "%";
  ctx.drawImage(image, 0, 0);
  if (!$("overlay").checked) return;
  const obs = state.observations[source],
    model = state.edits[source].model,
    g = obs.geometry,
    dx = (g.x1 - g.x0) / g.cols,
    dy = (g.y1 - g.y0) / g.rows;
  const pending = new Set(
    obs.unknowns
      .filter((u) => !state.edits[source].resolved.includes(u.id))
      .map((u) => u.id),
  );
  for (const field of ["horizontalWalls", "verticalWalls"])
    for (let r = 0; r < model[field].length; r++)
      for (let c = 0; c < model[field][r].length; c++) {
        const wall = model[field][r][c],
          unknown = pending.has(`${field}:${r}:${c}`),
          focus =
            selected?.field === field &&
            selected.row === r &&
            selected.col === c;
        ctx.beginPath();
        ctx.strokeStyle = focus
          ? "#8848d9"
          : unknown
            ? "#ee9b27"
            : wall
              ? "#168b82"
              : "#78bcb24d";
        ctx.lineWidth = focus
          ? Math.max(4, dx * 0.07)
          : unknown
            ? Math.max(3, dx * 0.05)
            : wall
              ? Math.max(2, dx * 0.035)
              : 1;
        ctx.setLineDash(unknown ? [5, 4] : wall ? [] : [2, 5]);
        if (field === "horizontalWalls") {
          ctx.moveTo(g.x0 + c * dx, g.y0 + r * dy);
          ctx.lineTo(g.x0 + (c + 1) * dx, g.y0 + r * dy);
        } else {
          ctx.moveTo(g.x0 + c * dx, g.y0 + r * dy);
          ctx.lineTo(g.x0 + c * dx, g.y0 + (r + 1) * dy);
        }
        ctx.stroke();
      }
  ctx.setLineDash([]);
  if (model.route?.length) {
    ctx.beginPath();
    ctx.strokeStyle = "#e74865";
    ctx.lineWidth = Math.max(2, dx * 0.055);
    for (const [i, p] of model.route.entries()) {
      const x = g.x0 + (p.col + 0.5) * dx,
        y = g.y0 + (p.row + 0.5) * dy;
      i ? ctx.lineTo(x, y) : ctx.moveTo(x, y);
    }
    ctx.stroke();
    for (const [i, p] of model.route.entries()) {
      ctx.beginPath();
      ctx.arc(
        g.x0 + (p.col + 0.5) * dx,
        g.y0 + (p.row + 0.5) * dy,
        Math.max(2, dx * 0.045),
        0,
        Math.PI * 2,
      );
      ctx.fillStyle = "#e74865";
      ctx.fill();
    }
  }
  for (const key of ["entrance", "exit"]) {
    const p = model[key],
      x = g.x0 + (p.col + 0.5) * dx,
      y = g.y0 + (p.row + 0.5) * dy;
    ctx.beginPath();
    ctx.arc(x, y, Math.max(7, Math.min(dx, dy) * 0.17), 0, Math.PI * 2);
    ctx.fillStyle = key === "entrance" ? "#14745e" : "#293f36";
    ctx.fill();
    ctx.fillStyle = "white";
    ctx.font = `bold ${Math.max(9, Math.min(dx, dy) * 0.18)}px sans-serif`;
    ctx.textAlign = "center";
    ctx.textBaseline = "middle";
    ctx.fillText(key === "entrance" ? "S" : "G", x, y);
  }
}
$("overlay").onchange = draw;
$("zoom").oninput = draw;
window.addEventListener("resize", draw);
$("undo").onclick = () => {
  if (!undo.length) return;
  redo.push(
    clone({ edits: state.edits, uniqueRequired: state.uniqueRequired }),
  );
  Object.assign(state, undo.pop());
  invalidate();
  renderControls();
  draw();
};
$("redo").onclick = () => {
  if (!redo.length) return;
  undo.push(
    clone({ edits: state.edits, uniqueRequired: state.uniqueRequired }),
  );
  Object.assign(state, redo.pop());
  invalidate();
  renderControls();
  draw();
};
$("clear-route").onclick = () =>
  change(() => {
    state.edits[source].model.route = [];
    state.edits[source].routeReviewed = false;
  });
$("reverse-route").onclick = () =>
  change(() => {
    state.edits[source].model.route.reverse();
    state.edits[source].routeReviewed = false;
  });
$("route-reviewed").onchange = () => {
  const checked = $("route-reviewed").checked;
  change(() => (state.edits[source].routeReviewed = checked));
};
$("unique-required").onchange = () => {
  const checked = $("unique-required").checked;
  change(() => (state.uniqueRequired = checked));
};
async function reanalyze(rotate) {
  if (
    !(await confirmAction(
      "画像を再認識しますか？",
      "現在の壁・解答線の修正と承認は取り消されます。保存した作業は残ります。",
    ))
  )
    return;
  const sources = clone(state.sources);
  if (rotate) {
    sources[source].rotation = ((sources[source].rotation || 0) + 90) % 360;
    delete sources[source].geometry;
  } else {
    sources[source].geometry = {};
    for (const key of ["x0", "y0", "x1", "y1", "cols", "rows"])
      sources[source].geometry[key] = Number($(key).value);
  }
  await importWork("import", { sources, reference: state.reference });
}
$("reanalyze").onclick = () => reanalyze(false);
$("rotate").onclick = () => reanalyze(true);
function updateApprovalButton() {
  $("approve").disabled =
    !state || !image || !$("confirm-review").checked || pendingCount() > 0;
}
$("confirm-review").onchange = updateApprovalButton;
function renderResult() {
  const result = state?.result,
    status = result?.overallStatus || "NEEDS_REVIEW";
  const names = {
    PASS: "条件付き PASS",
    FAIL: "FAIL",
    NEEDS_REVIEW: "確認待ち",
    INVALID_INPUT: "入力を修正",
    UNSUPPORTED: "未対応",
    RESOURCE_LIMIT: "上限に達しました",
    ERROR: "処理エラー",
  };
  for (const id of ["approval-state", "result-status"]) {
    $(id).textContent = dirty ? "変更あり・再確認" : names[status];
    $(id).className =
      "badge " +
      (status === "PASS"
        ? "pass"
        : status === "FAIL"
          ? "fail"
          : status === "NEEDS_REVIEW"
            ? "review"
            : "error");
  }
  $("result-summary").textContent = dirty
    ? "モデルが変わったため、前の結果と承認を取り消しました。"
    : status === "PASS"
      ? "承認したモデルで、要求された検査が成立しました。未検査の範囲も確認してください。"
      : status === "FAIL"
        ? "承認したモデルに条件違反があります。下の理由と反例を確認してください。"
        : "まだ確定判定ではありません。以下は認識したモデルの暫定結果です。";
  $("checks").replaceChildren();
  for (const [key, label] of Object.entries(labels)) {
    const check = result?.checks[key],
      card = document.createElement("div");
    card.className = "check-card";
    const title = document.createElement("small");
    title.textContent = label;
    const value = document.createElement("strong");
    value.textContent = check
      ? check.status === "NOT_RUN"
        ? "未検査"
        : check.status + (status === "NEEDS_REVIEW" ? "（暫定）" : "")
      : "—";
    if (check?.status === "FAIL") value.className = "fail";
    const code = document.createElement("code");
    code.textContent = check?.reasonCode || "";
    card.append(title, value, code);
    $("checks").append(card);
  }
  $("issues").replaceChildren();
  for (const issue of result?.issues || []) {
    if (issue.reasonCode === "HUMAN_REVIEW_REQUIRED") continue;
    const p = document.createElement("p");
    p.textContent =
      (labels[issue.check] || "入力") +
      " · " +
      issue.reasonCode +
      (issue.coordinates ? " · " + JSON.stringify(issue.coordinates) : "");
    $("issues").append(p);
  }
  $("evidence").textContent = result
    ? JSON.stringify(
        {
          notChecked: result.scope.notChecked,
          assurance: result.recognition.assurance,
          digest: result.recognition.modelDigest,
          pending: result.recognition.pending,
          evidence: { ...result.evidence, recognitionEdits: undefined },
        },
        null,
        2,
      )
    : "再検査すると反例と差分を表示します。";
  updateApprovalButton();
}
async function evaluate(approve = false) {
  if (!state) return false;
  setBusy(true, false);
  try {
    const next = await api(approve ? "approve" : "evaluate", {
      id: state.id,
      revision: state.revision,
      edits: state.edits,
      uniqueRequired: state.uniqueRequired,
    });
    Object.assign(state, next);
    dirty = false;
    batchUI?.updated(state);
    renderControls();
    renderResult();
    draw();
    return true;
  } catch (error) {
    state.result = null;
    state.approved = false;
    dirty = true;
    batchUI?.changed(state);
    try {
      const sync = await api("state", { id: state.id });
      state.revision = sync.revision;
    } catch {}
    renderResult();
    fail(error);
    return false;
  } finally {
    setBusy(false);
  }
}
$("evaluate").onclick = () => evaluate();
$("approve").onclick = () => {
  if ($("confirm-review").checked && pendingCount() === 0) evaluate(true);
};
function download(name, data, type = "application/json") {
  const blob =
    data instanceof Blob
      ? data
      : new Blob(
          [typeof data === "string" ? data : JSON.stringify(data, null, 2)],
          { type },
        );
  const url = URL.createObjectURL(blob),
    anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = name;
  anchor.click();
  setTimeout(() => URL.revokeObjectURL(url), 10000);
}
async function exportProject() {
  if (!(await evaluate())) return null;
  try {
    const data = await api("export", {
      id: state.id,
      revision: state.revision,
    });
    return data.project;
  } catch (error) {
    fail(error);
    return null;
  }
}
$("save-project").onclick = async () => {
  const project = await exportProject();
  if (project) {
    download("mazeproof-work.mazeproof", project);
    unsaved = false;
  }
};
$("save-report").onclick = async () => {
  if (await evaluate()) download("mazeproof-report.json", state.result);
};
$("save-model").onclick = () =>
  download(`mazeproof-${source}.json`, state.edits[source].model);
$("save-overlay").onclick = () => {
  $("canvas").toBlob(
    (blob) => download(`mazeproof-${source}-overlay.png`, blob),
    "image/png",
  );
};
const esc = (value) =>
  String(value).replace(
    /[&<>"']/g,
    (c) =>
      ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[
        c
      ],
  );
$("save-html").onclick = async () => {
  if (!(await evaluate())) return;
  const result = state.result;
  const rows = Object.entries(result.checks)
    .map(
      ([k, v]) =>
        `<tr><th>${esc(labels[k])}</th><td>${esc(v.status)}</td><td>${esc(v.reasonCode)}</td></tr>`,
    )
    .join("");
  const html = `<!doctype html><html lang="ja"><meta charset="utf-8"><title>MazeProof 検品レポート</title><style>body{font:15px system-ui;max-width:900px;margin:50px auto;color:#254735;padding:20px}h1{font-size:32px}table{border-collapse:collapse;width:100%}td,th{padding:12px;text-align:left;border-bottom:1px solid #ddd}pre{white-space:pre-wrap;overflow-wrap:anywhere;font-size:11px}img{max-width:100%;max-height:600px}aside{background:#f0f5ee;padding:20px}small{color:#667}</style><h1>MazeProof · ${esc(result.overallStatus)}</h1><aside>この結果は${result.recognition.assurance === "human_confirmed" ? "人間が確認・承認した" : "未承認の暫定"}モデルに対する判定です。元画像の完全な証明ではありません。PDFのベクター構造は未検査です。</aside><p>未検査: ${esc(result.scope.notChecked.join(", ") || "なし（上記の確証範囲内）")}</p><table>${rows}</table>${Object.entries(
    state.observations,
  )
    .map(
      ([role, obs]) =>
        `<h2>${role === "problem" ? "問題" : "解答"} · ${esc(obs.name)}</h2><small>SHA-256: ${esc(obs.digest)}</small><p><img alt="原画像の描画" src="data:image/png;base64,${obs.image}"></p>`,
    )
    .join(
      "",
    )}<h2>検証の詳細</h2><pre>${esc(JSON.stringify(result, null, 2))}</pre></html>`;
  download("mazeproof-report.html", html, "text/html");
};
batchUI = createBatchUI({
  api,
  readFile,
  display,
  evaluate,
  download,
  labels,
  escape: esc,
  fail,
  message,
  confirm: confirmAction,
  state: () => state,
  clear: () => {
    state = null;
    image = null;
    imageLoadSerial++;
    dirty = false;
    undo = [];
    redo = [];
    unsaved = false;
    $("workbench").hidden = true;
  },
});
// Give the trusted, same-origin guide a tab-scoped copy of the current local
// session, so its Home link works. Do not put the token in the guide URL or
// persistent storage; sever the opener before loading the guide.
$("help-link").onclick = (event) => {
  event.preventDefault();
  const guide = window.open("", "_blank");
  if (!guide) {
    message("使い方を開くには、このサイトの別タブ表示を許可してください。");
    return;
  }
  if (token) guide.sessionStorage.setItem("mazeproof-token", token);
  guide.opener = null;
  guide.location.replace("/help");
};
window.addEventListener("beforeunload", (e) => {
  if (batchUI.hasWork() ? batchUI.hasUnsaved() : state && unsaved) {
    e.preventDefault();
    e.returnValue = "";
  }
});
if (!token) message(errors.LOCAL_SESSION_REQUIRED);
