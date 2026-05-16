"use strict";

const STATUS_COLORS = {
    emerging: "#facc15",
    active: "#38bdf8",
    dormant: "#94a3b8",
    resolved: "#34d399",
};

const state = {
    threads: [],
    currentThreadId: null,
    cy: null,
    detail: null,
    showImportance: false,
    filterFlags: false,
};

async function fetchJSON(url) {
    const res = await fetch(url);
    if (!res.ok) throw new Error(`${res.status} ${res.statusText}`);
    return res.json();
}

function daysSince(iso) {
    if (!iso) return Infinity;
    const t = Date.parse(iso);
    if (isNaN(t)) return Infinity;
    return (Date.now() - t) / 86400000;
}

function fmtRelative(iso) {
    const d = daysSince(iso);
    if (!isFinite(d)) return "—";
    if (d < 1) return "今天";
    if (d < 2) return "昨天";
    return `${Math.floor(d)} 天前`;
}

function renderSidebar() {
    const list = document.getElementById("thread-list");
    const search = document.getElementById("search").value.trim().toLowerCase();
    const meta = document.getElementById("sidebar-meta");
    const filtered = state.threads
        .filter((t) => !search || (t.title || "").toLowerCase().includes(search))
        .filter((t) => !state.filterFlags || t.mismatch_flag_count > 0 || t.background_repeat_count > 0);

    list.innerHTML = "";
    for (const t of filtered) {
        const li = document.createElement("li");
        li.dataset.threadId = t.thread_id;
        if (t.thread_id === state.currentThreadId) li.classList.add("selected");
        if (daysSince(t.last_covered_in_podcast_at) >= 3) li.classList.add("dim");

        const title = document.createElement("div");
        title.className = "thread-title";
        title.textContent = t.title || "(untitled)";
        li.appendChild(title);

        const meta = document.createElement("div");
        meta.className = "thread-meta";
        meta.append(
            chip(`${t.signal_count} signals`),
            chip(`${t.phase_count} phases`),
            chip(`last seen ${fmtRelative(t.last_seen_at)}`),
        );
        if (t.mismatch_flag_count > 0) {
            const b = document.createElement("span");
            b.className = "badge";
            b.textContent = `mismatch ${t.mismatch_flag_count}`;
            meta.appendChild(b);
        }
        if (t.background_repeat_count > 0) {
            const b = document.createElement("span");
            b.className = "badge repeat";
            b.textContent = `repeat ${t.background_repeat_count}`;
            meta.appendChild(b);
        }
        li.appendChild(meta);

        li.addEventListener("click", () => loadThread(t.thread_id));
        list.appendChild(li);
    }
    meta.textContent = `${filtered.length} / ${state.threads.length} threads`;
}

function chip(text, cls = "") {
    const span = document.createElement("span");
    span.className = "chip" + (cls ? " " + cls : "");
    span.textContent = text;
    return span;
}

async function loadThreads() {
    state.threads = await fetchJSON("/api/threads?lookback_days=30&limit=200");
    renderSidebar();
}

async function loadThread(threadId) {
    state.currentThreadId = threadId;
    renderSidebar();
    document.getElementById("canvas-empty").style.display = "none";
    document.getElementById("cy").classList.add("visible");
    state.detail = await fetchJSON(`/api/threads/${encodeURIComponent(threadId)}`);
    renderGraph();
    renderDetailEmpty();
}

function maxImportance(phase) {
    let max = 0;
    for (const s of phase.signals || []) {
        if (s && typeof s.importance_score === "number" && s.importance_score > max) {
            max = s.importance_score;
        }
    }
    return max;
}

function renderGraph() {
    const phases = state.detail.phases || [];
    const elements = [];
    for (const phase of phases) {
        elements.push({
            data: {
                id: phase.phase_id,
                label: phase.title || phase.phase_id,
                status: phase.status,
                signalCount: phase.signal_count,
                importance: maxImportance(phase),
            },
            classes: phase.status,
        });
    }
    for (const phase of phases) {
        if (phase.parent_phase_id) {
            elements.push({
                data: {
                    id: `${phase.parent_phase_id}__${phase.phase_id}`,
                    source: phase.parent_phase_id,
                    target: phase.phase_id,
                },
                classes: "branch",
            });
        }
    }

    const opacityFn = (ele) => {
        if (!state.showImportance) return 1;
        const imp = ele.data("importance") || 0;
        return Math.max(0.25, Math.min(1, imp / 100));
    };

    if (state.cy) state.cy.destroy();
    state.cy = cytoscape({
        container: document.getElementById("cy"),
        elements,
        layout: { name: "breadthfirst", directed: true, padding: 30, spacingFactor: 1.4 },
        style: [
            {
                selector: "node",
                style: {
                    label: "data(label)",
                    "background-color": (ele) => STATUS_COLORS[ele.data("status")] || "#cbd5e1",
                    "background-opacity": opacityFn,
                    "text-wrap": "wrap",
                    "text-max-width": "140px",
                    "font-size": "11px",
                    color: "#0f172a",
                    "text-valign": "bottom",
                    "text-margin-y": 6,
                    width: (ele) => 24 + Math.min(60, (ele.data("signalCount") || 1) * 8),
                    height: (ele) => 24 + Math.min(60, (ele.data("signalCount") || 1) * 8),
                    "border-width": 2,
                    "border-color": "#0f172a",
                    "border-opacity": 0.4,
                },
            },
            {
                selector: "edge.branch",
                style: {
                    width: 2,
                    "line-color": "#94a3b8",
                    "target-arrow-color": "#94a3b8",
                    "target-arrow-shape": "triangle",
                    "curve-style": "bezier",
                    "line-style": "dashed",
                },
            },
            {
                selector: "node:selected",
                style: { "border-color": "#0284c7", "border-opacity": 1, "border-width": 4 },
            },
        ],
    });
    state.cy.on("tap", "node", (evt) => {
        const phaseId = evt.target.data("id");
        renderDetail(phaseId);
    });
}

