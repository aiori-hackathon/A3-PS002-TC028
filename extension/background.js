chrome.runtime.onInstalled.addListener(() => {
  chrome.storage.local.set({ detectedNotice: null });
});
