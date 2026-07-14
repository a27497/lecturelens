package com.example.courselingo.media;

public interface MediaPlaybackService {

    PlaybackTokenResponse requestUploadPlaybackToken(String authorizationHeader, String uploadId);

    PlaybackTokenResponse requestTaskPlaybackToken(String authorizationHeader, String taskId);

    MediaStreamResponse stream(String uploadId, String token, String rangeHeader);
}
