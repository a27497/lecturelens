package com.example.courselingo.vision.ocr;

import java.io.IOException;
import java.time.Duration;
import java.util.List;

interface OcrProcessExecutor {

    OcrProcessResult execute(List<String> command, Duration timeout) throws IOException, InterruptedException;
}