function renderDetailEmpty() {
    document.getElementById("detail-empty").hidden = false;
    document.getElementById("detail-content").hidden = true;
}

function renderDetail(phaseId) {
    const phase = (state.detail.phases || []).find((p) => p.phase_id === phaseId);
    if (!phase) return;
    document.getElementById("detail-empty").hidden = true;
    const root = document.getElementById("detail-content");
    root.hidden = false;
    root.innerHTML = "";

    const h = document.createElement("h2");
    h.textContent = phase.title || phase.phase_id;
    root.appendChild(h);

    const status = document.createElement("span");
    status.className = `status-pill ${phase.status}`;
    status.textContent = phase.status;
    status.style.background = STATUS_COLORS[phase.status] || "#cbd5e1";
    root.appendChild(status);

    const meta = document.createElement("div");
    meta.className = "meta";
    meta.innerHTML = `
        signals: ${phase.signal_count} ・ opened ${fmtRelative(phase.opened_at)} ・ last advanced ${fmtRelative(phase.last_advanced_at)}<br/>
        ${phase.parent_phase_id ? `forked from <code>${phase.parent_phase_id}</code><br/>` : ""}
        <em>${phase.novelty_reason || ""}</em>
    `;
    root.appendChild(meta);

    if (phase.summary) {
        const s = document.createElement("div");
        s.className = "reasoning";
        s.textContent = phase.summary;
        root.appendChild(s);
    }

    if ((phase.llm_decision_log || []).length) {
        const h3 = document.createElement("h3");
        h3.textContent = "決策紀錄";
        root.appendChild(h3);
        for (const entry of phase.llm_decision_log) {
            const r = document.createElement("div");
            r.className = "reasoning";
            r.textContent = entry;
            root.appendChild(r);
        }
    }

    const h3 = document.createElement("h3");
    h3.textContent = `Signals (${(phase.signals || []).length})`;
    root.appendChild(h3);
    for (const s of phase.signals || []) {
        const card = document.createElement("div");
        card.className = "signal";
        if (!s || s.missing) {
            card.textContent = `(missing) ${s?.signal_id || ""}`;
            root.appendChild(card);
            continue;
        }
        const t = document.createElement("div");
        t.className = "signal-title";
        if (s.url) {
            const a = document.createElement("a");
            a.href = s.url;
            a.target = "_blank";
            a.rel = "noopener";
            a.textContent = s.title || s.signal_id;
            t.appendChild(a);
        } else {
            t.textContent = s.title || s.signal_id;
        }
        card.appendChild(t);
        const meta = document.createElement("div");
        meta.className = "signal-meta";
        if (s.publisher) meta.appendChild(chip(s.publisher));
        if (typeof s.importance_score === "number") meta.appendChild(chip(`imp ${s.importance_score}`));
        if (s.adjudication_decision) {
            meta.appendChild(chip(`W4: ${s.adjudication_decision}`, "evidence"));
        }
        if (s.is_background_repeat) meta.appendChild(chip("background repeat", "repeat"));
        if ((s.adjudication_rationale || "").includes("thread_mismatch_suspected")) {
            meta.appendChild(chip("mismatch?", "warn"));
        }
        if ((s.adjudication_rationale || "").includes("duplicate_suspected")) {
            meta.appendChild(chip("duplicate?", "warn"));
        }
        card.appendChild(meta);
        root.appendChild(card);
    }
}

document.getElementById("search").addEventListener("input", renderSidebar);
document.getElementById("show-importance").addEventListener("change", (e) => {
    state.showImportance = e.target.checked;
    if (state.detail) renderGraph();
});
document.getElementById("filter-flags").addEventListener("change", (e) => {
    state.filterFlags = e.target.checked;
    renderSidebar();
});

loadThreads().catch((e) => {
    document.getElementById("sidebar-meta").textContent = `error: ${e.message}`;
});
