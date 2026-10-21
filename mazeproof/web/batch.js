// Batch navigation owns the queue; the server owns every verification/approval.
// Saved reports are never trusted as approval when a batch is reopened.
import { MAX_BUNDLE_BYTES, projectBlob } from "/files.js";
const $ = (id) => document.getElementById(id);
const MAX_ITEMS = 100;
const MAX_SOURCE_BYTES = 32 * 1024 * 1024;
const VERSION = "mazeproof.batch/1";
const node = (tag, text, className) => {
  const element = document.createElement(tag);
  if (text !== undefined) element.textContent = text;
  if (className) element.className = className;
  return element;
};
const isPDF = (source) => source.name.toLowerCase().endsWith(".pdf");
const brief = (result) => ({
  overallStatus: result.overallStatus,
  provisionalStatus: result.evidence?.provisionalStatus,
  pending: result.recognition?.pending.length || 0,
  checks: result.checks,
  assurance: result.recognition?.assurance,
});

export function createBatchUI(deps) {
  let rows = [],
    draft = [],
    solutions = [],
    active = null;
  let running = false,
    stop = false,
    locked = false,
    uiBusy = false;
  let unsaved = false,
    preparing = false;
  const guard =
    (fn) =>
    async (...args) => {
      try {
        await fn(...args);
      } catch (error) {
        deps.fail(error);
      }
    };
  async function exclusive(fn) {
    if (running || locked || uiBusy) return;
    locked = true;
    render();
    try {
      return await fn();
    } finally {
      locked = false;
      render();
    }
  }
  const button = (text, fn) => {
    const b = node("button", text);
    b.type = "button";
    b.onclick = guard(fn);
    b.disabled = running || locked || uiBusy;
    return b;
  };
  const sourceSize = (sources) =>
    Object.values(sources).reduce((n, s) => n + s.data.length, 0);
  function checkSources(items) {
    if (!items.length || items.length > MAX_ITEMS)
      throw new Error("一括検品は1〜100件にしてください。");
    let encodedBytes = 0;
    for (const item of items) {
      const sources = item.sources;
      if (
        !sources ||
        !sources.problem ||
        Object.keys(sources).some((k) => !["problem", "solution"].includes(k))
      )
        throw new Error("問題画像のない一括作業です。");
      for (const s of Object.values(sources)) {
        if (
          !s ||
          typeof s.name !== "string" ||
          s.name.length > 255 ||
          typeof s.data !== "string"
        )
          throw new Error("一括作業の画像データが不正です。");
      }
      encodedBytes += sourceSize(sources);
    }
    if (encodedBytes > Math.ceil(MAX_SOURCE_BYTES / 3) * 4)
      throw new Error("原画像の合計が32MiBを超えます。件数を分けてください。");
  }
  function makeRow(item) {
    return {
      key: crypto.randomUUID(),
      sources: item.project ? item.project.sources : item.sources,
      project: item.project || null,
      uniqueRequired: item.uniqueRequired ?? true,
      phase: "queued",
      id: null,
      revision: 0,
      result: null,
      error: "",
      dirty: false,
    };
  }
  function updated(next) {
    if (!active) return;
    const result = next.result ? brief(next.result) : null;
    if (
      active.digest !== next.digest ||
      JSON.stringify(active.result) !== JSON.stringify(result)
    )
      unsaved = true;
    Object.assign(active, {
      id: next.id,
      revision: next.revision,
      sources: next.sources || active.sources,
      digest: next.digest,
      result,
      phase: "ready",
      dirty: false,
    });
    $("batch-review-position").textContent =
      `${rows.indexOf(active) + 1} / ${rows.length} · ${active.sources.problem.name}`;
  }
  function showList() {
    active = null;
    deps.clear();
    $("welcome").hidden = true;
    $("workbench").hidden = true;
    $("batch-setup").hidden = true;
    $("batch-list").hidden = false;
    $("batch-review-nav").hidden = true;
    render();
  }
  async function flush() {
    return !active || (await deps.evaluate());
  }
  async function closeRow(row) {
    if (!row.id) return;
    await deps.api("close", { id: row.id, revision: row.revision });
    row.id = null;
  }
  async function release() {
    for (const row of rows) {
      try {
        await closeRow(row);
      } catch {
        /* A stopped server may already have cleared it. */
      }
    }
    const single = deps.state();
    if (!rows.length && single) {
      try {
        await deps.api("close", { id: single.id, revision: single.revision });
      } catch {}
    }
    rows = [];
    active = null;
    deps.clear();
  }
  function matches(row) {
    const filter = $("batch-filter").value;
    if (filter === "all") return true;
    if (filter === "error" || filter === "queued") return row.phase === filter;
    if (filter === "review")
      return (
        row.phase === "ready" && row.result?.assurance !== "human_confirmed"
      );
    if (filter === "suspect")
      return (
        row.phase === "ready" &&
        row.result?.assurance !== "human_confirmed" &&
        row.result?.provisionalStatus === "FAIL"
      );
    return row.phase === "ready" && row.result?.assurance === "human_confirmed";
  }
  function status(row) {
    if (row.phase === "queued") return "未処理";
    if (row.phase === "reading") return "読み込み中";
    if (row.phase === "error") return "読み取りエラー";
    if (row.dirty) return "変更あり・再確認";
    if (row.result?.assurance !== "human_confirmed") return "確認待ち";
    return row.result.overallStatus === "PASS" ? "条件付き PASS" : "FAIL";
  }
  function counts() {
    return {
      total: rows.length,
      queued: rows.filter((r) => r.phase === "queued" || r.phase === "reading")
        .length,
      review: rows.filter(
        (r) => r.phase === "ready" && r.result?.assurance !== "human_confirmed",
      ).length,
      pass: rows.filter(
        (r) =>
          r.phase === "ready" &&
          r.result?.assurance === "human_confirmed" &&
          r.result.overallStatus === "PASS",
      ).length,
      fail: rows.filter(
        (r) =>
          r.phase === "ready" &&
          r.result?.assurance === "human_confirmed" &&
          r.result.overallStatus === "FAIL",
      ).length,
      error: rows.filter((r) => r.phase === "error").length,
    };
  }
  function render() {
    const disabled = running || locked || uiBusy;
    $("reset").disabled = disabled;
    $("batch-resume").disabled =
      disabled || !rows.some((r) => r.phase === "queued");
    $("batch-retry").disabled =
      disabled || !rows.some((r) => r.phase === "error");
    $("batch-pause").hidden = !running;
    $("batch-pause").disabled = stop;
    for (const id of [
      "batch-save",
      "batch-report-json",
      "batch-report-html",
      "batch-back",
      "batch-next",
    ])
      $(id).disabled = disabled || !rows.length;
    $("batch-total").textContent = `${rows.length} 件`;
    const c = counts();
    $("batch-counts").textContent =
      `未処理 ${c.queued} · 確認待ち ${c.review} · 条件付き PASS ${c.pass} · FAIL ${c.fail} · エラー ${c.error}`;
    $("batch-progress").textContent = running
      ? stop
        ? "現在の1件が終わったら停止します。完了した結果は残ります。"
        : `${rows.filter((r) => ["ready", "error"].includes(r.phase)).length} / ${rows.length} 件の読み込み完了`
      : c.queued
        ? `未処理が ${c.queued} 件あります。「未処理を読み込む」で続けられます。`
        : "読み込みが終わりました。各迷路の確認を進めてください。";
    const body = $("batch-result-rows");
    body.replaceChildren();
    rows.forEach((row, index) => {
      if (!matches(row)) return;
      const tr = node("tr");
      tr.dataset.key = row.key;
      const identity = node("th");
      identity.scope = "row";
      identity.append(
        node("span", `${index + 1}. ${row.sources.problem.name}`),
      );
      identity.append(
        node(
          "small",
          `${isPDF(row.sources.problem) ? `問題 p.${row.sources.problem.page} · ` : ""}解答：${row.sources.solution ? row.sources.solution.name + (isPDF(row.sources.solution) ? ` p.${row.sources.solution.page}` : "") : "なし"}`,
        ),
      );
      const state = node("td", status(row));
      state.dataset.status =
        row.result?.assurance === "human_confirmed"
          ? row.result.overallStatus
          : row.phase;
      const details = node("td");
      if (row.phase === "error") details.textContent = row.error;
      else if (row.result) {
        details.append(node("div", `未確認箇所 ${row.result.pending}`));
        const failed = Object.entries(row.result.checks || {})
          .filter(([, v]) => v.status === "FAIL")
          .map(([key, v]) => `${deps.labels[key]}：${v.reasonCode}`);
        details.append(
          node(
            "small",
            failed.length
              ? (row.result.assurance === "human_confirmed" ? "" : "暫定 · ") +
                  failed.join(" / ")
              : row.result.assurance === "human_confirmed"
                ? "未検査の項目は個別の結果で確認してください。"
                : "全体を原画像と照合してください。",
          ),
        );
      }
      const actions = node("td");
      if (row.phase === "ready")
        actions.append(button("確認する", () => open(row)));
      if (row.phase === "error")
        actions.append(
          button("この行を再試行", async () => {
            row.phase = "queued";
            await process([row]);
          }),
        );
      for (const role of ["problem", "solution"]) {
        const label = node(
          "label",
          role === "problem"
            ? "問題を差し替え"
            : row.sources.solution
              ? "解答を差し替え"
              : "解答を追加",
          "batch-file-button",
        );
        const input = node("input");
        input.type = "file";
        input.accept = ".png,.jpg,.jpeg,.pdf";
        input.disabled = disabled;
        input.setAttribute(
          "aria-label",
          `${index + 1}件目の${role === "problem" ? "問題を差し替え" : "解答を選択"}`,
        );
        input.onchange = guard(async () => {
          if (input.files[0]) await replace(row, role, input.files[0]);
        });
        label.append(input);
        actions.append(label);
      }
      actions.append(
        button("一覧から除く", () =>
          exclusive(async () => {
            if (
              !(await deps.confirm(
                "この行を一覧から除きますか？",
                "この行の未保存の修正は失われます。原本ファイルは変更しません。",
              ))
            )
              return;
            await closeRow(row);
            rows = rows.filter((r) => r !== row);
            unsaved = true;
          }),
        ),
      );
      tr.append(identity, state, details, actions);
      body.append(tr);
    });
    $("batch-empty").hidden = body.childElementCount > 0;
  }
  async function open(row) {
    if (running || locked || uiBusy) return;
    locked = true;
    render();
    try {
      if (!(await flush())) return;
      const next = await deps.api("state", { id: row.id });
      active = row;
      await deps.display({ ...next, sources: row.sources });
    } finally {
      locked = false;
      render();
    }
  }
  async function process(targets = rows.filter((r) => r.phase === "queued")) {
    if (running || locked || uiBusy) return;
    running = true;
    stop = false;
    for (const row of targets) {
      if (stop) break;
      row.phase = "reading";
      row.error = "";
      render();
      try {
        const next = await deps.api(
          "batch-item",
          row.project
            ? { project: row.project }
            : { sources: row.sources, uniqueRequired: row.uniqueRequired },
        );
        Object.assign(row, {
          id: next.id,
          revision: next.revision,
          sources: next.sources,
          result: brief(next.result),
          digest: next.digest,
          phase: "ready",
          project: null,
        });
      } catch (error) {
        row.phase = "error";
        row.error = error.message;
        row.errorCode = error.code || "CONNECTION_FAILED";
        row.result = null;
      }
      unsaved = true;
    }
    running = false;
    render();
  }
  async function fromFile(file, page = 1) {
    const result = { name: file.name, data: await deps.readFile(file) };
    if (isPDF(result)) result.page = page;
    return result;
  }
  async function replace(row, role, file) {
    return exclusive(async () => {
      const source = await fromFile(file);
      const sources = { ...row.sources, [role]: source };
      checkSources(
        rows.map((r) => ({ sources: r === row ? sources : r.sources })),
      );
      if (
        !(await deps.confirm(
          "この行の画像を置き換えますか？",
          "この行の修正と承認を取り消します。PDFを差し替えると1ページ目を使います。別ページは新しい一括検品の投入画面で指定してください。",
        ))
      )
        return;
      await closeRow(row);
      Object.assign(row, {
        sources,
        project: null,
        phase: "queued",
        result: null,
        error: "",
        dirty: false,
      });
      unsaved = true;
    });
  }
  function renderDraft() {
    const body = $("batch-draft-rows");
    body.replaceChildren();
    draft.forEach((entry, i) => {
      const tr = node("tr");
      tr.append(node("td", `${i + 1}. ${entry.problem.name}`));
      const pageField = (key, enabled, label) => {
        const cell = node("td"),
          input = node("input");
        input.type = "number";
        input.min = 1;
        input.max = 20;
        input.value = entry[key];
        input.disabled = !enabled;
        input.setAttribute("aria-label", `${i + 1}件目の${label}`);
        input.onchange = () => {
          entry[key] = Number(input.value);
        };
        cell.append(input);
        return cell;
      };
      tr.append(pageField("problemPage", isPDF(entry.problem), "問題ページ"));
      const cell = node("td"),
        select = node("select");
      select.setAttribute("aria-label", `${i + 1}件目の解答画像`);
      const none = node("option", "解答なし");
      none.value = "-1";
      select.append(none);
      solutions.forEach((file, j) => {
        const opt = node("option", `${j + 1}. ${file.name}`);
        opt.value = j;
        select.append(opt);
      });
      select.value = entry.solution;
      select.onchange = () => {
        entry.solution = Number(select.value);
        renderDraft();
      };
      cell.append(select);
      tr.append(cell);
      tr.append(
        pageField(
          "solutionPage",
          entry.solution >= 0 && isPDF(solutions[entry.solution]),
          "解答ページ",
        ),
      );
      const actions = node("td");
      actions.append(
        button("行を複製", () => {
          if (draft.length >= MAX_ITEMS) throw new Error("最大100件です。");
          draft.splice(i + 1, 0, { ...entry });
          renderDraft();
        }),
        button("除く", () => {
          draft.splice(i, 1);
          renderDraft();
        }),
      );
      tr.append(actions);
      body.append(tr);
    });
    $("batch-run-new").disabled = !draft.length || preparing;
    $("batch-draft-count").textContent =
      `${draft.length} 件 · 解答あり ${draft.filter((r) => r.solution >= 0).length} 件`;
  }
  $("batch-start").onclick = () => {
    $("welcome").hidden = true;
    $("batch-setup").hidden = false;
    renderDraft();
  };
  $("batch-problems").onchange = guard(() => {
    const files = [...$("batch-problems").files];
    $("batch-problems").value = "";
    if (files.length + draft.length > MAX_ITEMS)
      throw new Error("最大100件です。件数を分けてください。");
    draft.push(
      ...files.map((problem) => ({
        problem,
        problemPage: 1,
        solution: -1,
        solutionPage: 1,
      })),
    );
    renderDraft();
  });
  $("batch-solutions").onchange = guard(() => {
    const files = [...$("batch-solutions").files];
    $("batch-solutions").value = "";
    if (solutions.length + files.length > MAX_ITEMS)
      throw new Error("解答ファイルも最大100個です。");
    solutions.push(...files);
    renderDraft();
  });
  $("batch-run-new").onclick = guard(async () => {
    if (preparing || !draft.length) return;
    preparing = true;
    $("batch-setup").inert = true;
    $("reset").disabled = true;
    try {
      const total = draft.reduce(
        (n, r) => n + r.problem.size + (solutions[r.solution]?.size || 0),
        0,
      );
      if (total > MAX_SOURCE_BYTES)
        throw new Error(
          "原画像の合計が32MiBを超えます。件数を分けてください。",
        );
      const prepared = [];
      for (const entry of draft) {
        for (const [file, page] of [
          [entry.problem, entry.problemPage],
          [solutions[entry.solution], entry.solutionPage],
        ]) {
          if (
            file &&
            isPDF(file) &&
            (!Number.isInteger(page) || page < 1 || page > 20)
          )
            throw new Error("PDFのページは1〜20の整数で指定してください。");
        }
        const sources = {
          problem: await fromFile(entry.problem, entry.problemPage),
        };
        if (entry.solution >= 0)
          sources.solution = await fromFile(
            solutions[entry.solution],
            entry.solutionPage,
          );
        prepared.push({ sources });
      }
      checkSources(prepared);
      await release();
      rows = prepared.map(makeRow);
      draft = [];
      solutions = [];
      unsaved = true;
      showList();
    } finally {
      preparing = false;
      $("batch-setup").inert = false;
      $("reset").disabled = false;
    }
    await process();
  });
  $("batch-setup-back").onclick = guard(async () => {
    if (
      draft.length &&
      !(await deps.confirm(
        "トップへ戻りますか？",
        "選択した組み合わせは取り消されます。原本ファイルは変更しません。",
      ))
    )
      return;
    draft = [];
    solutions = [];
    $("batch-setup").hidden = true;
    $("welcome").hidden = false;
  });
  $("batch-resume").onclick = guard(() => process());
  $("batch-pause").onclick = () => {
    stop = true;
    render();
  };
  $("batch-retry").onclick = guard(async () => {
    const targets = rows.filter((r) => r.phase === "error");
    targets.forEach((r) => {
      r.phase = "queued";
    });
    await process(targets);
  });
  $("batch-filter").onchange = render;
  $("batch-back").onclick = guard(async () => {
    if (await flush()) showList();
  });
  $("batch-next").onclick = guard(async () => {
    if (!(await flush())) return;
    const start = rows.indexOf(active);
    const ordered = [...rows.slice(start + 1), ...rows.slice(0, start)];
    const next = ordered.find(
      (r) => r.phase === "ready" && r.result?.assurance !== "human_confirmed",
    );
    if (next) await open(next);
    else {
      showList();
      deps.message(
        "ほかに読み込み済みの確認待ちはありません。一覧でエラー・未処理も確認してください。",
      );
    }
  });
  async function collect() {
    if (!(await flush()))
      throw new Error(
        "現在の修正を同期できませんでした。表示された理由を確認してください。",
      );
    locked = true;
    render();
    try {
      const items = [];
      for (const row of rows) {
        let project = row.project;
        if (row.id) {
          const exported = await deps.api("export", {
            id: row.id,
            revision: row.revision,
          });
          project = exported.project;
        }
        // Each saved row must also fit its own restore request, including rows
        // loaded from an older bundle that have not been reprocessed yet.
        if (project) projectBlob(project);
        items.push({
          id: row.key,
          ...(project
            ? { project }
            : { sources: row.sources, uniqueRequired: row.uniqueRequired }),
        });
      }
      return items;
    } finally {
      locked = false;
      render();
    }
  }
  $("batch-save").onclick = guard(async () => {
    const items = await collect();
    const document = {
      schemaVersion: VERSION,
      items,
      notice:
        "Reopening rechecks all images and requires fresh human approval.",
    };
    const blob = new Blob([JSON.stringify(document)], {
      type: "application/json",
    });
    if (blob.size > MAX_BUNDLE_BYTES)
      throw new Error(
        "一括作業が128MiBを超えます。個別の「作業を保存」を使い、件数を分けてください。",
      );
    deps.download("mazeproof-batch.mazeproof-batch", blob);
    unsaved = false;
    deps.message("一括作業をダウンロードしました。保存先を確認してください。");
  });
  async function report(html) {
    const items = await collect();
    const report = {
      schemaVersion: "mazeproof.batch-report/1",
      counts: counts(),
      notice:
        "Each result applies only to its reviewed model. Pending items and unchecked scope are not passes.",
      items: items.map((item, i) => ({
        id: item.id,
        problem: rows[i].sources.problem.name,
        solution: rows[i].sources.solution?.name || null,
        state: rows[i].phase,
        status: status(rows[i]),
        // A restored but not reprocessed project's old result is untrusted.
        result: rows[i].phase === "ready" ? item.project.result : null,
        error: rows[i].phase === "error" ? rows[i].errorCode : null,
      })),
    };
    if (!html) {
      deps.download("mazeproof-batch-report.json", report);
      return;
    }
    const esc = deps.escape;
    const body = report.items
      .map(
        (item) =>
          `<tr><th>${esc(item.problem)}</th><td>${esc(item.solution || "なし")}</td><td>${esc(item.status)}</td><td>${esc(
            item.result
              ? Object.entries(item.result.checks)
                  .map(
                    ([k, v]) =>
                      `${deps.labels[k]}: ${v.status}${item.result.recognition?.assurance !== "human_confirmed" && v.status !== "NOT_RUN" ? "（暫定）" : ""}`,
                  )
                  .join(" / ")
              : item.error || "未処理",
          )}</td></tr>`,
      )
      .join("");
    deps.download(
      "mazeproof-batch-report.html",
      `<!doctype html><html lang="ja"><meta charset="utf-8"><title>MazeProof 一括検品レポート</title><style>body{font:15px system-ui;max-width:1100px;margin:40px auto;padding:20px;color:#243d3a}table{border-collapse:collapse;width:100%}th,td{padding:12px;text-align:left;border:1px solid #ddd;overflow-wrap:anywhere}pre{white-space:pre-wrap;overflow-wrap:anywhere}</style><h1>一括検品の記録</h1><p>条件付き PASS は人が承認したモデルに対する結果です。確認待ち・未処理・未検査は合格ではありません。</p><p>${esc($("batch-counts").textContent)}</p><table><thead><tr><th>問題</th><th>解答</th><th>状態</th><th>検査項目</th></tr></thead><tbody>${body}</tbody></table><details><summary>判定の詳細・未検査の範囲</summary><pre>${esc(JSON.stringify(report, null, 2))}</pre></details></html>`,
      "text/html",
    );
  }
  $("batch-report-json").onclick = guard(() => report(false));
  $("batch-report-html").onclick = guard(() => report(true));
  $("batch-project-file").onchange = guard(async () => {
    const file = $("batch-project-file").files[0];
    $("batch-project-file").value = "";
    if (!file) return;
    if (file.size > MAX_BUNDLE_BYTES)
      throw new Error("一括作業は128MiB以下にしてください。");
    const saved = JSON.parse(await file.text());
    if (saved?.schemaVersion !== VERSION || !Array.isArray(saved.items))
      throw new Error("対応する一括作業ファイルではありません。");
    const prepared = saved.items.map((item) => {
      if (
        !item ||
        typeof item !== "object" ||
        Boolean(item.project) === Boolean(item.sources)
      )
        throw new Error("一括作業の項目が不正です。");
      if (
        item.uniqueRequired !== undefined &&
        typeof item.uniqueRequired !== "boolean"
      )
        throw new Error("一括作業の検証方針が不正です。");
      return {
        project: item.project || null,
        sources: item.project?.sources || item.sources,
        uniqueRequired: item.uniqueRequired,
      };
    });
    checkSources(prepared);
    await release();
    rows = prepared.map(makeRow);
    unsaved = true;
    showList();
    deps.message(
      "一括作業を開きました。「未処理を読み込む」で再認識します。保存されていた承認・結果は引き継ぎません。",
    );
  });
  return {
    hasWork: () => rows.length > 0 || draft.length > 0,
    hasUnsaved: () => unsaved || draft.length > 0,
    setBusy(value) {
      uiBusy = value;
      if (rows.length) render();
    },
    changed() {
      if (!active) return;
      active.dirty = true;
      active.result = null;
      unsaved = true;
    },
    updated,
    displayed(next) {
      $("batch-setup").hidden = true;
      $("batch-list").hidden = true;
      $("batch-review-nav").hidden = !active;
      updated(next);
    },
    async reset() {
      if (!rows.length && $("batch-setup").hidden && $("batch-list").hidden)
        return false;
      if (running || preparing || locked || uiBusy) return true;
      if (
        (rows.length || draft.length) &&
        !(await deps.confirm(
          "一括検品を終了しますか？",
          "未保存の一覧と修正は失われます。必要なら先に「一括作業を保存」を使ってください。",
        ))
      )
        return true;
      await release();
      draft = [];
      solutions = [];
      unsaved = false;
      for (const id of [
        "batch-list",
        "batch-setup",
        "workbench",
        "batch-review-nav",
      ])
        $(id).hidden = true;
      $("welcome").hidden = false;
      $("import-form").reset();
      return true;
    },
  };
}
