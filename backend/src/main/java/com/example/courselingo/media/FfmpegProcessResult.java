package com.example.courselingo.media;

record FfmpegProcessResult(
    int exitCode,
    String stdout,
    String stderr,
    boolean timedOut
) {

    static FfmpegProcessResult success(String stdout, String stderr) {
        return new FfmpegProcessResult(0, stdout, stderr, false);
    }
}
