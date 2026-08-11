/*
 * Ticker search — over tickers that have actually been analyzed (see
 * data/processed/analyzed_calls.db), not a fixed universe. Any ticker can
 * be analyzed, but only via an active Claude Code session (no standalone
 * API key configured for this tool -- see known_issues.yaml), so a search
 * for a ticker nobody's analyzed yet can't trigger analysis itself. Instead
 * it shows a clear "not analyzed yet" state with a copyable prompt, rather
 * than a dead end or a fake result.
 *
 * Reads assets/search-index.json (built by src/site/build.py from
 * analyzed_calls.db -- never fetched live, never hits
 * stockanalysis.com/fool.com from the browser).
 *
 * Initializes every `.ticker-search` container on the page independently
 * (the hero search on Overview and the compact nav search on every page
 * both use this same script, each with its own input/panel/state) rather
 * than assuming a single fixed instance.
 */
(function () {
  const script = document.currentScript;
  const indexUrl = script.getAttribute("data-search-index");
  const baseHref = script.getAttribute("data-base-href") || "";

  let tickersPromise = fetch(indexUrl)
    .then((r) => r.json())
    .catch(() => []);

  function initInstance(container, idx) {
    const input = container.querySelector("input");
    const panel = container.querySelector(".ticker-search-panel");
    if (!input || !panel) return;

    // give each instance's panel a unique id for aria-controls, in case
    // more than one search box is on the page at once (hero + nav)
    if (!panel.id) panel.id = "ticker-search-panel-" + idx;
    input.setAttribute("aria-controls", panel.id);

    let tickers = [];
    let activeIndex = -1;

    tickersPromise.then((data) => {
      tickers = data;
    });

    function matches(query) {
      const q = query.trim().toLowerCase();
      if (!q) return tickers;
      return tickers.filter(
        (t) => t.ticker.toLowerCase().includes(q) || (t.company || "").toLowerCase().includes(q)
      );
    }

    function notAnalyzedYetHtml(query) {
      const safeQuery = (query || "").replace(/</g, "&lt;").trim();
      const askText = safeQuery ? `analyze ${safeQuery.toUpperCase()}` : "analyze TICKER";
      let html = '<div class="search-empty">';
      if (safeQuery) {
        html += `<strong>&ldquo;${safeQuery}&rdquo; hasn't been analyzed yet.</strong>`;
      } else {
        html += "<strong>No tickers analyzed yet.</strong>";
      }
      html += `<p>Ask Claude in your session: <code>${askText}</code></p>`;
      if (tickers.length > 0) {
        html +=
          "<p>Already analyzed:</p><ul class=\"search-fallback-list\">" +
          tickers
            .map((t) => `<li><a href="${baseHref}${t.report_path}">${t.ticker}</a>${t.company ? " — " + t.company : ""}</li>`)
            .join("") +
          "</ul>";
      }
      html += "</div>";
      return html;
    }

    function renderList(list, query) {
      activeIndex = -1;
      if (list.length === 0) {
        panel.innerHTML = notAnalyzedYetHtml(query);
        return;
      }
      panel.innerHTML = list
        .map(
          (t, i) =>
            `<a class="search-result" href="${baseHref}${t.report_path}" data-index="${i}">` +
            `<span class="sr-ticker">${t.ticker}</span>` +
            `<span class="sr-company">${t.company || ""}</span>` +
            `<span class="sr-sector">${t.quarter_label || ""}</span>` +
            `</a>`
        )
        .join("");
    }

    function open() {
      panel.hidden = false;
      input.setAttribute("aria-expanded", "true");
      renderList(matches(input.value), input.value);
    }

    function close() {
      panel.hidden = true;
      input.setAttribute("aria-expanded", "false");
      activeIndex = -1;
    }

    input.addEventListener("focus", open);
    input.addEventListener("input", open);

    input.addEventListener("keydown", (e) => {
      const results = panel.querySelectorAll(".search-result");
      if (e.key === "ArrowDown") {
        e.preventDefault();
        if (results.length === 0) return;
        activeIndex = (activeIndex + 1) % results.length;
        results.forEach((el, i) => el.classList.toggle("active", i === activeIndex));
        results[activeIndex].scrollIntoView({ block: "nearest" });
      } else if (e.key === "ArrowUp") {
        e.preventDefault();
        if (results.length === 0) return;
        activeIndex = (activeIndex - 1 + results.length) % results.length;
        results.forEach((el, i) => el.classList.toggle("active", i === activeIndex));
        results[activeIndex].scrollIntoView({ block: "nearest" });
      } else if (e.key === "Enter") {
        if (activeIndex >= 0 && results[activeIndex]) {
          window.location.href = results[activeIndex].getAttribute("href");
        } else if (results.length === 1) {
          window.location.href = results[0].getAttribute("href");
        }
      } else if (e.key === "Escape") {
        close();
        input.blur();
      }
    });

    document.addEventListener("click", (e) => {
      if (!container.contains(e.target)) close();
    });
  }

  document.querySelectorAll(".ticker-search").forEach(initInstance);
})();
