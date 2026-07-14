// Runs in the page when the popup asks for content. Readability.js is
// injected just before this file. Works on the RENDERED DOM, so SPA/JS-heavy
// pages extract fine. Returns its result as the script's completion value.
(() => {
  try {
    const clone = document.cloneNode(true);
    const article = new Readability(clone, { charThreshold: 200 }).parse();

    // Fallback for pages Readability rejects (dashboards, docs indexes…):
    // take visible body text, crudely de-chromed.
    let text = article && article.textContent ? article.textContent : "";
    let usedFallback = false;
    if (!text || text.trim().length < 200) {
      usedFallback = true;
      const junk = document.querySelectorAll("nav, header, footer, script, style, noscript, aside");
      const clone2 = document.body.cloneNode(true);
      clone2.querySelectorAll("nav, header, footer, script, style, noscript, aside")
        .forEach((n) => n.remove());
      void junk; // (original DOM untouched)
      text = clone2.innerText || "";
    }
    text = text.replace(/\u00a0/g, " ").trim();

    return {
      ok: text.length > 0,
      url: location.href,
      title: (article && article.title) || document.title || location.href,
      siteName: (article && article.siteName) || location.hostname,
      byline: (article && article.byline) || "",
      text,
      words: text ? text.split(/\s+/).length : 0,
      usedFallback,
    };
  } catch (e) {
    return { ok: false, error: String(e), url: location.href, title: document.title };
  }
})();
