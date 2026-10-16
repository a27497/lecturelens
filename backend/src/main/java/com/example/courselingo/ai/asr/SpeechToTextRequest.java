package com.example.courselingo.ai.asr;

import java.nio.file.Path;
import java.time.Duration;

public record SpeechToTextRequest(
    Path audioFile,
    String language,
    String requestId,
    String taskId,
    Duration timeout,
    AudioInterval interval
) {
    public record AudioInterval(long startMillis,long endMillis,String source,String planHash) {
        public AudioInterval(long startMillis,long endMillis,String source){this(startMillis,endMillis,source,null);}
    }
    public SpeechToTextRequest(Path audioFile,String language,String requestId,String taskId,Duration timeout){this(audioFile,language,requestId,taskId,timeout,null);}
    public SpeechToTextRequest withInterval(AudioInterval value){return new SpeechToTextRequest(audioFile,language,requestId,taskId,timeout,value);}
}
