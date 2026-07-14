package com.example.courselingo.media;

import java.util.List;

public interface VideoFrameExtractor {

    List<ExtractedVideoFrame> extract(VideoFrameExtractionRequest request);
}
