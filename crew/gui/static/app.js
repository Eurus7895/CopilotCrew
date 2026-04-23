// Crew GUI client — HTMX augments, scrubber keyboard nav, SSE tap, status poll.

(() => {
  "use strict";

  const flash = (msg, level = "info") => {
    const el = document.getElementById("flash");
    if (!el) return;
    el.className = "flash visible " + (level === "info" ? "" : level);
    el.textContent = msg;
    clearTimeout(flash._t);
    flash._t = setTimeout(() => el.classList.remove("visible"), 2600);
  };

  // ── HTMX: expose server-side 409 / hx-trigger events ─────────────────
  document.body.addEventListener("htmx:responseError", (evt) => {
    const xhr = evt.detail.xhr;
    if (xhr.status === 409) {
      flash("Already running — wait for the current run to finish.", "warn");
    } else {
      flash(`Error (${xhr.status}) — check the server log.`, "error");
    }
  });

  document.body.addEventListener("standup-started", () => {
    flash("Regenerating standup draft…");
  });

  // ── Status polling via hx-trigger="every 30s" updates dot text only.
  // We refresh the DOM by swapping innerHTML of .status-row manually.
  document.body.addEventListener("htmx:afterRequest", async (evt) => {
    if (!evt.detail.requestConfig) return;
    const path = evt.detail.requestConfig.path;
    if (path !== "/status") return;
    try {
      const data = JSON.parse(evt.detail.xhr.responseText);
      const dot = document.querySelector(".status-row .dot");
      const model = document.querySelector(".status-row .model");
      if (dot) {
        dot.classList.toggle("ok", !!data.online);
        dot.classList.toggle("off", !data.online);
      }
      if (model && typeof data.model === "string") {
        model.textContent = data.model;
      }
    } catch { /* ignore */ }
  });

  // ── Keyboard scrubber: arrow keys move through the left-rail timeline.
  const navByDelta = (delta) => {
    const rows = Array.from(document.querySelectorAll(".today-row"));
    if (!rows.length) return;
    const selectedIdx = rows.findIndex((r) => r.classList.contains("selected"));
    const target = rows[Math.min(Math.max(selectedIdx + delta, 0), rows.length - 1)];
    if (target && target !== rows[selectedIdx]) target.click();
  };
  document.addEventListener("keydown", (ev) => {
    if (ev.target instanceof HTMLInputElement || ev.target instanceof HTMLTextAreaElement) return;
    if (ev.key === "ArrowDown" || ev.key === "j") { ev.preventDefault(); navByDelta(+1); }
    if (ev.key === "ArrowUp"   || ev.key === "k") { ev.preventDefault(); navByDelta(-1); }
  });

  // ── SSE: subscribe to pipeline progress / output updates.
  if ("EventSource" in window) {
    const es = new EventSource("/events/stream");
    es.addEventListener("pipeline_progress", (ev) => {
      try {
        const d = JSON.parse(ev.data);
        if (d.state === "done") {
          flash("Standup updated.");
          // Refresh the draft card in place.
          if (window.htmx) {
            window.htmx.ajax("GET", "/standup/draft", { target: "#card-standup", swap: "outerHTML" });
          }
        } else if (d.state === "error") {
          flash(`Pipeline error: ${d.detail || "unknown"}`, "error");
        }
      } catch { /* ignore */ }
    });
    es.addEventListener("output_updated", () => {
      if (window.htmx) {
        window.htmx.ajax("GET", "/standup/draft", { target: "#card-standup", swap: "outerHTML" });
      }
    });
    es.onerror = () => { /* keep browser's auto-reconnect */ };
  }
})();
