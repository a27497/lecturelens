package com.example.courselingo.media;

import java.io.IOException;
import java.time.Duration;
import java.util.List;

interface FfmpegProcessExecutor {

    FfmpegProcessResult execute(List<String> command, Duration timeout) throws IOException, InterruptedException;
}
