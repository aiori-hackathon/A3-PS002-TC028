(() => {
  const text = document.body?.innerText || "";
  const signals = [/cookie/i, /privacy notice/i, /personal data/i, /analytics/i, /advertising/i];
  const matched = signals.filter(r => r.test(text)).length;
  const explicit = document.querySelector('[data-consentguard="notice"]');
  if (explicit || matched >= 3) {
    const noticeText = explicit ? explicit.innerText : text.slice(0, 5000);
    const payload = {
      site: location.hostname === "localhost" ? "demo.local" : location.hostname,
      url: location.href,
      title: document.title,
      noticeText,
      summary: [
        "What data: the notice may describe device, usage, preference or account data.",
        "Why collected: identify the stated service, analytics, personalisation or advertising purposes.",
        "How used: review the notice wording before granting any optional purpose."
      ],
      detectedAt: new Date().toISOString()
    };
    chrome.storage.local.set({ detectedNotice: payload });
    chrome.runtime.sendMessage({ type: "NOTICE_DETECTED", payload }).catch(()=>{});
  }
})();
