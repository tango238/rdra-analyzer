"""
RDRA モデル インタラクティブビューア HTML テンプレート生成

単一の自己完結型 HTML ファイルを生成し、ブラウザで RDRA モデルを
対話的に閲覧できるようにする。
"""


def generate_viewer_html(
    project_name: str,
    generated_at: str,
    data_json: str,
    mermaid_sources: str,
) -> str:
    """RDRA モデルのインタラクティブビューア HTML を生成する。

    Args:
        project_name: プロジェクト名
        generated_at: 生成日時文字列
        data_json: RDRA データの JSON 文字列
        mermaid_sources: Mermaid ソースコードの JSON 文字列 ({view_name: source})

    Returns:
        完全な HTML 文字列
    """
    # Escape for safe embedding inside <script> tags
    safe_data = data_json.replace("</", "<\\/")
    safe_mermaid = mermaid_sources.replace("</", "<\\/")

    return f"""<!DOCTYPE html>
<html lang="ja">
<head>
<meta charset="UTF-8">
<title>{project_name} - RDRA モデルビューア</title>
<script src="https://cdn.jsdelivr.net/npm/mermaid@10/dist/mermaid.min.js"></script>
<style>
*,*::before,*::after{{box-sizing:border-box;margin:0;padding:0}}
:root{{
  --sidebar-w:260px;--detail-w:400px;
  --bg-sidebar:#1a1a2e;--bg-main:#f5f6fa;--bg-card:#fff;
  --accent:#4361ee;--accent-light:#eef1ff;
  --high:#e63946;--medium:#f4a261;--low:#2a9d8f;
  --text:#222;--text-muted:#666;--border:#dde;
}}
html,body{{height:100%;font-family:-apple-system,BlinkMacSystemFont,"Segoe UI","Noto Sans JP",sans-serif;color:var(--text);background:var(--bg-main)}}

/* ---------- grid layout ---------- */
#app{{display:grid;grid-template-columns:var(--sidebar-w) 1fr;grid-template-rows:52px 1fr;height:100vh;overflow:hidden}}
#sidebar{{grid-row:1/3;background:var(--bg-sidebar);color:#ccd;overflow-y:auto;padding:0}}
#topbar{{grid-column:2;display:flex;align-items:center;gap:12px;padding:0 24px;background:var(--bg-card);border-bottom:1px solid var(--border);position:relative}}
#main{{grid-column:2;overflow-y:auto;padding:28px 32px}}

/* ---------- sidebar ---------- */
.sb-header{{padding:20px 18px 14px;border-bottom:1px solid rgba(255,255,255,.08)}}
.sb-header h1{{font-size:15px;color:#fff;font-weight:600;margin-bottom:4px}}
.sb-header small{{font-size:11px;color:#889}}
.sb-stats{{display:grid;grid-template-columns:1fr 1fr;gap:6px;padding:14px 18px;border-bottom:1px solid rgba(255,255,255,.08)}}
.sb-stat{{background:rgba(255,255,255,.05);border-radius:6px;padding:8px 10px;text-align:center}}
.sb-stat .num{{font-size:20px;font-weight:700;color:#fff}}
.sb-stat .lbl{{font-size:10px;color:#889;margin-top:2px}}
.sb-nav{{list-style:none;padding:10px 0}}
.sb-nav li{{cursor:pointer;padding:9px 18px;font-size:13px;color:#aab;transition:background .15s}}
.sb-nav li:hover{{background:rgba(255,255,255,.06)}}
.sb-nav li.active{{background:var(--accent);color:#fff;font-weight:600}}

/* ---------- topbar search ---------- */
#search-input{{flex:1;max-width:420px;padding:7px 12px;border:1px solid var(--border);border-radius:6px;font-size:13px;outline:none}}
#search-input:focus{{border-color:var(--accent)}}
#search-results{{position:absolute;top:48px;left:24px;width:420px;background:var(--bg-card);border:1px solid var(--border);border-radius:8px;box-shadow:0 8px 24px rgba(0,0,0,.12);display:none;max-height:320px;overflow-y:auto;z-index:100}}
#search-results .sr-item{{padding:10px 14px;cursor:pointer;font-size:13px;border-bottom:1px solid var(--border)}}
#search-results .sr-item:hover{{background:var(--accent-light)}}
.sr-tag{{display:inline-block;font-size:10px;padding:1px 6px;border-radius:4px;margin-right:6px;font-weight:600;color:#fff}}

/* ---------- main content ---------- */
.view-section{{display:none}}
.view-section.active{{display:block}}
.view-title{{font-size:20px;font-weight:700;margin-bottom:18px}}
.diagram-wrap{{background:var(--bg-card);border:1px solid var(--border);border-radius:10px;padding:20px;margin-bottom:24px;overflow:hidden;max-height:70vh;position:relative;cursor:grab}}
.diagram-wrap.dragging{{cursor:grabbing}}
.diagram-wrap .diagram-inner{{transform-origin:0 0;transition:transform 0.1s ease}}
.diagram-wrap svg{{max-width:none}}
.zoom-controls{{position:absolute;top:8px;right:8px;display:flex;gap:4px;z-index:10}}
.zoom-btn{{width:32px;height:32px;border:1px solid var(--border);border-radius:6px;background:var(--bg-card);cursor:pointer;font-size:16px;display:flex;align-items:center;justify-content:center;opacity:0.8}}
.zoom-btn:hover{{opacity:1;background:#f0f0f0}}

/* tables */
.data-table{{width:100%;border-collapse:collapse;font-size:13px;background:var(--bg-card);border-radius:8px;overflow:hidden;border:1px solid var(--border)}}
.data-table th{{background:#f0f1f5;text-align:left;padding:10px 12px;cursor:pointer;user-select:none;white-space:nowrap;font-weight:600;font-size:12px}}
.data-table th:hover{{background:#e4e6ee}}
.data-table th .sort-arrow{{margin-left:4px;color:#aaa;font-size:10px}}
.data-table td{{padding:9px 12px;border-top:1px solid var(--border)}}
.data-table tr:hover td{{background:var(--accent-light)}}
.clickable{{color:var(--accent);cursor:pointer;font-weight:500}}
.clickable:hover{{text-decoration:underline}}

/* priority badges */
.badge{{display:inline-block;padding:2px 8px;border-radius:4px;font-size:11px;font-weight:600;color:#fff}}
.badge-high{{background:var(--high)}}.badge-medium{{background:var(--medium)}}.badge-low{{background:var(--low)}}.badge-must{{background:var(--high)}}.badge-should{{background:var(--medium)}}.badge-could{{background:var(--low)}}

/* tabs / selectors */
.tab-bar{{display:flex;gap:4px;margin-bottom:16px;flex-wrap:wrap}}
.tab-btn{{padding:6px 14px;border:1px solid var(--border);border-radius:6px;background:var(--bg-card);cursor:pointer;font-size:12px}}
.tab-btn.active{{background:var(--accent);color:#fff;border-color:var(--accent)}}
select.view-select{{padding:6px 10px;border:1px solid var(--border);border-radius:6px;font-size:13px;margin-bottom:14px}}

/* detail panel */
#detail-panel{{position:fixed;top:0;right:-440px;width:var(--detail-w);height:100vh;background:var(--bg-card);border-left:1px solid var(--border);box-shadow:-4px 0 24px rgba(0,0,0,.08);transition:right .25s ease, width .25s ease;z-index:200;overflow-y:auto;padding:24px}}
#detail-panel.open{{right:0}}
#detail-panel.wide{{width:70vw;right:-70vw}}
#detail-panel.wide.open{{right:0}}
#detail-panel .scenario-diagram-wrap{{background:var(--bg-main);border:1px solid var(--border);border-radius:10px;padding:20px;margin:16px 0;overflow:hidden;min-height:200px;position:relative;cursor:grab}}
#detail-panel .scenario-diagram-wrap.dragging{{cursor:grabbing}}
#detail-panel .scenario-diagram-wrap .diagram-inner{{transform-origin:0 0;transition:transform 0.1s ease}}
#detail-panel .scenario-diagram-wrap svg{{max-width:none}}
#detail-close{{position:absolute;top:14px;right:14px;width:28px;height:28px;border:none;background:none;font-size:18px;cursor:pointer;color:var(--text-muted);border-radius:4px}}
#detail-close:hover{{background:#eee}}
.detail-title{{font-size:17px;font-weight:700;margin-bottom:16px;padding-right:32px}}
.detail-section{{margin-bottom:16px}}
.detail-section h4{{font-size:12px;color:var(--text-muted);text-transform:uppercase;margin-bottom:6px;letter-spacing:.3px}}
.detail-list{{list-style:none}}
.detail-list li{{padding:4px 0;font-size:13px;border-bottom:1px solid #f0f0f0}}

/* cross-reference matrix */
.matrix-wrap{{overflow:auto;max-height:70vh}}
.matrix-table{{border-collapse:collapse;font-size:12px}}
.matrix-table th,.matrix-table td{{border:1px solid var(--border);padding:6px 8px;text-align:center;min-width:36px}}
.matrix-table th{{background:#f0f1f5;position:sticky;top:0;z-index:2}}
.matrix-table th.row-head{{text-align:left;position:sticky;left:0;z-index:3;background:#f0f1f5}}
.matrix-table td.row-head{{text-align:left;position:sticky;left:0;background:var(--bg-card);font-weight:500;z-index:1}}
.matrix-table .check{{color:var(--accent);font-weight:700}}
</style>
</head>
<body>
<div id="app">

<!-- Sidebar -->
<aside id="sidebar">
  <div class="sb-header">
    <h1 id="proj-name"></h1>
    <small id="gen-date"></small>
  </div>
  <div class="sb-stats" id="stats-grid"></div>
  <ul class="sb-nav" id="nav-list"></ul>
</aside>

<!-- Top bar -->
<header id="topbar">
  <input id="search-input" type="text" placeholder="エンティティ・ユースケースを検索...">
  <div id="search-results"></div>
</header>

<!-- Main -->
<main id="main"></main>

</div>

<!-- Detail panel -->
<div id="detail-panel">
  <button id="detail-close">&times;</button>
  <div id="detail-content"></div>
</div>

<script>
// ===== Data =====
const DATA = {safe_data};
const MERMAID_SRC = {safe_mermaid};
const PROJECT_NAME = {_js_str(project_name)};
const GENERATED_AT = {_js_str(generated_at)};

// ===== Nav config =====
const VIEWS = [
  {{key:"info_grouped",  label:"情報モデル概要",   diagram:"information_model_grouped"}},
  {{key:"info_detail",   label:"情報モデル詳細",   diagram:"information_model"}},
  {{key:"uc_diagram",    label:"ユースケース複合図",diagram:"usecase_diagram"}},
  {{key:"uc_conditions", label:"ユースケース条件図",diagram:"usecase_conditions"}},
  {{key:"scenarios",     label:"操作シナリオ",     diagram:null}},
  {{key:"states",        label:"状態遷移図",       diagram:null}},
  {{key:"policies",      label:"ビジネスポリシー", diagram:null}},
  {{key:"screens",        label:"画面",             diagram:null}},
  {{key:"actors",         label:"アクター",         diagram:null}},
  {{key:"business",      label:"業務",             diagram:null}},
  {{key:"actor_uc",      label:"アクター×UC",     diagram:null}},
  {{key:"cross_ref",     label:"エンティティ×UC",  diagram:null}},
];

let currentView = null;
const renderedDiagrams = new Set();

// ===== Init =====
document.addEventListener("DOMContentLoaded", () => {{
  mermaid.initialize({{ startOnLoad:false, theme:"default", securityLevel:"loose" }});
  renderSidebar();
  buildSections();
  navigate(VIEWS[0].key);
  initSearch();
  document.getElementById("detail-close").onclick = () => {{ const p = document.getElementById("detail-panel"); p.classList.remove("open"); p.classList.remove("wide"); }};
}});

// ===== Sidebar =====
function renderSidebar() {{
  document.getElementById("proj-name").textContent = PROJECT_NAME;
  document.getElementById("gen-date").textContent = GENERATED_AT;
  const stats = [
    {{n:(DATA.entities||[]).length, l:"エンティティ"}},
    {{n:(DATA.usecases||[]).length, l:"ユースケース"}},
    {{n:(DATA.scenarios||[]).length, l:"シナリオ"}},
    {{n:(DATA.policies||[]).length, l:"ポリシー"}},
  ];
  document.getElementById("stats-grid").innerHTML = stats.map(s => `<div class="sb-stat"><div class="num">${{s.n}}</div><div class="lbl">${{s.l}}</div></div>`).join("");
  const nav = document.getElementById("nav-list");
  nav.innerHTML = VIEWS.map(v => `<li data-view="${{v.key}}">${{v.label}}</li>`).join("");
  nav.addEventListener("click", e => {{
    const li = e.target.closest("li[data-view]");
    if(li) navigate(li.dataset.view);
  }});
}}

// ===== Build sections =====
function buildSections() {{
  const main = document.getElementById("main");
  VIEWS.forEach(v => {{
    const sec = document.createElement("section");
    sec.className = "view-section";
    sec.id = "view-" + v.key;
    sec.innerHTML = buildViewContent(v);
    main.appendChild(sec);
  }});
}}

function buildViewContent(v) {{
  let html = `<div class="view-title">${{v.label}}</div>`;
  // Diagram-only views (uc_conditions は個別表示するので除外)
  if (v.diagram && v.key !== "uc_conditions") {{
    html += `<div class="diagram-wrap" id="dg-${{v.key}}"></div>`;
  }}
  // Per-view extras
  switch(v.key) {{
    case "info_grouped":
    case "info_detail":
      html += entityTable();
      break;
    case "uc_diagram":
      html += usecaseTable();
      break;
    case "uc_conditions":
      html += ucConditionsTable();
      break;
    case "scenarios":
      html += scenarioTable();
      break;
    case "states":
      html += `<div class="tab-bar" id="state-tabs"></div>`;
      html += `<div class="diagram-wrap" id="dg-state"></div>`;
      html += stateTable();
      break;
    case "policies":
      html += policyTable();
      break;
    case "screens":
      html += screenTable();
      break;
    case "actors":
      html += actorTable();
      break;
    case "business":
      html += `<div class="matrix-wrap" id="business-view"></div>`;
      break;
    case "actor_uc":
      html += `<div class="matrix-wrap" id="actor-uc-matrix"></div>`;
      break;
    case "cross_ref":
      html += `<div class="matrix-wrap" id="cross-matrix"></div>`;
      break;
  }}
  return html;
}}

// ===== Table builders =====
function entityTable() {{
  const rows = (DATA.entities||[]).map(e =>
    `<tr><td class="clickable" data-entity="${{e.class_name}}">${{e.name}}</td><td>${{e.class_name}}</td><td>${{e.table_name||""}}</td><td>${{(e.attributes||[]).length}}</td><td>${{e.description||""}}</td></tr>`
  ).join("");
  return sortableTable("entity-tbl",["エンティティ名","クラス名","テーブル名","属性数","説明"],rows);
}}
function usecaseTable() {{
  const rows = (DATA.usecases||[]).map(u =>
    `<tr><td class="clickable" data-uc="${{u.id}}">${{u.id}}</td><td>${{u.name}}</td><td>${{u.actor}}</td><td>${{u.category||""}}</td><td>${{priorityBadge(u.priority)}}</td></tr>`
  ).join("");
  return sortableTable("uc-tbl",["ID","名称","アクター","カテゴリ","優先度"],rows);
}}
function ucConditionsTable() {{
  const rows = (DATA.usecases||[]).map(u =>
    `<tr><td class="clickable" data-uc-condition="${{u.id}}" style="cursor:pointer;color:var(--accent)">${{u.id}}</td><td>${{u.name}}</td><td>${{u.actor}}</td><td>${{(u.preconditions||[]).length}}</td><td>${{(u.postconditions||[]).length}}</td><td>${{(u.related_entities||[]).length}}</td></tr>`
  ).join("");
  return sortableTable("uccond-tbl",["ID","名称","アクター","事前条件数","事後条件数","エンティティ数"],rows);
}}
function screenTable() {{
  const screens = DATA.screen_specs||[];
  if(!screens.length) return `<p style="color:var(--text-muted)">画面データがありません。<code>python main.py screens</code> を実行してください。</p>`;
  const rows = screens.map(s =>
    `<tr><td class="clickable" data-screen="${{s.route_path}}" style="cursor:pointer;color:var(--accent)">${{s.route_path}}</td><td>${{s.component_name}}</td><td>${{s.page_title||""}}</td><td>${{s.layout_type||""}}</td><td>${{(s.action_buttons||[]).length}}</td><td>${{(s.form_fields||[]).length}}</td></tr>`
  ).join("");
  return sortableTable("screen-tbl",["ルート","コンポーネント","タイトル","レイアウト","ボタン数","フィールド数"],rows);
}}
function actorTable() {{
  const actorMap = {{}};
  (DATA.usecases||[]).forEach(u => {{
    if(!actorMap[u.actor]) actorMap[u.actor] = {{usecases:[], categories:new Set(), entities:new Set()}};
    actorMap[u.actor].usecases.push(u);
    if(u.category) actorMap[u.actor].categories.add(u.category);
    (u.related_entities||[]).forEach(e => actorMap[u.actor].entities.add(e));
  }});
  const rows = Object.entries(actorMap).map(([actor, info]) =>
    `<tr><td class="clickable" data-actor="${{actor}}" style="cursor:pointer;color:var(--accent)">${{actor}}</td><td>${{info.usecases.length}}</td><td>${{[...info.categories].join(", ")}}</td><td>${{info.entities.size}}</td></tr>`
  ).join("");
  return sortableTable("actor-tbl",["アクター名","UC数","カテゴリ","関連エンティティ数"],rows);
}}
function scenarioTable() {{
  const rows = (DATA.scenarios||[]).map(s =>
    `<tr><td class="clickable" data-uc="${{s.usecase_id}}">${{s.usecase_id}}</td><td class="clickable" data-scenario="${{s.scenario_id}}" style="cursor:pointer;color:var(--accent)">${{s.scenario_id}}</td><td>${{s.scenario_name}}</td><td>${{s.scenario_type}}</td><td>${{(s.steps||[]).length}}</td></tr>`
  ).join("");
  return sortableTable("sc-tbl",["UC-ID","シナリオID","名称","種別","ステップ数"],rows);
}}
function stateTable() {{
  const rows = (DATA.state_machines||[]).map(sm =>
    `<tr><td class="clickable" data-entity="${{sm.entity_class}}">${{sm.entity_name}}</td><td>${{sm.state_field}}</td><td>${{(sm.states||[]).length}}</td><td>${{(sm.transitions||[]).length}}</td></tr>`
  ).join("");
  return sortableTable("sm-tbl",["エンティティ","状態フィールド","状態数","遷移数"],rows);
}}
function policyTable() {{
  const rows = (DATA.policies||[]).map(p =>
    `<tr><td class="clickable" data-policy="${{p.id}}" style="cursor:pointer;color:var(--accent)">${{p.id}}</td><td>${{p.name}}</td><td>${{p.category||""}}</td><td>${{priorityBadge(p.severity)}}</td><td>${{p.description||""}}</td></tr>`
  ).join("");
  return sortableTable("bp-tbl",["ID","名称","カテゴリ","重要度","説明"],rows);
}}

function sortableTable(id, headers, rows) {{
  const ths = headers.map((h,i) => `<th onclick="sortTable('${{id}}',${{i}})">${{h}}<span class="sort-arrow">&#9650;</span></th>`).join("");
  return `<table class="data-table" id="${{id}}"><thead><tr>${{ths}}</tr></thead><tbody>${{rows}}</tbody></table>`;
}}
function priorityBadge(p) {{
  if(!p) return "";
  const cls = {{"high":"high","medium":"medium","low":"low","must":"must","should":"should","could":"could"}}[p]||"low";
  return `<span class="badge badge-${{cls}}">${{p}}</span>`;
}}

// ===== Navigate =====
function navigate(key) {{
  currentView = key;
  document.querySelectorAll(".view-section").forEach(s => s.classList.remove("active"));
  document.querySelectorAll(".sb-nav li").forEach(li => li.classList.toggle("active", li.dataset.view===key));
  const sec = document.getElementById("view-"+key);
  if(sec) sec.classList.add("active");
  // Render diagram lazily
  const vCfg = VIEWS.find(v=>v.key===key);
  if(vCfg && vCfg.diagram && !renderedDiagrams.has(key)) {{
    renderDiagram("dg-"+key, MERMAID_SRC[vCfg.diagram]);
    renderedDiagrams.add(key);
  }}
  // Special views
  // scenarios: テーブルからシナリオIDクリックで詳細パネルに表示
  if(key==="states") initStateTabs();
  if(key==="business") buildBusinessView();
  if(key==="actor_uc") buildActorUcMatrix();
  if(key==="cross_ref") buildCrossRef();
}}

async function renderDiagram(containerId, src) {{
  const el = document.getElementById(containerId);
  if(!el || !src) {{ if(el) el.innerHTML="<p style='color:#999'>ダイアグラムデータなし</p>"; return; }}
  try {{
    const id = "mmd-" + containerId + "-" + Date.now();
    const {{ svg }} = await mermaid.render(id, src);
    // ズーム・パン用のラッパーとコントロールを追加
    el.innerHTML = `<div class="zoom-controls">
      <button class="zoom-btn" data-zoom="in" title="拡大">+</button>
      <button class="zoom-btn" data-zoom="out" title="縮小">−</button>
      <button class="zoom-btn" data-zoom="reset" title="リセット">⟲</button>
    </div><div class="diagram-inner">${{svg}}</div>`;
    _initZoomPan(el);
    _attachSvgClickHandlers(el);
  }} catch(err) {{
    el.innerHTML = `<pre style="color:var(--high);font-size:12px">描画エラー: ${{err.message}}</pre>`;
  }}
}}

function _initZoomPan(container) {{
  const inner = container.querySelector(".diagram-inner");
  if(!inner) return;
  let scale = 1, panX = 0, panY = 0;
  let isDragging = false, startX = 0, startY = 0;

  function applyTransform() {{
    inner.style.transform = `translate(${{panX}}px, ${{panY}}px) scale(${{scale}})`;
  }}

  // マウスホイールでズーム
  container.addEventListener("wheel", (e) => {{
    e.preventDefault();
    const delta = e.deltaY > 0 ? -0.1 : 0.1;
    scale = Math.min(Math.max(0.1, scale + delta), 5);
    applyTransform();
  }}, {{passive: false}});

  // ドラッグでパン
  container.addEventListener("mousedown", (e) => {{
    if(e.target.closest(".zoom-btn") || e.target.closest(".node") || e.target.closest("[data-entity]") || e.target.closest("[data-uc]")) return;
    isDragging = true;
    startX = e.clientX - panX;
    startY = e.clientY - panY;
    container.classList.add("dragging");
  }});
  document.addEventListener("mousemove", (e) => {{
    if(!isDragging) return;
    panX = e.clientX - startX;
    panY = e.clientY - startY;
    inner.style.transition = "none";
    applyTransform();
  }});
  document.addEventListener("mouseup", () => {{
    isDragging = false;
    container.classList.remove("dragging");
    inner.style.transition = "transform 0.1s ease";
  }});

  // ボタンコントロール
  container.querySelectorAll(".zoom-btn").forEach(btn => {{
    btn.addEventListener("click", (e) => {{
      e.stopPropagation();
      const action = btn.dataset.zoom;
      if(action === "in") scale = Math.min(scale + 0.2, 5);
      else if(action === "out") scale = Math.max(scale - 0.2, 0.1);
      else {{ scale = 1; panX = 0; panY = 0; }}
      applyTransform();
    }});
  }});
}}

function _attachSvgClickHandlers(container) {{
  // MermaidのSVGノードからUC-IDやエンティティ名を検出してクリック可能にする
  const nodes = container.querySelectorAll(".node, .nodeLabel, .label, g[id]");
  nodes.forEach(node => {{
    const text = node.textContent || "";
    // UC-XXX パターン
    const ucMatch = text.match(/UC-\\d{{3}}/);
    if(ucMatch) {{
      node.style.cursor = "pointer";
      node.addEventListener("click", (e) => {{
        e.stopPropagation();
        showUcDetail(ucMatch[0]);
      }});
      return;
    }}
    // アクター名マッチ
    const actors = [...new Set((DATA.usecases||[]).map(u=>u.actor))];
    const actorMatch = actors.find(a => text.trim() === a);
    if(actorMatch) {{
      node.style.cursor = "pointer";
      node.addEventListener("click", (e) => {{
        e.stopPropagation();
        showActorDetail(actorMatch);
      }});
      return;
    }}
    // エンティティ名マッチ
    const ent = (DATA.entities||[]).find(e => text.trim() === e.name || text.trim() === e.class_name);
    if(ent) {{
      node.style.cursor = "pointer";
      node.addEventListener("click", (e) => {{
        e.stopPropagation();
        showEntityDetail(ent.class_name);
      }});
    }}
  }});
}}

// ===== Scenarios (no-op, diagram shown in detail panel) =====

// ===== State tabs =====
let activeStateEntity = null;
function initStateTabs() {{
  const bar = document.getElementById("state-tabs");
  if(!bar || bar.children.length > 0) return;
  (DATA.state_machines||[]).forEach((sm, i) => {{
    const btn = document.createElement("button");
    btn.className = "tab-btn" + (i===0?" active":"");
    btn.textContent = sm.entity_name;
    btn.onclick = () => selectStateTab(sm, btn);
    bar.appendChild(btn);
  }});
  if(DATA.state_machines && DATA.state_machines.length) selectStateTab(DATA.state_machines[0], bar.children[0]);
}}
function selectStateTab(sm, btn) {{
  activeStateEntity = sm.entity_class;
  document.querySelectorAll("#state-tabs .tab-btn").forEach(b=>b.classList.remove("active"));
  btn.classList.add("active");
  const srcKey = "state_" + sm.entity_class;
  renderDiagram("dg-state", MERMAID_SRC[srcKey]);
}}

// ===== Cross-reference matrix (CRUD) =====
function _routeToCrud(routes) {{
  const crud = new Set();
  (routes||[]).forEach(r => {{
    const m = r.split(" ")[0].toUpperCase();
    if(m === "POST") crud.add("C");
    if(m === "GET") crud.add("R");
    if(m === "PUT" || m === "PATCH") crud.add("U");
    if(m === "DELETE") crud.add("D");
  }});
  return crud;
}}
function buildBusinessView() {{
  const wrap = document.getElementById("business-view");
  if(!wrap || wrap.children.length > 0) return;
  const ucs = (DATA.usecases||[]);
  const entities = (DATA.entities||[]);
  // 1. エンティティごとにCUD操作を持つUCをグループ化 → UCグループ
  const ucGroups = {{}};  // key: エンティティ名 → {{entity, ucs: [uc]}}
  ucs.forEach(u => {{
    const crud = _routeToCrud(u.related_routes);
    const hasCUD = crud.has("C") || crud.has("U") || crud.has("D");
    if(!hasCUD) return;
    (u.related_entities||[]).forEach(en => {{
      const entObj = entities.find(e => e.class_name===en || e.name===en);
      const entityName = entObj ? entObj.name : en;
      if(!ucGroups[entityName]) ucGroups[entityName] = {{entity: entityName, ucs: []}};
      if(!ucGroups[entityName].ucs.find(x => x.id === u.id)) {{
        ucGroups[entityName].ucs.push(u);
      }}
    }});
  }});
  // 2. アクター×UCグループ → 業務
  const gyomuList = [];
  const gyomuSet = new Set();
  Object.values(ucGroups).forEach(grp => {{
    const actorMap = {{}};
    grp.ucs.forEach(u => {{
      if(!actorMap[u.actor]) actorMap[u.actor] = [];
      actorMap[u.actor].push(u);
    }});
    Object.entries(actorMap).forEach(([actor, ucList]) => {{
      const gyomuKey = actor + "|" + grp.entity;
      if(!gyomuSet.has(gyomuKey)) {{
        gyomuSet.add(gyomuKey);
        const crudSet = new Set();
        ucList.forEach(u => {{
          const crud = _routeToCrud(u.related_routes);
          ["C","U","D"].forEach(c => {{ if(crud.has(c)) crudSet.add(c); }});
        }});
        gyomuList.push({{
          actor: actor,
          entity: grp.entity,
          name: grp.entity + "管理",
          ucs: ucList,
          crud: crudSet,
        }});
      }}
    }});
  }});
  // ソート: アクター → エンティティ
  gyomuList.sort((a,b) => a.actor.localeCompare(b.actor) || a.entity.localeCompare(b.entity));
  // 3. テーブル描画
  const crudColors = {{C:"#2a9d8f",U:"#f4a261",D:"#e63946"}};
  let html = `<p style="margin-bottom:12px;color:#666">業務 = アクター × UCグループ（エンティティに対するCUD操作を持つUCの集合）</p>`;
  html += "<table class='data-table' id='business-tbl'><thead><tr>";
  html += `<th onclick="sortTable('business-tbl',0)">業務名<span class="sort-arrow">&#9650;</span></th>`;
  html += `<th onclick="sortTable('business-tbl',1)">アクター<span class="sort-arrow">&#9650;</span></th>`;
  html += `<th onclick="sortTable('business-tbl',2)">対象エンティティ<span class="sort-arrow">&#9650;</span></th>`;
  html += `<th>CUD</th><th>関連UC</th>`;
  html += "</tr></thead><tbody>";
  gyomuList.forEach(g => {{
    const cudLabels = ["C","U","D"].filter(c=>g.crud.has(c))
      .map(c=>`<span style="color:${{crudColors[c]}};font-weight:bold">${{c}}</span>`).join(" ");
    const entObj = entities.find(e => e.name===g.entity);
    const cls = entObj ? entObj.class_name : g.entity;
    const ucLinks = g.ucs.map(u =>
      `<span class="clickable" data-uc="${{u.id}}" style="font-size:0.85em">${{u.id}}</span>`
    ).join(" ");
    html += `<tr>`;
    html += `<td><strong>${{g.name}}</strong></td>`;
    html += `<td class="clickable" data-actor="${{g.actor}}" style="cursor:pointer;color:var(--accent)">${{g.actor}}</td>`;
    html += `<td class="clickable" data-entity="${{cls}}" style="cursor:pointer;color:var(--accent)">${{g.entity}}</td>`;
    html += `<td>${{cudLabels}}</td>`;
    html += `<td>${{ucLinks}}</td>`;
    html += `</tr>`;
  }});
  html += "</tbody></table>";
  html += `<div style="margin-top:12px;font-size:13px">
    <span style="color:${{crudColors.C}}">&#9632; C=Create</span>&nbsp;
    <span style="color:${{crudColors.U}}">&#9632; U=Update</span>&nbsp;
    <span style="color:${{crudColors.D}}">&#9632; D=Delete</span>&nbsp;
    <span style="color:#999">※ Read のみのUCは業務に含まれません</span>
  </div>`;
  wrap.innerHTML = html;
}}

function buildActorUcMatrix() {{
  const wrap = document.getElementById("actor-uc-matrix");
  if(!wrap || wrap.children.length > 0) return;
  const ucs = (DATA.usecases||[]);
  // アクター一覧を収集
  const actorSet = new Set();
  ucs.forEach(u => {{ if(u.actor) actorSet.add(u.actor); }});
  const actors = [...actorSet].sort();
  // カテゴリ一覧を収集
  const categorySet = new Set();
  ucs.forEach(u => {{ if(u.category) categorySet.add(u.category); }});
  const categories = [...categorySet].sort();
  // アクター×カテゴリごとにUCをグループ化
  const map = {{}};
  ucs.forEach(u => {{
    const key = (u.actor||"") + "|" + (u.category||"");
    if(!map[key]) map[key] = [];
    map[key].push(u);
  }});
  let html = "<table class='matrix-table'><thead><tr><th class='row-head'>アクター \\ カテゴリ</th>";
  categories.forEach(cat => html += `<th>${{cat}}</th>`);
  html += "</tr></thead><tbody>";
  actors.forEach(actor => {{
    html += "<tr>";
    html += `<td class="row-head clickable-header" data-actor="${{actor}}" style="cursor:pointer">${{actor}}</td>`;
    categories.forEach(cat => {{
      const key = actor + "|" + cat;
      const ucList = map[key] || [];
      if(ucList.length > 0) {{
        const labels = ucList.map(u =>
          `<span class="clickable" data-uc="${{u.id}}" style="font-size:0.85em">${{u.id}}</span>`
        ).join("<br>");
        html += `<td class="check">${{labels}}</td>`;
      }} else {{
        html += `<td></td>`;
      }}
    }});
    html += "</tr>";
  }});
  html += "</tbody></table>";
  wrap.innerHTML = html;
}}

function buildCrossRef() {{
  const wrap = document.getElementById("cross-matrix");
  if(!wrap || wrap.children.length > 0) return;
  const entities = (DATA.entities||[]).map(e=>e.name);
  const ucs = (DATA.usecases||[]);
  // Build lookup: entity+uc -> CRUD set
  const map = {{}};
  ucs.forEach(u => {{
    const crud = _routeToCrud(u.related_routes);
    (u.related_entities||[]).forEach(en => {{
      // match by class_name or japanese name
      const eName = (DATA.entities||[]).find(e => e.class_name===en || e.name===en);
      const key = eName ? eName.name : en;
      const mk = key + "|" + u.id;
      if(!map[mk]) map[mk] = new Set();
      crud.forEach(c => map[mk].add(c));
    }});
  }});
  const crudColors = {{C:"#2a9d8f",R:"#4361ee",U:"#f4a261",D:"#e63946"}};
  let html = "<table class='matrix-table'><thead><tr><th class='row-head'>エンティティ \\ UC</th>";
  ucs.forEach(u => html += `<th title="${{u.name}}" class="clickable-header" data-uc="${{u.id}}" style="cursor:pointer">${{u.id}}</th>`);
  html += "</tr></thead><tbody>";
  entities.forEach(en => {{
    const entObj = (DATA.entities||[]).find(e=>e.name===en);
    const cls = entObj ? entObj.class_name : en;
    html += "<tr>";
    html += `<td class="row-head clickable-header" data-entity="${{cls}}" style="cursor:pointer">${{en}}</td>`;
    ucs.forEach(u => {{
      const mk = en + "|" + u.id;
      const cruds = map[mk];
      if(cruds && cruds.size > 0) {{
        const labels = ["C","R","U","D"].filter(c=>cruds.has(c))
          .map(c=>`<span style="color:${{crudColors[c]}};font-weight:bold">${{c}}</span>`).join("");
        html += `<td class="check">${{labels}}</td>`;
      }} else {{
        html += `<td></td>`;
      }}
    }});
    html += "</tr>";
  }});
  html += "</tbody></table>";
  // Legend
  html += `<div style="margin-top:12px;font-size:13px">
    <span style="color:${{crudColors.C}}">&#9632; C=Create</span>&nbsp;
    <span style="color:${{crudColors.R}}">&#9632; R=Read</span>&nbsp;
    <span style="color:${{crudColors.U}}">&#9632; U=Update</span>&nbsp;
    <span style="color:${{crudColors.D}}">&#9632; D=Delete</span>
  </div>`;
  wrap.innerHTML = html;
}}

// ===== Sortable tables =====
const sortState = {{}};
function sortTable(tableId, colIdx) {{
  const table = document.getElementById(tableId);
  if(!table) return;
  const key = tableId + "-" + colIdx;
  sortState[key] = !sortState[key];
  const asc = sortState[key];
  const tbody = table.querySelector("tbody");
  const rows = Array.from(tbody.rows);
  rows.sort((a,b) => {{
    let va = a.cells[colIdx].textContent.trim();
    let vb = b.cells[colIdx].textContent.trim();
    const na = parseFloat(va), nb = parseFloat(vb);
    if(!isNaN(na) && !isNaN(nb)) return asc ? na-nb : nb-na;
    return asc ? va.localeCompare(vb,"ja") : vb.localeCompare(va,"ja");
  }});
  rows.forEach(r => tbody.appendChild(r));
}}

// ===== Search =====
function initSearch() {{
  const input = document.getElementById("search-input");
  const box = document.getElementById("search-results");
  input.addEventListener("input", () => {{
    const q = input.value.trim().toLowerCase();
    if(q.length < 1) {{ box.style.display="none"; return; }}
    let items = [];
    (DATA.entities||[]).forEach(e => {{
      if((e.name+e.class_name+e.table_name).toLowerCase().includes(q))
        items.push({{type:"Entity",label:e.name,sub:e.class_name,cls:e.class_name}});
    }});
    (DATA.usecases||[]).forEach(u => {{
      if((u.id+u.name+u.actor).toLowerCase().includes(q))
        items.push({{type:"UseCase",label:u.id+" "+u.name,sub:u.actor,uc:u.id}});
    }});
    if(!items.length) {{ box.style.display="none"; return; }}
    box.style.display="block";
    box.innerHTML = items.slice(0,12).map(it => {{
      const color = it.type==="Entity"?"var(--accent)":"var(--medium)";
      const data = it.cls ? `data-entity="${{it.cls}}"` : `data-uc="${{it.uc}}"`;
      return `<div class="sr-item" ${{data}}><span class="sr-tag" style="background:${{color}}">${{it.type}}</span>${{it.label}} <span style="color:var(--text-muted);font-size:11px">${{it.sub}}</span></div>`;
    }}).join("");
  }});
  document.addEventListener("click", e => {{
    if(!box.contains(e.target) && e.target!==input) box.style.display="none";
  }});
  box.addEventListener("click", e => {{
    const item = e.target.closest(".sr-item");
    if(!item) return;
    box.style.display="none";
    input.value="";
    if(item.dataset.entity) showEntityDetail(item.dataset.entity);
    else if(item.dataset.uc) showUcDetail(item.dataset.uc);
  }});
}}

// ===== Detail panel =====
document.addEventListener("click", e => {{
  const ucCond = e.target.closest("[data-uc-condition]");
  if(ucCond && !ucCond.closest("#search-results")) {{ showUcConditionDetail(ucCond.dataset.ucCondition); return; }}
  const screen = e.target.closest("[data-screen]");
  if(screen && !screen.closest("#search-results")) {{ showScreenDetail(screen.dataset.screen); return; }}
  const sc = e.target.closest("[data-scenario]");
  if(sc && !sc.closest("#search-results")) {{ showScenarioDetail(sc.dataset.scenario); return; }}
  const actor = e.target.closest("[data-actor]");
  if(actor && !actor.closest("#search-results")) {{ showActorDetail(actor.dataset.actor); return; }}
  const bp = e.target.closest("[data-policy]");
  if(bp && !bp.closest("#search-results")) {{ showPolicyDetail(bp.dataset.policy); return; }}
  const el = e.target.closest("[data-entity]");
  if(el && !el.closest("#search-results")) {{ showEntityDetail(el.dataset.entity); return; }}
  const uc = e.target.closest("[data-uc]");
  if(uc && !uc.closest("#search-results")) {{ showUcDetail(uc.dataset.uc); return; }}
}});

function showPolicyDetail(bpId) {{
  const bp = (DATA.policies||[]).find(p => p.id===bpId);
  if(!bp) return;
  let html = `<div class="detail-title">${{bp.id}} ${{bp.name}}</div>`;
  html += `<div class="detail-section"><h4>カテゴリ</h4><p>${{bp.category||"—"}}</p></div>`;
  html += `<div class="detail-section"><h4>重要度</h4><p>${{priorityBadge(bp.severity)}}</p></div>`;
  if(bp.description) html += `<div class="detail-section"><h4>説明</h4><p>${{bp.description}}</p></div>`;
  if(bp.related_entities && bp.related_entities.length) {{
    html += `<div class="detail-section"><h4>関連エンティティ</h4><ul class="detail-list">${{bp.related_entities.map(e => {{
      const ent = (DATA.entities||[]).find(x => x.class_name===e || x.name===e);
      const cls = ent ? ent.class_name : e;
      return `<li><span class="clickable" data-entity="${{cls}}">${{e}}</span></li>`;
    }}).join("")}}</ul></div>`;
  }}
  if(bp.related_usecases && bp.related_usecases.length) {{
    html += `<div class="detail-section"><h4>関連ユースケース</h4><ul class="detail-list">${{bp.related_usecases.map(uid => {{
      const uc = (DATA.usecases||[]).find(u => u.id===uid);
      return `<li><span class="clickable" data-uc="${{uid}}">${{uid}}</span>${{uc ? " " + uc.name : ""}}</li>`;
    }}).join("")}}</ul></div>`;
  }}
  if(bp.code_references && bp.code_references.length) {{
    html += `<div class="detail-section"><h4>コード参照</h4><table class="data-table"><thead><tr><th>ファイル</th><th>説明</th><th>種別</th></tr></thead><tbody>`;
    bp.code_references.forEach(ref => {{
      const typeBadge = ref.code_type ? `<span class="badge badge-could">${{ref.code_type}}</span>` : "—";
      html += `<tr><td><code style="font-size:0.85em">${{ref.file_path}}</code></td><td>${{ref.description}}</td><td>${{typeBadge}}</td></tr>`;
    }});
    html += `</tbody></table></div>`;
  }}
  openDetail(html);
}}

function showEntityDetail(cls) {{
  const ent = (DATA.entities||[]).find(e => e.class_name===cls || e.name===cls);
  if(!ent) return;
  const rels = (DATA.relationships||[]).filter(r => r.from_entity===ent.name || r.to_entity===ent.name);
  const groups = (DATA.information_groups||[]).filter(g => (g.entities||[]).includes(ent.name));
  const sms = (DATA.state_machines||[]).filter(s => s.entity_class===cls || s.entity_name===ent.name);
  let html = `<div class="detail-title">${{ent.name}} (${{ent.class_name}})</div>`;
  html += `<div class="detail-section"><h4>テーブル</h4><p>${{ent.table_name||"—"}}</p></div>`;
  if(ent.description) html += `<div class="detail-section"><h4>説明</h4><p>${{ent.description}}</p></div>`;
  if(ent.attributes && ent.attributes.length) {{
    html += `<div class="detail-section"><h4>属性</h4><ul class="detail-list">${{ent.attributes.map(a=>`<li>${{typeof a==="string"?a:a.name+" : "+(a.type||"")}}</li>`).join("")}}</ul></div>`;
  }}
  if(rels.length) {{
    html += `<div class="detail-section"><h4>関連</h4><ul class="detail-list">${{rels.map(r=>`<li>${{r.from_entity}} → ${{r.to_entity}} (${{r.relation_type}}) ${{r.label||""}}</li>`).join("")}}</ul></div>`;
  }}
  if(groups.length) {{
    html += `<div class="detail-section"><h4>関連ユースケース</h4><ul class="detail-list">${{groups.map(g=>`<li><span class="clickable" data-uc="${{g.usecase_id}}">${{g.usecase_id}}</span> ${{g.usecase_name}}</li>`).join("")}}</ul></div>`;
  }}
  if(sms.length) {{
    html += `<div class="detail-section"><h4>状態遷移</h4><ul class="detail-list">${{sms.map(s=>`<li>フィールド: ${{s.state_field}} / 状態数: ${{(s.states||[]).length}}</li>`).join("")}}</ul></div>`;
  }}
  openDetail(html);
}}

function showUcDetail(ucId) {{
  const uc = (DATA.usecases||[]).find(u => u.id===ucId);
  if(!uc) return;
  const scs = (DATA.scenarios||[]).filter(s => s.usecase_id===ucId);
  const pols = (DATA.policies||[]).filter(p => (p.related_usecases||[]).includes(ucId));
  const groups = (DATA.information_groups||[]).filter(g => g.usecase_id===ucId);
  let html = `<div class="detail-title">${{uc.id}} ${{uc.name}}</div>`;
  html += `<div class="detail-section"><h4>アクター</h4><p>${{uc.actor}}</p></div>`;
  if(uc.description) html += `<div class="detail-section"><h4>説明</h4><p>${{uc.description}}</p></div>`;
  html += `<div class="detail-section"><h4>優先度</h4>${{priorityBadge(uc.priority)}}</div>`;
  if(uc.preconditions && uc.preconditions.length) {{
    html += `<div class="detail-section"><h4>事前条件</h4><ul class="detail-list">${{uc.preconditions.map(c=>`<li>${{c}}</li>`).join("")}}</ul></div>`;
  }}
  if(uc.postconditions && uc.postconditions.length) {{
    html += `<div class="detail-section"><h4>事後条件</h4><ul class="detail-list">${{uc.postconditions.map(c=>`<li>${{c}}</li>`).join("")}}</ul></div>`;
  }}
  // 関連エンティティ: information_groups またはユースケースの related_entities から
  const entList = (groups.length && groups[0].entities) ? groups[0].entities : (uc.related_entities||[]);
  if(entList.length) {{
    html += `<div class="detail-section"><h4>関連エンティティ</h4><ul class="detail-list">${{entList.map(en=>{{
      const entObj = (DATA.entities||[]).find(e=>e.name===en||e.class_name===en);
      const cls = entObj ? entObj.class_name : en;
      const name = entObj ? entObj.name : en;
      return `<li><span class="clickable" data-entity="${{cls}}">${{name}}</span></li>`;
    }}).join("")}}</ul></div>`;
  }}
  if(uc.related_controllers && uc.related_controllers.length) {{
    html += `<div class="detail-section"><h4>関連コントローラー</h4><ul class="detail-list">${{uc.related_controllers.map(c=>`<li>${{c}}</li>`).join("")}}</ul></div>`;
  }}
  if(uc.related_views && uc.related_views.length) {{
    html += `<div class="detail-section"><h4>関連ビュー</h4><ul class="detail-list">${{uc.related_views.map(v=>`<li>${{v}}</li>`).join("")}}</ul></div>`;
  }}
  if(uc.related_routes && uc.related_routes.length) {{
    html += `<div class="detail-section"><h4>APIルート</h4><ul class="detail-list">${{uc.related_routes.map(r=>`<li><code>${{r}}</code></li>`).join("")}}</ul></div>`;
  }}
  if(scs.length) {{
    html += `<div class="detail-section"><h4>シナリオ</h4><ul class="detail-list">${{scs.map(s=>`<li>${{s.scenario_id}} ${{s.scenario_name}} (${{s.scenario_type}})</li>`).join("")}}</ul></div>`;
  }}
  if(pols.length) {{
    html += `<div class="detail-section"><h4>関連ポリシー</h4><ul class="detail-list">${{pols.map(p=>`<li>${{p.id}} ${{p.name}}</li>`).join("")}}</ul></div>`;
  }}
  openDetail(html);
}}

function showActorDetail(actorName) {{
  const ucs = (DATA.usecases||[]).filter(u => u.actor === actorName);
  if(!ucs.length) return;
  // 集計
  const categories = [...new Set(ucs.map(u=>u.category).filter(Boolean))];
  const entitySet = new Set();
  const controllerSet = new Set();
  const routeSet = new Set();
  ucs.forEach(u => {{
    (u.related_entities||[]).forEach(e => entitySet.add(e));
    (u.related_controllers||[]).forEach(c => controllerSet.add(c));
    (u.related_routes||[]).forEach(r => routeSet.add(r));
  }});
  const scenarios = (DATA.scenarios||[]).filter(s => ucs.some(u => u.id === s.usecase_id));
  const policies = (DATA.policies||[]).filter(p => (p.related_usecases||[]).some(uid => ucs.some(u => u.id === uid)));

  let html = `<div class="detail-title">${{actorName}}</div>`;
  html += `<div class="detail-section"><h4>統計</h4>
    <p>ユースケース: ${{ucs.length}}件 | エンティティ: ${{entitySet.size}}件 | シナリオ: ${{scenarios.length}}件</p>
  </div>`;
  if(categories.length) {{
    html += `<div class="detail-section"><h4>関連カテゴリ</h4><ul class="detail-list">${{categories.map(c=>`<li>${{c}}</li>`).join("")}}</ul></div>`;
  }}
  html += `<div class="detail-section"><h4>ユースケース</h4><ul class="detail-list">${{ucs.map(u=>
    `<li><span class="clickable" data-uc="${{u.id}}">${{u.id}}</span> ${{u.name}} <span style="color:#999">[${{u.priority}}]</span></li>`
  ).join("")}}</ul></div>`;
  if(entitySet.size) {{
    const entList = [...entitySet];
    html += `<div class="detail-section"><h4>関連エンティティ</h4><ul class="detail-list">${{entList.map(en=>{{
      const entObj = (DATA.entities||[]).find(e=>e.class_name===en||e.name===en);
      const cls = entObj ? entObj.class_name : en;
      const name = entObj ? entObj.name : en;
      return `<li><span class="clickable" data-entity="${{cls}}">${{name}}</span></li>`;
    }}).join("")}}</ul></div>`;
  }}
  if(controllerSet.size) {{
    html += `<div class="detail-section"><h4>関連コントローラー</h4><ul class="detail-list">${{[...controllerSet].map(c=>`<li>${{c}}</li>`).join("")}}</ul></div>`;
  }}
  if(routeSet.size) {{
    const routeList = [...routeSet].slice(0, 20);
    html += `<div class="detail-section"><h4>APIルート（上位${{Math.min(routeSet.size,20)}}件）</h4><ul class="detail-list">${{routeList.map(r=>`<li><code>${{r}}</code></li>`).join("")}}</ul></div>`;
  }}
  if(scenarios.length) {{
    html += `<div class="detail-section"><h4>シナリオ</h4><ul class="detail-list">${{scenarios.map(s=>`<li>${{s.scenario_id}} ${{s.scenario_name}}</li>`).join("")}}</ul></div>`;
  }}
  if(policies.length) {{
    html += `<div class="detail-section"><h4>関連ポリシー</h4><ul class="detail-list">${{policies.map(p=>`<li>${{p.id}} ${{p.name}}</li>`).join("")}}</ul></div>`;
  }}
  openDetail(html);
}}

function showUcConditionDetail(ucId) {{
  const uc = (DATA.usecases||[]).find(u => u.id === ucId);
  if(!uc) return;
  const srcKey = "uc_condition_" + ucId;
  const src = MERMAID_SRC[srcKey];

  let html = `<div class="detail-title">${{uc.id}} ${{uc.name}}</div>`;
  html += `<div class="detail-section"><p>アクター: ${{uc.actor}} | カテゴリ: ${{uc.category||"—"}} | ${{priorityBadge(uc.priority)}}</p></div>`;
  if(uc.description) html += `<div class="detail-section"><p>${{uc.description}}</p></div>`;

  // 条件図ダイアグラム
  html += `<div class="scenario-diagram-wrap" id="uc-condition-diagram"></div>`;

  // 事前条件
  if(uc.preconditions && uc.preconditions.length) {{
    html += `<div class="detail-section"><h4>事前条件</h4><ul class="detail-list">${{uc.preconditions.map(c=>`<li>${{c}}</li>`).join("")}}</ul></div>`;
  }}
  // 事後条件
  if(uc.postconditions && uc.postconditions.length) {{
    html += `<div class="detail-section"><h4>事後条件</h4><ul class="detail-list">${{uc.postconditions.map(c=>`<li>${{c}}</li>`).join("")}}</ul></div>`;
  }}
  // 関連エンティティ
  if(uc.related_entities && uc.related_entities.length) {{
    html += `<div class="detail-section"><h4>関連エンティティ</h4><ul class="detail-list">${{uc.related_entities.map(en=>{{
      const entObj = (DATA.entities||[]).find(e=>e.class_name===en||e.name===en);
      const cls = entObj ? entObj.class_name : en;
      const name = entObj ? entObj.name : en;
      return `<li><span class="clickable" data-entity="${{cls}}">${{name}}</span></li>`;
    }}).join("")}}</ul></div>`;
  }}
  // APIルート
  if(uc.related_routes && uc.related_routes.length) {{
    html += `<div class="detail-section"><h4>APIルート</h4><ul class="detail-list">${{uc.related_routes.map(r=>`<li><code>${{r}}</code></li>`).join("")}}</ul></div>`;
  }}

  openDetail(html, true);

  if(src) {{
    setTimeout(async () => {{
      const container = document.getElementById("uc-condition-diagram");
      if(!container) return;
      try {{
        const id = "mmd-uccond-" + Date.now();
        const {{ svg }} = await mermaid.render(id, src);
        container.innerHTML = `<div class="zoom-controls">
          <button class="zoom-btn" data-zoom="in" title="拡大">+</button>
          <button class="zoom-btn" data-zoom="out" title="縮小">−</button>
          <button class="zoom-btn" data-zoom="reset" title="リセット">⟲</button>
        </div><div class="diagram-inner">${{svg}}</div>`;
        _initZoomPan(container);
        _attachSvgClickHandlers(container);
      }} catch(err) {{
        container.innerHTML = `<pre style="color:var(--high);font-size:12px">${{err.message}}</pre>`;
      }}
    }}, 100);
  }}
}}

function showScreenDetail(routePath) {{
  const scr = (DATA.screen_specs||[]).find(s => s.route_path === routePath);
  if(!scr) return;

  let html = `<div class="detail-title">${{scr.page_title || scr.component_name}}</div>`;
  html += `<div class="detail-section"><p><code>${{scr.route_path}}</code></p>`;
  html += `<p>コンポーネント: ${{scr.component_name}}</p>`;
  if(scr.file_path) html += `<p>ファイル: <code>${{scr.file_path}}</code></p>`;
  if(scr.layout_type) html += `<p>レイアウト: ${{scr.layout_type}}</p>`;
  if(scr.shared_layout) html += `<p>共有レイアウト: ${{scr.shared_layout}}</p>`;
  html += `</div>`;

  // ボタン
  if(scr.action_buttons && scr.action_buttons.length) {{
    html += `<div class="detail-section"><h4>ボタン / アクション</h4>`;
    html += `<table class="data-table"><thead><tr><th>ラベル</th><th>遷移先</th><th>API</th></tr></thead><tbody>`;
    scr.action_buttons.forEach(b => {{
      const target = b.target ? `<span class="clickable" data-screen="${{b.target}}" style="color:var(--accent)">${{b.target}}</span>` : "—";
      html += `<tr><td>${{b.label}}</td><td>${{target}}</td><td><code>${{b.api_call||"—"}}</code></td></tr>`;
    }});
    html += `</tbody></table></div>`;
  }}

  // フォームフィールド
  if(scr.form_fields && scr.form_fields.length) {{
    html += `<div class="detail-section"><h4>フォーム項目</h4>`;
    html += `<table class="data-table"><thead><tr><th>ラベル</th><th>種別</th></tr></thead><tbody>`;
    scr.form_fields.forEach(f => {{
      html += `<tr><td>${{f.label}}</td><td>${{f.element_type}}</td></tr>`;
    }});
    html += `</tbody></table></div>`;
  }}

  // タブ
  if(scr.tabs && scr.tabs.length) {{
    html += `<div class="detail-section"><h4>タブ</h4><ul class="detail-list">${{scr.tabs.map(t=>`<li>${{t}}</li>`).join("")}}</ul></div>`;
  }}

  // モーダル
  if(scr.modals && scr.modals.length) {{
    html += `<div class="detail-section"><h4>モーダル / ダイアログ</h4><ul class="detail-list">${{scr.modals.map(m=>`<li>${{m}}</li>`).join("")}}</ul></div>`;
  }}

  // API アクション
  if(scr.api_actions && Object.keys(scr.api_actions).length) {{
    html += `<div class="detail-section"><h4>APIアクション</h4>`;
    html += `<table class="data-table"><thead><tr><th>操作</th><th>エンドポイント</th></tr></thead><tbody>`;
    Object.entries(scr.api_actions).forEach(([label, api]) => {{
      html += `<tr><td>${{label}}</td><td><code>${{api||"—"}}</code></td></tr>`;
    }});
    html += `</tbody></table></div>`;
  }}

  // ナビゲーション
  if(scr.parent_page) {{
    html += `<div class="detail-section"><h4>親ページ</h4><p><span class="clickable" data-screen="${{scr.parent_page}}" style="color:var(--accent)">${{scr.parent_page}}</span></p></div>`;
  }}
  if(scr.child_pages && scr.child_pages.length) {{
    html += `<div class="detail-section"><h4>子ページ</h4><ul class="detail-list">${{scr.child_pages.map(c=>`<li><span class="clickable" data-screen="${{c}}" style="color:var(--accent)">${{c}}</span></li>`).join("")}}</ul></div>`;
  }}

  // 共有ナビゲーション
  if(scr.shared_nav_items && scr.shared_nav_items.length) {{
    html += `<div class="detail-section"><h4>共有ナビゲーション</h4><ul class="detail-list">${{scr.shared_nav_items.map(n=>
      `<li><span class="clickable" data-screen="${{n.target}}" style="color:var(--accent)">${{n.label}}</span> → ${{n.target}}</li>`
    ).join("")}}</ul></div>`;
  }}

  // 関連ユースケース
  const relatedUcs = (DATA.usecases||[]).filter(u =>
    (u.related_routes||[]).some(r => {{
      const apiPath = r.split(" ")[1] || r;
      return Object.values(scr.api_actions||{{}}).some(a => a.includes(apiPath));
    }})
  );
  if(relatedUcs.length) {{
    html += `<div class="detail-section"><h4>関連ユースケース</h4><ul class="detail-list">${{relatedUcs.map(u=>
      `<li><span class="clickable" data-uc="${{u.id}}">${{u.id}}</span> ${{u.name}}</li>`
    ).join("")}}</ul></div>`;
  }}

  openDetail(html);
}}

function showScenarioDetail(scenarioId) {{
  const sc = (DATA.scenarios||[]).find(s => s.scenario_id === scenarioId);
  if(!sc) return;
  const srcKey = "scenario_" + scenarioId;
  const src = MERMAID_SRC[srcKey];

  let html = `<div class="detail-title">${{sc.scenario_id}} ${{sc.scenario_name}}</div>`;
  html += `<div class="detail-section">
    <p><span class="clickable" data-uc="${{sc.usecase_id}}" style="color:var(--accent)">${{sc.usecase_id}}</span> ${{sc.usecase_name}} | 種別: ${{sc.scenario_type}}</p>
  </div>`;

  // ダイアグラム描画エリア
  html += `<div class="scenario-diagram-wrap" id="scenario-detail-diagram"></div>`;

  // ステップテーブル
  if(sc.steps && sc.steps.length) {{
    html += `<div class="detail-section"><h4>ステップ</h4>`;
    html += `<table class="data-table"><thead><tr><th>#</th><th>アクター</th><th>操作</th><th>期待結果</th></tr></thead><tbody>`;
    sc.steps.forEach(st => {{
      html += `<tr><td>${{st.step_no}}</td><td>${{st.actor}}</td><td>${{st.action}}</td><td>${{st.expected_result}}</td></tr>`;
    }});
    html += `</tbody></table></div>`;
  }}

  openDetail(html, true);

  // ダイアグラムを非同期で描画
  if(src) {{
    setTimeout(async () => {{
      const container = document.getElementById("scenario-detail-diagram");
      if(!container) return;
      try {{
        const id = "mmd-sc-detail-" + Date.now();
        const {{ svg }} = await mermaid.render(id, src);
        container.innerHTML = `<div class="zoom-controls">
          <button class="zoom-btn" data-zoom="in" title="拡大">+</button>
          <button class="zoom-btn" data-zoom="out" title="縮小">−</button>
          <button class="zoom-btn" data-zoom="reset" title="リセット">⟲</button>
        </div><div class="diagram-inner">${{svg}}</div>`;
        _initZoomPan(container);
      }} catch(err) {{
        container.innerHTML = `<pre style="color:var(--high);font-size:12px">${{err.message}}</pre>`;
      }}
    }}, 100);
  }}
}}

function openDetail(html, wide) {{
  const panel = document.getElementById("detail-panel");
  document.getElementById("detail-content").innerHTML = html;
  panel.classList.remove("wide");
  if(wide) panel.classList.add("wide");
  panel.classList.add("open");
}}
</script>
</body>
</html>"""


def _js_str(s: str) -> str:
    """Python 文字列を JavaScript 文字列リテラルにエスケープして返す。"""
    escaped = s.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n").replace("\r", "\\r").replace("</", "<\\/")
    return f'"{escaped}"'
