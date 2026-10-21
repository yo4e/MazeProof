import { samples } from "./samples.js";

const $ = (id) => document.getElementById(id);
const buttons = [...document.querySelectorAll("[data-case]")];
const ids = ["normal", "wall", "gap"];
const state = {
  id: "normal",
  role: "solution",
  overlay: true,
  zoom: false,
  step: 0,
};
const images = new Map();
let ready = false;
const copy = {
  normal: {
    title: "問題のない例",
    description:
      "黒い壁と、上の入口から下の出口まで続く赤い線。左右の画像を見比べて、読み取りと原画像が合っているかを確かめます。",
    look: "① 入口から、赤い線をたどってみる",
    detail:
      "上側の開口が入口です。黒い壁に青緑の線が重なり、赤い線に紫の点線が沿っています。「問題画像」に切り替えると、赤線のない壁も確認できます。",
    result: "この例では、通り道は1通りです",
    summary:
      "用意した壁と解答の構造では、入口から出口へ進めて、赤線の通り道も壁を横切っていません。",
    report:
      "このサンプルの構造では、道のつながり・解答の唯一性・壁を越えない解答・問題と解答の壁の一致を確認できました。画像の読み間違いがないことまで、自動で保証した結果ではありません。",
    help: "本番では、画像全体を見比べたうえで人が確認します。ここでは結果の例へ進みます。",
  },
  wall: {
    title: "壁を確認する例",
    description:
      "説明のため、通路を「壁がある」と読み違えた状態を用意しました。①の場所で、左の原画像と右の青緑の線を比べてください。",
    look: "① 原画像にない壁を、読み取っていませんか？",
    detail:
      "上段の中央、左の原画像には黒い縦壁がありません。右の例には青緑の縦線があり、通路をふさいでいます。拡大すると違いを確認しやすくなります。",
    result: "この読み取りのままでは、出口へ進めません",
    summary:
      "余分な壁が道をふさいでいます。原画像の不備と決めつけず、先に壁の読み取りを直す必要があります。",
    fixedResult: "通路に直した例では、出口へ進めます",
    fixedSummary:
      "用意した修正例では、余分な壁を取り除くと道がつながり、解答も1通りになります。実際の画像では全体の再確認が必要です。",
    report:
      "①の位置で、原画像にない壁が読み取りに含まれていました。修正例では通路に戻すと道がつながりました。実際の検品では、①だけでなく壁・入口・出口・解答線の全体を原画像と照合してください。",
    help: "まず、この読み違いが検査にどう現れるかを見てから、決まった修正例を試します。",
    fixedLook: "① 余分な壁を取り除いた例です",
    fixedDetail:
      "右側の青緑の縦線がなくなり、原画像の通路と一致しました。元の画像は変えず、読み取った壁の情報を修正する操作の例です。",
    correction: "通路に直した例を見る",
  },
  gap: {
    title: "赤線が途切れた例",
    description:
      "この例は、解答画像そのものの赤い線が途切れています。迷路に道があることと、提出された解答がつながることは別々に確認します。",
    look: "① 赤い線が、途中でなくなっています",
    detail:
      "上段の中央で赤い線が途切れています。黒い壁が原因ではありません。「問題画像」へ切り替えると、この場所が通路であることを確認できます。",
    result: "道はありますが、この赤線はつながっていません",
    summary:
      "迷路の道は1通りでも、解答の線には途切れがあります。「迷路が解ける」だけでは、解答画像まで問題ないとは言えません。",
    fixedResult: "線をつないだ修正例では、解答もつながります",
    fixedSummary:
      "用意した修正後の解答画像と構造に切り替えました。この例では赤線がつながり、壁も横切っていません。実際には修正後の解答画像も人が確認します。",
    report:
      "①の位置に赤線の途切れがありました。問題の迷路には道がありますが、修正前の解答は連続していません。修正例では解答画像の線をつないでいます。実際の検品では修正後の原画像を再度見比べてください。",
    help: "「道があるか」と「解答線がつながるか」の結果を見て、用意した修正後の画像へ進みます。",
    fixedLook: "① 線をつないだ解答画像に切り替えました",
    fixedDetail:
      "原画像の側も、用意した修正後の画像になりました。実際の検品でも、提出する解答画像を直したら、もう一度読み込んで確認します。",
    correction: "線をつないだ解答の例を見る",
  },
};

