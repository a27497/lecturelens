package com.example.courselingo.media;

import java.nio.file.Path;
import java.time.Duration;

public interface VideoMetadataProbe {

    VideoMetadata probe(Path sourceVideo, Duration timeout);
}
