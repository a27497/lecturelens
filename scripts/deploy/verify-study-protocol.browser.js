// Run on the already authenticated 10-16 production page. The existing app
// supplies authentication; this script never accesses credential storage or
// inspects authentication headers. No operation creates a Run or starts a model.
(async () => {
  const task = "task_38372ad3617f4a91b6c1f864429b5966";
  const session = "4b7782ab-b66b-5787-a990-1a09760357c3";
  const path = `/api/tasks/${task}/study/command`;
  const statusPath = `/api/tasks/${task}/study/status`;
  const absent = "audit-nonexistent-6d2016ad-2b20-4eb4-a8cb-9c5fba791904";
  const rows = [];
  const emit = (path, http_status, error_code) => rows.push({ path, http_status, error_code });
  try {
    const entry = document.querySelector('script[type="module"][src*="/assets/index-"]');
    const url = new URL(entry?.src || "", location.href);
    if (location.origin !== "https://34.81.153.182" || url.pathname !== "/assets/index-7QXHsJzU.js") {
      emit(statusPath, 0, "UNEXPECTED_ORIGIN_OR_BUILD");
      console.table(rows);
      return;
    }
    const app = await import(url.href);
    // These exports were verified against the served 10-16 bundle. Delegate
    // authentication directly to its existing helper without retaining headers.
    if (typeof app.c !== "function" || typeof app.s?.request !== "function") {
      emit(statusPath, 0, "APP_REQUEST_HELPER_UNAVAILABLE");
      console.table(rows);
      return;
    }
    const requests = [
      { method: "GET", url: statusPath },
      { method: "POST", url: path, data: { operation: "RUNS", session_id: session } },
      { method: "POST", url: path, data: { operation: "DECIDE_APPROVAL", session_id: session, run_id: absent, request_key: absent, approval_decision: "reject" } },
      { method: "POST", url: path, data: { operation: "ATTEMPT_HISTORY", session_id: session, run_id: absent, artifact_id: absent, question_index: 0 } },
      { method: "POST", url: path, data: { operation: "FEEDBACK_NOTES", session_id: session, run_id: absent, feedback_id: absent } },
    ];
    for (const request of requests) {
      try {
        const response = await app.s.request({
          ...request,
          headers: app.c(),
          validateStatus: () => true,
          // ApiResponse begins with code. Read only this bounded field; never
          // decode data, messages, course text, answers or other response fields.
          transformResponse: [(raw) => {
            const match = typeof raw === "string" && raw.slice(0, 128).match(/^\s*\{\s*"code"\s*:\s*"([A-Z0-9_]{1,80})"/);
            return match ? match[1] : "CODE_UNAVAILABLE";
          }],
        });
        emit(request.url, response.status, response.data);
        if ([401, 403, 422, 503].includes(response.status)) break;
      } catch {
        emit(request.url, 0, "REQUEST_FAILED");
        break;
      }
    }
  } catch {
    emit(statusPath, 0, "CHECK_SETUP_FAILED");
  }
  console.table(rows);
})();