function draw(canvas, overlay) {
  const sample = samples[state.id];
  const variant = state.step === 2 ? sample.after : sample.before;
  const ctx = canvas.getContext("2d");
  const [fx, fy] = sample.focus;
  const side = state.zoom ? 156 : 337;
  const x = state.zoom ? Math.max(0, Math.min(337 - side, fx - side / 2)) : 0;
  const y = state.zoom ? Math.max(0, Math.min(337 - side, fy - side / 2)) : 0;
  ctx.setTransform(1, 0, 0, 1, 0, 0);
  ctx.clearRect(0, 0, canvas.width, canvas.height);
  ctx.scale(canvas.width / side, canvas.height / side);
  ctx.translate(-x, -y);
  ctx.drawImage(images.get(variant[state.role + "Image"]), 0, 0);
  if (overlay && state.overlay) {
    const model = state.role === "problem" ? variant.problem : variant.solution;
    ctx.strokeStyle = "#168b84";
    ctx.lineWidth = 2.5;
    for (const [r, row] of model.horizontalWalls.entries()) {
      for (const [c, wall] of row.entries()) {
        if (wall)
          line(ctx, 24 + c * 72, 24 + r * 72, 24 + (c + 1) * 72, 24 + r * 72);
      }
    }
    for (const [r, row] of model.verticalWalls.entries()) {
      for (const [c, wall] of row.entries()) {
        if (wall)
          line(ctx, 24 + c * 72, 24 + r * 72, 24 + c * 72, 24 + (r + 1) * 72);
      }
    }
    if (state.role === "solution") {
      ctx.strokeStyle = "#684c9d";
      ctx.lineWidth = 2.4;
      ctx.setLineDash([4, 4]);
      for (let i = 1; i < model.route.length; i++) {
        const a = model.route[i - 1];
        const b = model.route[i];
        if (Math.abs(a.row - b.row) + Math.abs(a.col - b.col) === 1) {
          line(
            ctx,
            60 + 72 * a.col,
            60 + 72 * a.row,
            60 + 72 * b.col,
            60 + 72 * b.row,
          );
        }
      }
      ctx.setLineDash([]);
    }
  }
  ctx.strokeStyle = "#a86416";
  ctx.lineWidth = 1.8;
  ctx.fillStyle = "#efb24b15";
  ctx.beginPath();
  ctx.arc(fx, fy, state.id === "normal" ? 15 : 27, 0, Math.PI * 2);
  ctx.fill();
  ctx.stroke();
  ctx.fillStyle = "#a86416";
  ctx.beginPath();
  ctx.arc(fx + 27, fy + 27, 10, 0, Math.PI * 2);
  ctx.fill();
  ctx.fillStyle = "white";
  ctx.font = "bold 12px sans-serif";
  ctx.textAlign = "center";
  ctx.textBaseline = "middle";
  ctx.fillText("1", fx + 27, fy + 27);
}

function line(ctx, x, y, x2, y2) {
  ctx.beginPath();
  ctx.moveTo(x, y);
  ctx.lineTo(x2, y2);
  ctx.stroke();
}

function render() {
  if (!ready) return;
  const text = copy[state.id];
  const fixed = state.step === 2;
  buttons.forEach((button) =>
    button.setAttribute(
      "aria-pressed",
      String(button.dataset.case === state.id),
    ),
  );
  $("problem").setAttribute("aria-pressed", String(state.role === "problem"));
  $("solution").setAttribute("aria-pressed", String(state.role === "solution"));
  $("overlay").checked = state.overlay;
  $("zoom").setAttribute("aria-pressed", String(state.zoom));
  $("zoom").textContent = state.zoom ? "全体に戻す" : "注目箇所を拡大";
  $("case-title").textContent = text.title;
  $("case-description").textContent = text.description;
  $("look-title").textContent = fixed ? text.fixedLook : text.look;
  $("look-description").textContent = fixed ? text.fixedDetail : text.detail;
  $("source-label").textContent =
    state.role === "problem"
      ? "合成した問題画像"
      : fixed && state.id === "gap"
        ? "用意した修正後の画像"
        : "合成した解答画像";
  $("overlay-label").textContent = state.overlay
    ? fixed
      ? "修正例を重ねて表示"
      : "色を重ねて照合"
    : "重ね表示はオフ";
  $("action-help").textContent =
    state.step === 0
      ? text.help
      : state.step === 1 && state.id !== "normal"
        ? "次は、決められた箇所だけを直した例に切り替えます。自由な編集や新しい検査は行いません。"
        : "別の例も試せます。「最初から」で、この例の修正前に戻せます。";
  $("advance").textContent =
    state.step === 0
      ? "この例の結果を見る →"
      : state.step === 1 && state.id !== "normal"
        ? text.correction + " →"
        : "次の例を試す →";
  $("result").hidden = state.step === 0;
  if (state.step > 0) renderResult(text, fixed);
  draw($("original"), false);
  draw($("recognized"), true);
  for (const id of ["original", "recognized"]) {
    $(id).setAttribute(
      "aria-label",
      `${text.title}の${state.role === "problem" ? "問題" : "解答"}画像。${id === "recognized" ? "読み取りを比較する側。" : "原画像の側。"}${fixed ? text.fixedDetail : text.detail}`,
    );
  }
}

