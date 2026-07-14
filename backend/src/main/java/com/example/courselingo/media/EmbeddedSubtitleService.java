package com.example.courselingo.media;

public interface EmbeddedSubtitleService {

    EmbeddedSubtitleProbeResponse probeUpload(String authorizationHeader, String uploadId);

    EmbeddedSubtitleProbeResponse probeTask(String authorizationHeader, String taskId);

    EmbeddedSubtitleFileResponse downloadUpload(String authorizationHeader, String uploadId, int streamIndex);

    EmbeddedSubtitleFileResponse downloadTask(String authorizationHeader, String taskId, int streamIndex);
}
