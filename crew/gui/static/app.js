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
    // Reveal the progress strip (each theme has one of these).
    const strip = document.getElementById("standup-progress");
    if (strip) {
      strip.hidden = false;
      const body = strip.querySelector(".standup-progress-body");
      if (body) body.textContent = "";
    }
  });

  // ── Status polling via hx-trigger="every 30s" updates dot text only.
  document.body.addEventListener("htmx:afterRequest", (evt) => {
    if (!evt.detail.requestConfig) return;
    const path = evt.detail.requestConfig.path;

    if (path === "/status") {
      try {
        const data = JSON.parse(evt.detail.xhr.responseText);
        const dot = document.querySelector(".status-row .dot, .warm-dot.ok");
        const model = document.querySelector(".model");
        if (dot) {
          dot.classList.toggle("ok", !!data.online);
          dot.classList.toggle("off", !data.online);
        }
        if (model && typeof data.model === "string") {
          model.textContent = data.model;
        }
      } catch { /* ignore */ }
      return;
    }

    // After a chat-turn fragment is appended, scroll the log to the bottom.
    if (path === "/chat" || path.startsWith("/pinned/")) {
      const log = document.getElementById("chat-log");
      if (log) log.scrollTop = log.scrollHeight;
    }
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

  // ── SSE: subscribe to pipeline + chat events ─────────────────────────
  const findBubble = (messageId) => {
    const wrap = document.getElementById("chat-msg-" + messageId);
    if (!wrap) return null;
    return wrap.querySelector(".chat-stream");
  };

  if ("EventSource" in window) {
    const es = new EventSource("/events/stream");

    // Pipeline progress (standup regenerate).
    es.addEventListener("pipeline_progress", (ev) => {
      try {
        const d = JSON.parse(ev.data);
        const strip = document.getElementById("standup-progress");
        const body = strip ? strip.querySelector(".standup-progress-body") : null;
        if (d.state === "delta" && body) {
          body.textContent += d.delta || "";
          body.scrollTop = body.scrollHeight;
        } else if (d.state === "done") {
          flash("Standup updated.");
          if (strip) strip.hidden = true;
          if (window.htmx) {
            window.htmx.ajax("GET", "/standup/draft", {
              target: "#card-standup", swap: "outerHTML",
            });
          }
        } else if (d.state === "error") {
          flash(`Pipeline error: ${d.detail || "unknown"}`, "error");
          if (body) body.textContent += `\n[error] ${d.detail || "unknown"}\n`;
        }
      } catch { /* ignore */ }
    });

    es.addEventListener("output_updated", () => {
      if (window.htmx) {
        window.htmx.ajax("GET", "/standup/draft", {
          target: "#card-standup", swap: "outerHTML",
        });
      }
    });

    // Chat token stream.
    es.addEventListener("chat_token", (ev) => {
      try {
        const d = JSON.parse(ev.data);
        const bubble = findBubble(d.message_id);
        if (!bubble) return;
        bubble.textContent += d.delta || "";
        const log = document.getElementById("chat-log");
        if (log) log.scrollTop = log.scrollHeight;
      } catch { /* ignore */ }
    });

    es.addEventListener("chat_done", (ev) => {
      try {
        const d = JSON.parse(ev.data);
        const bubble = findBubble(d.message_id);
        if (!bubble) return;
        bubble.dataset.state = "done";
        if (typeof d.text === "string" && d.text && !bubble.textContent.trim()) {
          bubble.textContent = d.text;
        }
      } catch { /* ignore */ }
    });

    es.addEventListener("chat_error", (ev) => {
      try {
        const d = JSON.parse(ev.data);
        const bubble = findBubble(d.message_id);
        if (bubble) {
          bubble.dataset.state = "error";
          bubble.textContent = (d.detail || "error").toString();
        }
        flash(`Chat error: ${d.detail || "unknown"}`, "error");
      } catch { /* ignore */ }
    });

    es.onerror = () => { /* keep browser's auto-reconnect */ };
  }
})();
