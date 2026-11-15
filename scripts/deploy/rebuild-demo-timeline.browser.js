// The course owner runs this once on the already authenticated course page,
// after the operator confirms no active Study Run. This posts only one endpoint.
(async () => {
  const path = "/api/tasks/task_38372ad3617f4a91b6c1f864429b5966/video-segments/rebuild";
  const emit = (http_status, error_code) => console.table([{ path, http_status, error_code }]);
  if (location.origin !== "https://34.81.153.182" || window.__lectureLensTimelineRebuildSent) {
    emit(0, "WRONG_ORIGIN_OR_ALREADY_SENT");
    return;
  }
  try {
    const app = await import("/assets/index-7QXHsJzU.js");
    if (typeof app.s?.post !== "function" || typeof app.c !== "function") {
      emit(0, "APP_HELPER_UNAVAILABLE");
      return;
    }
    window.__lectureLensTimelineRebuildSent = true;
    const response = await app.s.post(path, undefined, {
      headers: app.c(),
      timeout: 30000,
      validateStatus: () => true,
      transformResponse: [(raw) => {
        const match = typeof raw === "string" && raw.slice(0, 128).match(/^\s*\{\s*"code"\s*:\s*"([A-Z0-9_]{1,80})"/);
        return match ? match[1] : "CODE_UNAVAILABLE";
      }],
    });
    emit(response.status, response.data);
  } catch {
    emit(0, "REQUEST_NOT_CONFIRMED_DO_NOT_RETRY");
  }
})();
