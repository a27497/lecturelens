package com.example.courselingo.media;

import java.nio.file.Path;
import java.time.Duration;
import java.util.List;

public interface AudioChunker {

    List<AudioChunk> split(Path audioFile, Path outputDirectory, Duration chunkDuration, int maxChunks);
}
