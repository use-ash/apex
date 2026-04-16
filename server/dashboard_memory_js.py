# Memory admin page — JavaScript module.
# Imported by dashboard_js.py and spliced into DASHBOARD_JS.

DASHBOARD_MEMORY_JS = r"""/* =====================================================================
   Memory Page
   ===================================================================== */

let memoryGuidanceData = [];
let memoryContradictionsData = [];
let memoryStatusData = null;
let memoryDelegationBound = false;

/* -- Event delegation (CSP-safe — replaces inline onclick handlers) -- */

function _bindMemoryDelegation() {
    if (memoryDelegationBound) return;
    memoryDelegationBound = true;

    var guidanceEl = document.getElementById("memory-guidance-content");
    if (guidanceEl) guidanceEl.addEventListener("click", function(e) {
        var btn = e.target.closest("[data-action='delete-guidance']");
        if (btn) deleteGuidanceItem(parseInt(btn.dataset.idx, 10));
    });

    var contradictionsEl = document.getElementById("memory-contradictions-content");
    if (contradictionsEl) contradictionsEl.addEventListener("click", function(e) {
        var btn = e.target.closest("[data-action='resolve']");
        if (btn) resolveContradiction(parseInt(btn.dataset.idx, 10), btn.dataset.resolution);
    });

    var configEl = document.getElementById("memory-config-content");
    if (configEl) configEl.addEventListener("click", function(e) {
        var btn = e.target.closest("#btn-save-memory");
        if (btn) { saveConfig("memory"); return; }

        var infoBtn = e.target.closest(".btn-field-info");
        if (infoBtn) {
            var key = infoBtn.dataset.infoKey;
            var tooltip = document.getElementById("tooltip-memory-" + key);
            if (!tooltip) return;
            /* Close any other open tooltips */
            var allTips = configEl.querySelectorAll(".field-tooltip.visible");
            var allBtns = configEl.querySelectorAll(".btn-field-info.active");
            for (var t = 0; t < allTips.length; t++) {
                if (allTips[t] !== tooltip) allTips[t].classList.remove("visible");
            }
            for (var b = 0; b < allBtns.length; b++) {
                if (allBtns[b] !== infoBtn) allBtns[b].classList.remove("active");
            }
            /* Toggle this one */
            tooltip.classList.toggle("visible");
            infoBtn.classList.toggle("active");
            return;
        }

        /* Click outside tooltip closes it */
        if (!e.target.closest(".field-tooltip")) {
            var openTips = configEl.querySelectorAll(".field-tooltip.visible");
            var activeBtns = configEl.querySelectorAll(".btn-field-info.active");
            for (var i = 0; i < openTips.length; i++) openTips[i].classList.remove("visible");
            for (var j = 0; j < activeBtns.length; j++) activeBtns[j].classList.remove("active");
        }
    });

    var schedEl = document.getElementById("memory-schedule-content");
    if (schedEl) {
        schedEl.addEventListener("click", function(e) {
            var btn = e.target.closest("#btn-save-schedule");
            if (btn) { saveMemorySchedule(); return; }

            var infoBtn = e.target.closest(".btn-field-info[data-sched-info-key]");
            if (infoBtn) {
                var sKey = infoBtn.dataset.schedInfoKey;
                var tooltip = document.getElementById("tooltip-sched-" + sKey);
                if (!tooltip) return;
                /* Close any other open tooltips in schedule */
                var allTips = schedEl.querySelectorAll(".field-tooltip.visible");
                var allBtns = schedEl.querySelectorAll(".btn-field-info.active");
                for (var t = 0; t < allTips.length; t++) {
                    if (allTips[t] !== tooltip) allTips[t].classList.remove("visible");
                }
                for (var b = 0; b < allBtns.length; b++) {
                    if (allBtns[b] !== infoBtn) allBtns[b].classList.remove("active");
                }
                tooltip.classList.toggle("visible");
                infoBtn.classList.toggle("active");
                return;
            }

            /* Click outside tooltip closes it */
            if (!e.target.closest(".field-tooltip")) {
                var openTips = schedEl.querySelectorAll(".field-tooltip.visible");
                var activeBtns = schedEl.querySelectorAll(".btn-field-info.active");
                for (var i = 0; i < openTips.length; i++) openTips[i].classList.remove("visible");
                for (var j = 0; j < activeBtns.length; j++) activeBtns[j].classList.remove("active");
            }
        });
        /* Toggle enable/disable — update row opacity + time input */
        schedEl.addEventListener("change", function(e) {
            var toggle = e.target.closest("[data-sched-field='enabled']");
            if (toggle) {
                var row = toggle.closest("tr");
                var timeInput = row ? row.querySelector("[data-sched-field='time']") : null;
                if (row) row.style.opacity = toggle.checked ? "1" : "0.45";
                if (timeInput) timeInput.disabled = !toggle.checked;
            }
        });
    }
}

/* -- Main loader ---------------------------------------------------- */

async function loadMemory() {
    _bindMemoryDelegation();
    var btnRefresh = document.getElementById("btn-memory-refresh");
    if (btnRefresh) btnRefresh.disabled = true;

    try {
        var [status, guidance, contradictions, feedback, metacog] = await Promise.allSettled([
            apiFetch("/memory/status"),
            apiFetch("/memory/guidance"),
            apiFetch("/memory/contradictions"),
            apiFetch("/memory/feedback"),
            apiFetch("/memory/metacognition"),
        ]);

        memoryStatusData = status.status === "fulfilled" ? status.value : null;

        renderMemoryStatus(status);
        renderMemoryOverviewCards(status, metacog, feedback);

        if (guidance.status === "fulfilled") {
            memoryGuidanceData = guidance.value.items || [];
            filterAndRenderGuidance();
        } else {
            document.getElementById("memory-guidance-content").innerHTML =
                renderError("Could not load guidance data");
        }

        if (contradictions.status === "fulfilled") {
            memoryContradictionsData = contradictions.value.contradictions || [];
            renderMemoryContradictions();
        } else {
            document.getElementById("memory-contradictions-content").innerHTML =
                renderError("Could not load contradictions");
        }

        renderMemoryConfig();
        loadMemorySchedule();
    } catch (err) {
        showToast("Failed to load memory: " + err.message, "error");
    } finally {
        if (btnRefresh) btnRefresh.disabled = false;
    }
}
window.loadMemory = loadMemory;

/* -- Status Banner -------------------------------------------------- */

function renderMemoryStatus(result) {
    var banner = document.getElementById("memory-status-banner");
    var textEl = document.getElementById("memory-status-text");
    var metaEl = document.getElementById("memory-status-meta");
    if (!banner || !textEl) return;

    if (result.status === "rejected") {
        banner.className = "health-banner banner-critical";
        textEl.textContent = "Failed to load memory status";
        if (metaEl) metaEl.textContent = "";
        return;
    }

    var d = result.value;
    if (!d.initialized) {
        banner.className = "health-banner banner-warn";
        textEl.textContent = "Memory system not initialized — start a conversation to begin";
        if (metaEl) metaEl.textContent = "";
        return;
    }

    var allEnabled = d.type1_enabled && d.metacog_enabled;
    var anyEnabled = d.type1_enabled || d.metacog_enabled;
    var count = d.guidance_count || 0;
    var indexed = d.metacog_doc_count || 0;

    if (allEnabled && count > 0) {
        banner.className = "health-banner banner-ok";
        textEl.textContent = "Memory system active \u2014 " + count + " guidance items, " + indexed + " indexed documents";
    } else if (anyEnabled) {
        banner.className = "health-banner banner-warn";
        var parts = [];
        if (!d.type1_enabled) parts.push("Type 1 disabled");
        if (!d.metacog_enabled) parts.push("Metacognition disabled");
        textEl.textContent = "Partially enabled \u2014 " + parts.join(", ");
    } else {
        banner.className = "health-banner banner-critical";
        textEl.textContent = "Memory system disabled";
    }

    if (metaEl) {
        var pending = d.contradiction_count || 0;
        metaEl.textContent = pending > 0 ? pending + " contradiction(s) pending" : "";
    }
}

/* -- Overview Cards ------------------------------------------------- */

function renderMemoryOverviewCards(statusResult, metacogResult, feedbackResult) {
    /* Type 1 card */
    var t1 = document.getElementById("memory-type1-content");
    if (t1) {
        if (statusResult.status === "fulfilled") {
            var d = statusResult.value;
            var dotClass = d.type1_enabled ? "green" : "red";
            var label = d.type1_enabled ? "Enabled" : "Disabled";
            t1.innerHTML =
                '<div class="stat-row"><span class="stat-label">Status</span>' +
                '<span class="stat-value"><span class="status-dot ' + dotClass + '"></span> ' + label + '</span></div>' +
                '<div class="stat-row"><span class="stat-label">Items</span>' +
                '<span class="stat-value">' + (d.type1_count || 0) + '</span></div>' +
                '<div class="stat-row"><span class="stat-label">Char budget</span>' +
                '<span class="stat-value text-dim">2,000</span></div>';
        } else {
            t1.innerHTML = '<span class="text-dim">Unavailable</span>';
        }
    }

    /* Type 2 card */
    var t2 = document.getElementById("memory-type2-content");
    if (t2) {
        if (statusResult.status === "fulfilled") {
            var d2 = statusResult.value;
            var unified = d2.unified_enabled;
            t2.innerHTML =
                '<div class="stat-row"><span class="stat-label">Unified merge</span>' +
                '<span class="stat-value"><span class="status-dot ' + (unified ? "green" : "red") + '"></span> ' + (unified ? "On" : "Off") + '</span></div>' +
                '<div class="stat-row"><span class="stat-label">Items</span>' +
                '<span class="stat-value">' + (d2.type2_count || 0) + '</span></div>' +
                '<div class="stat-row"><span class="stat-label">Cooldown</span>' +
                '<span class="stat-value text-dim">300s</span></div>';
        } else {
            t2.innerHTML = '<span class="text-dim">Unavailable</span>';
        }
    }

    /* Metacognition card */
    var mc = document.getElementById("memory-metacog-content");
    if (mc) {
        if (metacogResult.status === "fulfilled") {
            var m = metacogResult.value;
            var sizeStr = m.index_size_bytes > 0 ? formatBytes(m.index_size_bytes) : "—";
            var builtStr = m.last_built ? timeAgo(m.last_built) : "Never";
            var cats = m.categories || {};
            var catParts = [];
            for (var c in cats) catParts.push(c + ": " + cats[c]);
            mc.innerHTML =
                '<div class="stat-row"><span class="stat-label">Documents</span>' +
                '<span class="stat-value">' + (m.doc_count || 0) + '</span></div>' +
                '<div class="stat-row"><span class="stat-label">Index size</span>' +
                '<span class="stat-value">' + sizeStr + '</span></div>' +
                '<div class="stat-row"><span class="stat-label">Last built</span>' +
                '<span class="stat-value text-dim">' + esc(builtStr) + '</span></div>' +
                (catParts.length > 0 ? '<div class="stat-row"><span class="stat-label">Categories</span>' +
                '<span class="stat-value text-dim" style="font-size:11px">' + esc(catParts.join(", ")) + '</span></div>' : '');
        } else {
            mc.innerHTML = '<span class="text-dim">Unavailable</span>';
        }
    }

    /* Feedback card */
    var fb = document.getElementById("memory-feedback-content");
    if (fb) {
        if (feedbackResult.status === "fulfilled") {
            var f = feedbackResult.value;
            var items = f.items || [];
            var avgHit = 0;
            if (items.length > 0) {
                var sum = 0;
                for (var i = 0; i < items.length; i++) sum += items[i].hit_rate || 0;
                avgHit = (sum / items.length * 100).toFixed(1);
            }
            fb.innerHTML =
                '<div class="stat-row"><span class="stat-label">Evaluations</span>' +
                '<span class="stat-value">' + (f.total_evaluations || 0) + '</span></div>' +
                '<div class="stat-row"><span class="stat-label">Tracked items</span>' +
                '<span class="stat-value">' + items.length + '</span></div>' +
                '<div class="stat-row"><span class="stat-label">Avg hit rate</span>' +
                '<span class="stat-value">' + (items.length > 0 ? avgHit + "%" : "\u2014") + '</span></div>';
        } else {
            fb.innerHTML = '<span class="text-dim">No feedback data collected</span>';
        }
    }
}

/* -- Guidance Table ------------------------------------------------- */

function filterAndRenderGuidance() {
    var typeFilter = document.getElementById("memory-guidance-filter");
    var pathFilter = document.getElementById("memory-pathway-filter");
    var type = typeFilter ? typeFilter.value : "all";
    var path = pathFilter ? pathFilter.value : "all";

    var filtered = memoryGuidanceData.filter(function(it) {
        if (type !== "all" && (it.type || "") !== type) return false;
        if (path !== "all" && (it.pathway || "") !== path) return false;
        return true;
    });

    renderMemoryGuidanceTable(filtered);
}
window.filterAndRenderGuidance = filterAndRenderGuidance;

function renderMemoryGuidanceTable(items) {
    var el = document.getElementById("memory-guidance-content");
    if (!el) return;

    if (!items || items.length === 0) {
        el.innerHTML = '<div class="text-dim" style="padding:16px;">No guidance items' +
            (memoryGuidanceData.length > 0 ? ' match the current filter.' : ' yet. Items are extracted automatically from conversations.') +
            '</div>';
        return;
    }

    var html = '<div style="overflow-x:auto; max-height:600px; overflow-y:auto;">' +
        '<table class="tls-table"><thead><tr>' +
        '<th>Type</th><th>Path</th><th>Text</th><th>Conf</th><th>Inj</th><th>Age</th><th></th>' +
        '</tr></thead><tbody>';

    for (var i = 0; i < items.length; i++) {
        var it = items[i];
        var origIdx = memoryGuidanceData.indexOf(it);
        var typeClass = (it.type || "pending").toLowerCase();
        var pathClass = (it.pathway || "type2").toLowerCase();
        var text = it.text || it.enforce || it.context || "";
        var preview = text.length > 120 ? text.substring(0, 120) + "\u2026" : text;
        var conf = it.confidence != null ? Math.round(it.confidence * 100) + "%" : "\u2014";
        var inj = it.injection_count || 0;
        var age = it.created_at ? timeAgo(it.created_at) : "\u2014";

        html += '<tr>' +
            '<td><span class="memory-type-badge ' + esc(typeClass) + '">' + esc(it.type || "pending") + '</span></td>' +
            '<td><span class="memory-pathway-badge ' + esc(pathClass) + '">' + esc(it.pathway || "type2") + '</span></td>' +
            '<td class="memory-item-expand"><span class="memory-item-text">' + esc(preview) + '</span>' +
            (text.length > 120 ? '<div class="memory-item-full">' + esc(text) + '</div>' : '') + '</td>' +
            '<td class="mono" style="font-size:12px">' + conf + '</td>' +
            '<td class="mono" style="font-size:12px">' + inj + '</td>' +
            '<td class="text-dim" style="font-size:12px; white-space:nowrap">' + esc(age) + '</td>' +
            '<td><button class="btn btn-ghost btn-sm" style="color:var(--red); padding:2px 6px; font-size:11px;" ' +
            'data-action="delete-guidance" data-idx="' + origIdx + '">\u2715</button></td>' +
            '</tr>';
    }

    html += '</tbody></table></div>';
    html += '<div class="text-dim" style="font-size:11px; margin-top:8px; padding:0 4px;">' +
        'Showing ' + items.length + ' of ' + memoryGuidanceData.length + ' items' +
        '</div>';
    el.innerHTML = html;
}

/* -- Guidance Actions ----------------------------------------------- */

async function deleteGuidanceItem(index) {
    if (!confirm("Delete this guidance item? This cannot be undone.")) return;

    try {
        var result = await apiFetch("/memory/guidance/" + index, { method: "DELETE" });
        showToast("Item deleted (" + result.remaining + " remaining)", "success");
        /* Reload guidance + status */
        var [status, guidance] = await Promise.all([
            apiFetch("/memory/status"),
            apiFetch("/memory/guidance"),
        ]);
        memoryStatusData = status;
        memoryGuidanceData = guidance.items || [];
        renderMemoryStatus({ status: "fulfilled", value: status });
        filterAndRenderGuidance();
    } catch (err) {
        showToast("Delete failed: " + err.message, "error");
    }
}
window.deleteGuidanceItem = deleteGuidanceItem;

/* -- Contradictions ------------------------------------------------- */

function renderMemoryContradictions() {
    var el = document.getElementById("memory-contradictions-content");
    var countEl = document.getElementById("memory-contradiction-count");
    if (!el) return;

    var pending = memoryContradictionsData.filter(function(c) {
        return c.status === "pending" || !c.status;
    });

    if (countEl) {
        countEl.textContent = pending.length > 0 ? "(" + pending.length + " pending)" : "";
    }

    if (pending.length === 0) {
        el.innerHTML = '<div class="text-dim" style="padding:16px;">No pending contradictions.</div>';
        return;
    }

    var html = "";
    for (var i = 0; i < memoryContradictionsData.length; i++) {
        var c = memoryContradictionsData[i];
        if (c.status && c.status !== "pending") continue;

        var aText = (c.claim_a && c.claim_a.text) ? c.claim_a.text : (c.text_a || "Claim A");
        var bText = (c.claim_b && c.claim_b.text) ? c.claim_b.text : (c.text_b || "Claim B");
        var aPreview = aText.length > 150 ? aText.substring(0, 150) + "\u2026" : aText;
        var bPreview = bText.length > 150 ? bText.substring(0, 150) + "\u2026" : bText;
        var sim = c.similarity != null ? (c.similarity * 100).toFixed(1) + "%" : "\u2014";
        var flagged = c.flagged ? timeAgo(c.flagged) : "\u2014";

        html += '<div class="contradiction-card" data-idx="' + i + '">' +
            '<div class="contradiction-claims">' +
            '<div class="contradiction-claim"><div class="text-dim" style="font-size:10px; margin-bottom:4px;">CLAIM A</div>' +
            '<div style="font-size:12px;">' + esc(aPreview) + '</div></div>' +
            '<div class="contradiction-vs">vs</div>' +
            '<div class="contradiction-claim"><div class="text-dim" style="font-size:10px; margin-bottom:4px;">CLAIM B</div>' +
            '<div style="font-size:12px;">' + esc(bPreview) + '</div></div>' +
            '</div>' +
            '<div style="display:flex; justify-content:space-between; align-items:center;">' +
            '<span class="text-dim" style="font-size:11px;">Similarity: ' + sim + ' &middot; Flagged: ' + esc(flagged) + '</span>' +
            '<div class="contradiction-actions">' +
            '<button class="btn btn-ghost btn-sm" data-action="resolve" data-idx="' + i + '" data-resolution="keep_a">Keep A</button>' +
            '<button class="btn btn-ghost btn-sm" data-action="resolve" data-idx="' + i + '" data-resolution="keep_b">Keep B</button>' +
            '<button class="btn btn-ghost btn-sm" data-action="resolve" data-idx="' + i + '" data-resolution="keep_both">Keep Both</button>' +
            '<button class="btn btn-ghost btn-sm" style="color:var(--dim);" data-action="resolve" data-idx="' + i + '" data-resolution="dismiss">Dismiss</button>' +
            '</div></div></div>';
    }

    el.innerHTML = html;
}

async function resolveContradiction(index, action) {
    try {
        var result = await apiFetch("/memory/contradictions/" + index + "/resolve", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ action: action }),
        });

        showToast("Resolved: " + action.replace("_", " ") + " (" + result.remaining_pending + " remaining)", "success");

        /* Remove from local data and re-render */
        if (memoryContradictionsData[index]) {
            memoryContradictionsData[index].status = "resolved";
            memoryContradictionsData[index].resolution = action;
        }
        renderMemoryContradictions();

        /* If keep_a or keep_b, guidance may have changed */
        if (action === "keep_a" || action === "keep_b") {
            var guidance = await apiFetch("/memory/guidance");
            memoryGuidanceData = guidance.items || [];
            filterAndRenderGuidance();
        }
    } catch (err) {
        showToast("Resolve failed: " + err.message, "error");
    }
}
window.resolveContradiction = resolveContradiction;

/* -- Metacognition Search ------------------------------------------- */

async function memorySearch() {
    var input = document.getElementById("memory-search-input");
    var resultsEl = document.getElementById("memory-search-results");
    if (!input || !resultsEl) return;

    var query = input.value.trim();
    if (!query) {
        showToast("Enter a query to search", "warning");
        return;
    }

    var btn = document.getElementById("btn-memory-search");
    if (btn) btn.disabled = true;
    resultsEl.innerHTML = '<div class="loading-overlay"><div class="spinner"></div> Searching...</div>';

    try {
        var result = await apiFetch("/memory/metacognition/search", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ query: query }),
        });

        var html = '';

        if (result.pre_think_keywords) {
            html += '<div style="margin-bottom:12px;">' +
                '<span class="text-dim" style="font-size:11px;">Keywords: </span>' +
                '<span class="mono" style="font-size:12px; color:var(--accent);">' + esc(result.pre_think_keywords) + '</span>' +
                '<span class="text-dim" style="font-size:11px; margin-left:12px;">' + (result.elapsed_ms || 0) + 'ms</span>' +
                '</div>';
        }

        if (!result.should_retrieve) {
            html += '<div class="text-dim" style="padding:8px 0;">Message classified as non-substantive (too short or trivial). Retrieval skipped.</div>';
            resultsEl.innerHTML = html;
            return;
        }

        var results = result.results || [];
        if (results.length === 0) {
            html += '<div class="text-dim" style="padding:8px 0;">No matching documents found above similarity threshold.</div>';
            resultsEl.innerHTML = html;
            return;
        }

        for (var i = 0; i < results.length; i++) {
            var r = results[i];
            var scorePct = Math.round((r.score || 0) * 100);
            html += '<div class="memory-search-result">' +
                '<div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:6px;">' +
                '<div>' +
                '<span class="memory-type-badge ' + esc(r.category || "unknown") + '">' + esc(r.category || "unknown") + '</span>' +
                (r.source ? ' <span class="text-dim" style="font-size:11px;">' + esc(r.source) + '</span>' : '') +
                '</div>' +
                '<span class="mono" style="font-size:12px; color:var(--accent);">' + scorePct + '%</span>' +
                '</div>' +
                '<div class="memory-score-bar"><div class="memory-score-fill" style="width:' + scorePct + '%;"></div></div>' +
                '<div style="font-size:12px; color:var(--text); margin-top:8px; white-space:pre-wrap; word-break:break-word;">' +
                esc(r.preview || "") + '</div>' +
                '</div>';
        }

        resultsEl.innerHTML = html;
    } catch (err) {
        resultsEl.innerHTML = renderError("Search failed: " + err.message);
    } finally {
        if (btn) btn.disabled = false;
    }
}
window.memorySearch = memorySearch;

/* -- Operations ----------------------------------------------------- */

async function memoryOperation(action) {
    var btn = document.getElementById("btn-memory-" + action.replace("_", "-"));
    var output = document.getElementById("memory-operations-output");
    if (btn) btn.disabled = true;
    if (output) output.innerHTML = '<div class="loading-overlay" style="position:relative; min-height:40px;"><div class="spinner"></div> Running ' + esc(action) + '...</div>';

    try {
        var result = await apiFetch("/memory/operations/" + action, { method: "POST" });

        var html = '<div style="background:var(--surface); border:1px solid var(--soft-border); border-radius:var(--radius, 8px); padding:12px; margin-top:8px;">';
        html += '<div style="font-size:12px; font-weight:600; color:var(--text); margin-bottom:8px;">' + esc(action) + ' completed</div>';

        if (result.candidates && result.candidates.length > 0) {
            html += '<div style="font-size:12px; color:var(--text); margin-bottom:8px;">' + esc(result.output || "") + '</div>';
            html += '<table class="tls-table"><thead><tr><th>Preview</th><th>Injections</th><th>Hit Rate</th></tr></thead><tbody>';
            for (var i = 0; i < result.candidates.length; i++) {
                var c = result.candidates[i];
                html += '<tr><td style="font-size:11px; max-width:400px; overflow:hidden; text-overflow:ellipsis; white-space:nowrap;">' +
                    esc(c.text_preview || "") + '</td>' +
                    '<td class="mono" style="font-size:12px">' + c.injection_count + '</td>' +
                    '<td class="mono" style="font-size:12px">' + (c.hit_rate * 100).toFixed(1) + '%</td></tr>';
            }
            html += '</tbody></table>';
        } else if (result.output) {
            html += '<pre style="font-size:11px; color:var(--dim); white-space:pre-wrap; word-break:break-word; max-height:300px; overflow-y:auto; margin:0;">' +
                esc(result.output) + '</pre>';
        }

        html += '</div>';
        if (output) output.innerHTML = html;

        /* Refresh metacog card after index rebuild */
        if (action === "rebuild_index") {
            var metacog = await apiFetch("/memory/metacognition");
            renderMemoryOverviewCards(
                { status: "fulfilled", value: memoryStatusData || {} },
                { status: "fulfilled", value: metacog },
                { status: "rejected" }
            );
        }

        showToast(action.replace(/_/g, " ") + " completed", "success");
    } catch (err) {
        if (output) output.innerHTML = renderError(action + " failed: " + err.message);
        showToast(action + " failed: " + err.message, "error");
    } finally {
        if (btn) btn.disabled = false;
    }
}
window.memoryOperation = memoryOperation;

/* -- Extraction Schedule --------------------------------------------- */

var memoryScheduleData = null;

async function loadMemorySchedule() {
    var el = document.getElementById("memory-schedule-content");
    if (!el) return;

    try {
        var result = await apiFetch("/memory/schedule");
        memoryScheduleData = result.jobs || [];
        renderMemorySchedule();
    } catch (err) {
        el.innerHTML = '<div class="text-dim" style="padding:16px;">Could not load schedule. Crontab may not be accessible.</div>';
    }
}

function renderMemorySchedule() {
    var el = document.getElementById("memory-schedule-content");
    if (!el) return;

    var jobs = memoryScheduleData || [];
    if (jobs.length === 0) {
        el.innerHTML = '<div class="text-dim" style="padding:16px;">No extraction pipeline scripts found in this install.</div>';
        return;
    }

    var anyInstalled = jobs.some(function(j) { return j.installed; });

    var html = '<div class="text-dim" style="font-size:11px; margin-bottom:12px;">' +
        'Nightly pipeline: DB Snapshot \u2192 Chatmine (extraction) \u2192 Batch Digest \u2192 Autodream (consolidation).' +
        (!anyInstalled ? ' No cron jobs installed yet \u2014 enable and save to create them.' : '') +
        '</div>';

    html += '<table class="tls-table"><thead><tr>' +
        '<th style="width:40px;"></th>' +
        '<th>Job</th>' +
        '<th style="width:120px;">Time</th>' +
        '<th style="width:80px;">Status</th>' +
        '</tr></thead><tbody>';

    for (var i = 0; i < jobs.length; i++) {
        var j = jobs[i];
        var canEnable = j.script_exists;
        var checked = j.enabled ? " checked" : "";
        var disableToggle = canEnable ? "" : " disabled";
        var hr = parseInt(j.hour, 10);
        var mn = parseInt(j.minute, 10);
        var timeVal = (hr < 10 ? "0" : "") + hr + ":" + (mn < 10 ? "0" : "") + mn;
        var dimClass = j.enabled ? "" : ' style="opacity:0.45;"';

        var statusBadge;
        if (!j.script_exists) {
            statusBadge = '<span class="text-dim" style="font-size:11px;">script missing</span>';
        } else if (!j.installed) {
            statusBadge = '<span style="font-size:11px; color:var(--yellow);">not installed</span>';
        } else if (j.enabled) {
            statusBadge = '<span style="font-size:11px; color:var(--green);">active</span>';
        } else {
            statusBadge = '<span class="text-dim" style="font-size:11px;">disabled</span>';
        }

        var baseKey = j.key.split("_").slice(0, j.key.indexOf("_") > 0 && ["prod","dev","claude","codex"].indexOf(j.key.split("_").pop()) >= 0 ? -1 : undefined).join("_");
        /* Fallback: strip trailing variant tokens for info lookup */
        var infoKey = baseKey;
        if (!SCHEDULE_JOB_INFO[infoKey]) {
            /* Try just the first token (e.g. "chatmine" from "chatmine_prod") */
            infoKey = j.key.split("_")[0];
        }
        var jobInfo = SCHEDULE_JOB_INFO[infoKey] || "";

        var infoBtnHtml = "";
        if (jobInfo) {
            infoBtnHtml = ' <button type="button" class="btn-field-info" data-sched-info-key="' + esc(j.key) + '" ' +
                'aria-label="More info" title="More info">i</button>' +
                '<div class="field-tooltip" id="tooltip-sched-' + esc(j.key) + '">' +
                '<div class="field-tooltip-arrow"></div>' + jobInfo + '</div>';
        }

        html += '<tr' + dimClass + '>' +
            '<td><div class="toggle-wrap" style="margin:0;"><label class="toggle">' +
            '<input type="checkbox" data-sched-key="' + esc(j.key) + '" data-sched-field="enabled"' + checked + disableToggle + '>' +
            '<div class="toggle-track" style="width:32px; height:18px;"></div>' +
            '<div class="toggle-knob" style="width:12px; height:12px; top:3px; left:3px;"></div>' +
            '</label></div></td>' +
            '<td><div class="form-label-row" style="position:relative;"><span style="font-size:13px;">' + esc(j.label) + '</span>' +
            infoBtnHtml + '</div>' +
            '<div class="text-dim" style="font-size:11px;">' + esc(j.description || "") + '</div></td>' +
            '<td><input type="time" value="' + timeVal + '" ' +
            'data-sched-key="' + esc(j.key) + '" data-sched-field="time" ' +
            'style="background:var(--bg); border:1px solid var(--card); color:var(--text); padding:4px 8px; border-radius:6px; font-size:12px; width:100px;"' +
            (j.enabled ? "" : " disabled") + '></td>' +
            '<td>' + statusBadge + '</td>' +
            '</tr>';
    }

    html += '</tbody></table>';
    html += '<div class="config-actions">' +
        '<button class="btn btn-primary" id="btn-save-schedule">' +
        '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" width="14" height="14">' +
        '<path d="M19 21H5a2 2 0 01-2-2V5a2 2 0 012-2h11l5 5v11a2 2 0 01-2 2z"/>' +
        '<polyline points="17 21 17 13 7 13 7 21"/>' +
        '<polyline points="7 3 7 8 15 8"/>' +
        '</svg> Save Schedule' +
        '</button>' +
        '</div>';

    el.innerHTML = html;
}

async function saveMemorySchedule() {
    var el = document.getElementById("memory-schedule-content");
    if (!el) return;

    var updates = {};
    var toggles = el.querySelectorAll("[data-sched-field='enabled']");
    for (var i = 0; i < toggles.length; i++) {
        var key = toggles[i].dataset.schedKey;
        if (!updates[key]) updates[key] = {};
        updates[key].enabled = toggles[i].checked;
    }

    var times = el.querySelectorAll("[data-sched-field='time']");
    for (var i = 0; i < times.length; i++) {
        var key = times[i].dataset.schedKey;
        if (!updates[key]) updates[key] = {};
        var parts = (times[i].value || "0:0").split(":");
        updates[key].hour = parseInt(parts[0], 10);
        updates[key].minute = parseInt(parts[1], 10);
    }

    var btn = document.getElementById("btn-save-schedule");
    if (btn) btn.disabled = true;

    try {
        var result = await apiFetch("/memory/schedule", {
            method: "PUT",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ jobs: updates }),
        });
        memoryScheduleData = result.jobs || [];
        renderMemorySchedule();
        showToast("Schedule updated", "success");
    } catch (err) {
        showToast("Failed to save schedule: " + err.message, "error");
    } finally {
        if (btn) btn.disabled = false;
    }
}

/* -- Config Form ---------------------------------------------------- */

var SCHEDULE_JOB_INFO = {
    "db_snapshot": "Creates a point-in-time backup of your conversation database before the extraction pipeline runs. This ensures you have a safe rollback point in case anything goes wrong during knowledge extraction. <strong>Always schedule this before chatmine.</strong>",
    "chatmine": "Scans recent conversation transcripts and uses an LLM to extract actionable knowledge \u2014 corrections, decisions, preferences, and invariant rules. Extracted items are added to your guidance store for future conversations. <strong>This is the primary knowledge acquisition step.</strong>",
    "batch_digest": "Processes any conversation sessions that chatmine may have missed, sweeping up remaining knowledge into guidance items. Acts as a catch-all to ensure no useful knowledge slips through the cracks. <strong>Runs after chatmine to fill gaps.</strong>",
    "autodream": "Consolidates and prunes your guidance store overnight. Merges related items, removes expired or low-value entries, resolves duplicates, and rebuilds the semantic search index. <strong>Keeps your knowledge base lean and relevant over time.</strong>",
};

var MEMORY_FIELD_INFO = {
    "enable_type1": "Controls the always-on procedural memory pathway. When enabled, your most important rules and corrections are injected into <strong>every</strong> conversation turn automatically. Disable only if you want the system to stop applying invariant rules.",
    "enable_unified_memory": "Merges knowledge from multiple sources (extractions, corrections, decisions) into one coherent context block each turn. Disabling limits memory to individual source lookups, which may miss connections between related knowledge.",
    "enable_metacognition": "Controls AI-powered semantic search over your knowledge index. When enabled, the system finds relevant past knowledge based on conversation context. Disabling removes the retrieval layer \u2014 the system will only use always-on rules.",
    "type1_max_items": "<strong>Higher:</strong> more rules applied per turn, but uses more of the context window. <strong>Lower:</strong> only the most relevant rules survive. A good starting point is 10; go higher if important rules aren\u2019t firing, lower if responses feel over-constrained.",
    "type1_max_chars": "Character budget for the entire Type 1 block. <strong>Higher:</strong> more detailed rules can be injected, but each turn uses more of the context window. <strong>Lower:</strong> rules are summarized more aggressively and may be dropped to fit the budget.",
    "type2_max_chars": "Character budget for declarative knowledge injection. <strong>Higher:</strong> richer context from past conversations. <strong>Lower:</strong> saves context window for the current conversation. Balance based on how much prior knowledge matters for your use case.",
    "whisper_interval": "Cooldown between Type 2 memory injections in seconds. <strong>Higher (e.g. 600):</strong> less frequent refreshes, saves tokens. <strong>Lower (e.g. 60):</strong> more responsive to topic changes but costs more. 300s (5 min) works well for most conversations.",
    "promotion_min_injections": "How many times an item must be injected before it can be promoted to always-on invariant status. <strong>Higher:</strong> stricter \u2014 only well-tested items promote. <strong>Lower:</strong> faster promotion, but risks promoting premature patterns.",
    "promotion_min_hit_rate": "Minimum usefulness rate for promotion to invariant. <strong>Higher (e.g. 80%):</strong> only consistently useful items promote. <strong>Lower (e.g. 40%):</strong> more lenient. Items below this rate remain in the Type 2 pool.",
    "guidance_max_chars": "Total character budget across all stored guidance items. <strong>Higher:</strong> retains more knowledge but slows lookups. <strong>Lower:</strong> forces pruning of older items sooner. When the system seems to forget things you\u2019ve taught it, this budget may be too tight.",
    "guidance_max_age_days": "How long non-invariant items survive before automatic pruning. <strong>Higher:</strong> longer memory retention. <strong>Lower:</strong> fresher, more relevant knowledge. Invariants use a separate, longer TTL.",
    "invariant_ttl_days": "How long always-on invariant items persist. These are your most important rules so they get a longer TTL. <strong>Higher:</strong> rules persist longer. <strong>Lower:</strong> rules need re-validation more often.",
    "invariant_confidence_threshold": "Minimum confidence score for an item to pass invariant validation. <strong>Higher (e.g. 90%):</strong> very strict, fewer invariants qualify. <strong>Lower (e.g. 50%):</strong> more items qualify. A low threshold lets more rules stick around; a high one only keeps the ones the system is very sure about.",
    "similarity_threshold": "Minimum similarity score for metacognition search to return a result. <strong>Higher:</strong> only very relevant matches, but may miss useful context. <strong>Lower:</strong> more results returned, but some may be tangential. 35% is a good baseline for broad recall.",
    "metacog_max_results": "Maximum results per metacognition query. <strong>Higher:</strong> more context injected but uses more tokens. <strong>Lower:</strong> only the single best match. 2\u20133 works well for most conversations.",
    "embedding_backend": "Which backend generates embeddings for semantic search. <strong>Gemini:</strong> Google\u2019s API \u2014 fast, accurate, requires API key. <strong>Ollama:</strong> runs locally \u2014 private, no API costs, but slower.",
    "extraction_model": "The Ollama model used to extract knowledge from conversations. Larger models (e.g. 26b) extract more nuanced knowledge but run slower. Requires Ollama running locally with this model pulled.",
    "prethinker_model": "The lightweight Ollama model that extracts keywords before semantic search. Determines <em>what to search for</em>. Smaller models (e.g. 8b) are faster, which matters since this runs in the hot path of every substantive turn.",
};

var memoryBackendsData = null;

function renderMemoryConfig() {
    var el = document.getElementById("memory-config-content");
    if (!el) return;

    var fetches = [];
    if (!configSchema || !configSchema.memory) {
        fetches.push(apiFetch("/config/schema").then(function(r) {
            configSchema = r.schema || r;
        }));
        fetches.push(apiFetch("/config").then(function(r) {
            configValues = r.config || r;
        }));
    }
    fetches.push(apiFetch("/memory/backends").then(function(r) {
        memoryBackendsData = r;
    }).catch(function() {
        memoryBackendsData = null;
    }));

    if (fetches.length > 0) {
        Promise.all(fetches).then(function() {
            _renderMemoryConfigFields();
        }).catch(function() {
            el.innerHTML = '<span class="text-dim">Could not load config schema</span>';
        });
        return;
    }

    _renderMemoryConfigFields();
}

function _renderBackendSelect(key, spec, currentVal) {
    /* Render embedding_backend / extraction_model / prethinker_model
       as dynamic dropdowns driven by memoryBackendsData. */
    var fieldId = "field-memory-" + key;
    var b = memoryBackendsData || {};

    if (key === "embedding_backend") {
        var choices = b.embedding_choices || [];
        var h = '<select id="' + fieldId + '" data-config-field="1" data-section="memory" data-key="' + esc(key) + '">';
        for (var i = 0; i < choices.length; i++) {
            var c = choices[i];
            var sel = (String(currentVal) === c.value) ? " selected" : "";
            var dis = !c.available ? " disabled" : "";
            h += '<option value="' + esc(c.value) + '"' + sel + dis + '>' + esc(c.label) + '</option>';
        }
        if (choices.length === 0) {
            h += '<option disabled selected>No backends available</option>';
        }
        h += '</select>';
        return h;
    }

    /* extraction_model / prethinker_model — Ollama model dropdown */
    var models = b.ollama_models || [];
    var ollamaUp = b.ollama_available;

    if (!ollamaUp) {
        return '<select id="' + fieldId + '" data-config-field="1" data-section="memory" data-key="' + esc(key) + '" disabled>' +
            '<option value="' + esc(currentVal) + '" selected>' + esc(currentVal) + ' (Ollama not reachable)</option>' +
            '</select>';
    }

    var h = '<select id="' + fieldId + '" data-config-field="1" data-section="memory" data-key="' + esc(key) + '">';
    var foundCurrent = false;
    for (var i = 0; i < models.length; i++) {
        var m = models[i];
        var sel = (m === currentVal) ? " selected" : "";
        if (m === currentVal) foundCurrent = true;
        h += '<option value="' + esc(m) + '"' + sel + '>' + esc(m) + '</option>';
    }
    /* If current value isn't in the list (e.g. model was removed), still show it */
    if (!foundCurrent && currentVal) {
        h = '<option value="' + esc(currentVal) + '" selected>' + esc(currentVal) + ' (not installed)</option>' + h;
    }
    h += '</select>';
    return h;
}

var _BACKEND_FIELDS = {"embedding_backend": 1, "extraction_model": 1, "prethinker_model": 1};

function _renderMemoryConfigFields() {
    var el = document.getElementById("memory-config-content");
    if (!el || !configSchema || !configSchema.memory) return;

    var schema = configSchema.memory;
    var values = (configValues && configValues.memory) || {};
    var html = '<div class="memory-config-grid">';

    for (var key in schema) {
        if (schema[key].readonly) continue;
        var val = values[key] != null ? values[key] : schema[key].default;
        var fieldHtml;

        if (_BACKEND_FIELDS[key]) {
            /* Custom dynamic dropdown */
            fieldHtml = '<div class="form-field">' +
                '<label class="form-label" for="field-memory-' + esc(key) + '">' + esc(schema[key].description || key) + '</label>' +
                _renderBackendSelect(key, schema[key], val) +
                '</div>';
        } else {
            fieldHtml = renderFormField("memory", key, schema[key], val);
        }

        /* Inject info button into the label if we have help text */
        var info = MEMORY_FIELD_INFO[key];
        if (info) {
            var infoBtn = '<button type="button" class="btn-field-info" data-info-key="' + esc(key) + '" ' +
                'aria-label="More info" title="More info">i</button>' +
                '<div class="field-tooltip" id="tooltip-memory-' + esc(key) + '">' +
                '<div class="field-tooltip-arrow"></div>' + info + '</div>';
            /* Wrap label + info button in a flex row */
            fieldHtml = fieldHtml.replace(
                /<label class="form-label"/,
                '<div class="form-label-row" style="position:relative;"><label class="form-label"'
            );
            fieldHtml = fieldHtml.replace(
                /<\/label>/,
                '</label>' + infoBtn + '</div>'
            );
        }

        html += fieldHtml;
    }

    html += '<div class="config-actions">' +
        '<button class="btn btn-primary" id="btn-save-memory">' +
        '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" width="14" height="14">' +
        '<path d="M19 21H5a2 2 0 01-2-2V5a2 2 0 012-2h11l5 5v11a2 2 0 01-2 2z"/>' +
        '<polyline points="17 21 17 13 7 13 7 21"/>' +
        '<polyline points="7 3 7 8 15 8"/>' +
        '</svg> Save Memory Settings' +
        '</button>' +
        '<span class="restart-badge" id="restart-badge-memory">Restart required</span>' +
        '</div>';

    html += '</div>';
    el.innerHTML = html;
}

/* -- Helpers -------------------------------------------------------- */

function formatBytes(bytes) {
    if (bytes < 1024) return bytes + " B";
    if (bytes < 1048576) return (bytes / 1024).toFixed(1) + " KB";
    return (bytes / 1048576).toFixed(1) + " MB";
}

function timeAgo(isoStr) {
    if (!isoStr) return "\u2014";
    var then = new Date(isoStr);
    var now = new Date();
    var diff = Math.floor((now - then) / 1000);
    if (diff < 0) diff = 0;
    if (diff < 60) return diff + "s ago";
    if (diff < 3600) return Math.floor(diff / 60) + "m ago";
    if (diff < 86400) return Math.floor(diff / 3600) + "h ago";
    return Math.floor(diff / 86400) + "d ago";
}

"""
