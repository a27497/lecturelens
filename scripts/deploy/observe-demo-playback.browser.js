// Read only browser timing/status metadata after manually playing and seeking.
// No requests are sent and no media URL, credential, subtitle or response body
// is read. Native video requests must have finished to appear in this snapshot.
(() => {
  const video = document.querySelector("video.course-video-player");
  const path = "/api/media/uploads/up_d69077ad31e2414384b9dc3e2c7d6701/stream";
  if (!video) {
    console.table([{ path, http_status: "NOT_OBSERVED", error_code: "PLAYER_NOT_PRESENT" }]);
    return;
  }
  const resources = performance.getEntriesByType("resource").filter(entry => entry.initiatorType === "video");
  console.table(resources.map(entry => ({
    path,
    http_status: Number.isInteger(entry.responseStatus) ? entry.responseStatus : "NOT_EXPOSED",
    encoded_bytes: entry.encodedBodySize,
    duration_ms: Math.round(entry.duration),
  })));
  console.table([{
    duration_seconds: video.duration,
    current_seconds: video.currentTime,
    ready_state: video.readyState,
    media_error_code: video.error?.code ?? 0,
    seekable_ranges: Array.from({ length: video.seekable.length }, (_, i) => [video.seekable.start(i), video.seekable.end(i)]),
  }]);
})();
