package com.example.courselingo.task.runner;

import com.example.courselingo.media.AudioExtractionResult;
import com.example.courselingo.ai.asr.SpeechToTextResult;
import java.util.ArrayList;
import java.nio.file.Path;
import java.util.List;
import java.util.Optional;

public final class PipelineAnalysisTaskStepContext {

    private final AnalysisTaskExecutionContext taskContext;
    private final List<PipelineAnalysisTaskStepName> completedSteps;
    private Path uploadedSourcePath;
    private AudioExtractionResult audioExtractionResult;
    private SpeechToTextResult speechToTextResult;
    private final List<PipelineAiCallRecord> aiCallRecords = new ArrayList<>();

    PipelineAnalysisTaskStepContext(
        AnalysisTaskExecutionContext taskContext,
        List<PipelineAnalysisTaskStepName> completedSteps
    ) {
        this.taskContext = taskContext;
        this.completedSteps = completedSteps;
    }

    public PipelineAnalysisTaskStepContext(AnalysisTaskExecutionContext taskContext) {
        this(taskContext, new java.util.ArrayList<>());
    }

    public AnalysisTaskExecutionContext taskContext() {
        return taskContext;
    }

    public List<PipelineAnalysisTaskStepName> completedSteps() {
        return List.copyOf(completedSteps);
    }

    public String taskId() {
        return taskContext.taskId();
    }

    public String uploadId() {
        return taskContext.uploadId();
    }

    public Long userId() {
        return taskContext.userId();
    }

    public String targetLanguage() {
        return taskContext.targetLanguage();
    }

    public String requestId() {
        return taskContext.requestId();
    }

    public Optional<Path> uploadedSourcePath() {
        return Optional.ofNullable(uploadedSourcePath);
    }

    void setUploadedSourcePath(Path uploadedSourcePath) {
        this.uploadedSourcePath = uploadedSourcePath;
    }

    Path requireUploadedSourcePath() {
        return uploadedSourcePath().orElseThrow(() ->
            new IllegalStateException("uploaded source path is required before audio extraction")
        );
    }

    public Optional<AudioExtractionResult> audioExtractionResult() {
        return Optional.ofNullable(audioExtractionResult);
    }

    void setAudioExtractionResult(AudioExtractionResult audioExtractionResult) {
        this.audioExtractionResult = audioExtractionResult;
    }

    AudioExtractionResult requireAudioExtractionResult() {
        return audioExtractionResult().orElseThrow(() ->
            new IllegalStateException("audio extraction result is required before transcription")
        );
    }

    public Optional<Path> extractedAudioPath() {
        return audioExtractionResult().map(AudioExtractionResult::audioFile);
    }

    public Optional<SpeechToTextResult> speechToTextResult() {
        return Optional.ofNullable(speechToTextResult);
    }

    void setSpeechToTextResult(SpeechToTextResult speechToTextResult) {
        this.speechToTextResult = speechToTextResult;
    }

    SpeechToTextResult requireSpeechToTextResult() {
        return speechToTextResult().orElseThrow(() ->
            new IllegalStateException("ASR result is required before subtitle persistence")
        );
    }

    void addAiCallRecord(PipelineAiCallRecord record) {
        if (record != null) {
            aiCallRecords.add(record);
        }
    }

    public List<PipelineAiCallRecord> pendingAiCallRecords() {
        return List.copyOf(aiCallRecords);
    }

    List<PipelineAiCallRecord> drainAiCallRecords() {
        List<PipelineAiCallRecord> records = List.copyOf(aiCallRecords);
        aiCallRecords.clear();
        return records;
    }

    void restoreAiCallRecords(List<PipelineAiCallRecord> records) {
        if (records != null && !records.isEmpty()) {
            aiCallRecords.addAll(0, records);
        }
    }

    @Override
    public String toString() {
        return "PipelineAnalysisTaskStepContext{"
            + "taskContextPresent=" + (taskContext != null)
            + ", completedSteps=" + completedSteps
            + ", uploadedSourcePath=[redacted]"
            + ", extractedAudioPath=[redacted]"
            + ", asrResultPresent=" + (speechToTextResult != null)
            + ", asrSegmentCount=" + asrSegmentCount()
            + ", pendingAiCallRecordCount=" + aiCallRecords.size()
            + '}';
    }

    private int asrSegmentCount() {
        if (speechToTextResult == null || speechToTextResult.segments() == null) {
            return 0;
        }
        return speechToTextResult.segments().size();
    }
}