function renderResult(text, fixed) {
  const variant = fixed ? samples[state.id].after : samples[state.id].before;
  $("result-title").textContent = fixed ? text.fixedResult : text.result;
  $("result-description").textContent = fixed
    ? text.fixedSummary
    : text.summary;
  const names = {
    reachability: ["入口から出口へ", "道がつながる", "道がつながらない"],
    uniqueness: ["解答の通り道", "1通り", "道がなく、確認できない"],
    routeValidity: [
      "赤い解答線",
      "つながり、壁を越えない",
      state.id === "gap" ? "途中で途切れている" : "読み取った壁を越えている",
    ],
    mazeIdentity: ["問題と解答の壁", "一致する", "一致しない"],
  };
  $("checks").replaceChildren();
  for (const [name, labels] of Object.entries(names)) {
    const pass = variant.checks[name].status === "PASS";
    const row = document.createElement("div");
    if (!pass) row.className = "failed";
    const label = document.createElement("dt");
    label.textContent = labels[0];
    const value = document.createElement("dd");
    value.textContent = labels[pass ? 1 : 2];
    row.append(label, value);
    $("checks").append(row);
  }
  $("report-text").textContent = text.report;
}

function select(id) {
  state.id = id;
  state.role = "solution";
  state.overlay = true;
  state.zoom = false;
  state.step = 0;
  $("report").hidden = true;
  $("report-button").setAttribute("aria-expanded", "false");
  render();
  $("announcement").textContent = copy[id].title + "を最初から表示しました。";
}

buttons.forEach((button) =>
  button.addEventListener("click", () => select(button.dataset.case)),
);
$("reset").addEventListener("click", () => select(state.id));
for (const role of ["problem", "solution"])
  $(role).addEventListener("click", () => {
    state.role = role;
    render();
  });
$("overlay").addEventListener("change", () => {
  state.overlay = $("overlay").checked;
  render();
});
$("zoom").addEventListener("click", () => {
  state.zoom = !state.zoom;
  render();
});
$("advance").addEventListener("click", () => {
  if (state.step === 2 || (state.step === 1 && state.id === "normal")) {
    select(ids[(ids.indexOf(state.id) + 1) % ids.length]);
    $("case-title").scrollIntoView({ block: "center" });
  } else {
    state.step++;
    if (state.step === 2) state.role = "solution";
    $("report").hidden = true;
    $("report-button").setAttribute("aria-expanded", "false");
    render();
    $("result-title").focus({ preventScroll: true });
    $("announcement").textContent = $("result-title").textContent;
  }
});
$("report-button").addEventListener("click", () => {
  $("report").hidden = !$("report").hidden;
  $("report-button").setAttribute("aria-expanded", String(!$("report").hidden));
});

document.querySelectorAll("button,input").forEach((element) => {
  element.disabled = true;
});
try {
  const paths = new Set(
    Object.values(samples).flatMap((sample) =>
      [sample.before, sample.after].flatMap((variant) => [
        variant.problemImage,
        variant.solutionImage,
      ]),
    ),
  );
  await Promise.all(
    [...paths].map(
      (path) =>
        new Promise((resolve, reject) => {
          const img = new Image();
          img.onload = () => {
            images.set(path, img);
            resolve();
          };
          img.onerror = () =>
            reject(new Error("サンプル画像を読み込めませんでした。"));
          img.src = path;
        }),
    ),
  );
  ready = true;
  render();
  document.querySelectorAll("button,input").forEach((element) => {
    element.disabled = false;
  });
  document.body.dataset.ready = "true";
} catch {
  $("case-description").textContent =
    "サンプルを読み込めませんでした。接続を確認して、このページを再読み込みしてください。ローカル版の案内は下のリンクから開けます。";
  $("case-description").setAttribute("role", "alert");
}
