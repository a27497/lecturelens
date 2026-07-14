package com.example.courselingo.media;

import java.nio.file.Path;

@FunctionalInterface
public interface AudioDurationProbe {

    long probeDurationMillis(Path audioFile);
}
