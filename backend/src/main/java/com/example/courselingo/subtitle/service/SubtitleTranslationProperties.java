package com.example.courselingo.subtitle.service;

import com.example.courselingo.ai.llm.LlmRequestValidator;
import java.time.Duration;
import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "courselingo.subtitle.translation")
public class SubtitleTranslationProperties {

    private FullText fullText = new FullText();

    public FullText getFullText() {
        return fullText;
    }

    public void setFullText(FullText fullText) {
        this.fullText = fullText == null ? new FullText() : fullText;
    }

    public static class FullText {
        private static final Duration DEFAULT_REQUEST_TIMEOUT = Duration.ofSeconds(900);
        private static final int DEFAULT_MAX_TOKENS = LlmRequestValidator.MAX_TOKENS;
        private static final int DEFAULT_MAX_ATTEMPTS = 1;
        private static final int DEFAULT_SEMANTIC_MAX_ATTEMPTS = 2;
        private static final int DEFAULT_MAX_SOURCE_SEGMENTS = 1000;
        private static final int DEFAULT_BATCH_MAX_SEGMENTS = 8;
        private static final int DEFAULT_BATCH_MAX_INPUT_CHARS = 2500;
        private static final int DEFAULT_SINGLE_SEGMENT_MAX_PIECE_CHARS = 600;
        private static final int DEFAULT_SINGLE_SEGMENT_MIN_PIECE_CHARS = 80;
        private static final int DEFAULT_SINGLE_SEGMENT_MAX_DEPTH = 6;

        private boolean enabled = true;
        private Duration requestTimeout = DEFAULT_REQUEST_TIMEOUT;
        private int maxTokens = DEFAULT_MAX_TOKENS;
        private int maxAttempts = DEFAULT_MAX_ATTEMPTS;
        private int semanticMaxAttempts = DEFAULT_SEMANTIC_MAX_ATTEMPTS;
        private int maxSourceSegments = DEFAULT_MAX_SOURCE_SEGMENTS;
        private int batchMaxSegments = DEFAULT_BATCH_MAX_SEGMENTS;
        private int batchMaxInputChars = DEFAULT_BATCH_MAX_INPUT_CHARS;
        private boolean singleSegmentSplitEnabled = true;
        private int singleSegmentMaxPieceChars = DEFAULT_SINGLE_SEGMENT_MAX_PIECE_CHARS;
        private int singleSegmentMinPieceChars = DEFAULT_SINGLE_SEGMENT_MIN_PIECE_CHARS;
        private int singleSegmentMaxDepth = DEFAULT_SINGLE_SEGMENT_MAX_DEPTH;

        public boolean isEnabled() {
            return enabled;
        }

        public void setEnabled(boolean enabled) {
            this.enabled = enabled;
        }

        public Duration getRequestTimeout() {
            return requestTimeout;
        }

        public void setRequestTimeout(Duration requestTimeout) {
            this.requestTimeout = isPositive(requestTimeout) ? requestTimeout : DEFAULT_REQUEST_TIMEOUT;
        }

        public int getMaxTokens() {
            return maxTokens;
        }

        public void setMaxTokens(int maxTokens) {
            this.maxTokens = maxTokens > 0 ? Math.min(maxTokens, LlmRequestValidator.MAX_TOKENS) : DEFAULT_MAX_TOKENS;
        }

        public int getMaxAttempts() {
            return maxAttempts;
        }

        public void setMaxAttempts(int maxAttempts) {
            this.maxAttempts = maxAttempts > 0 ? maxAttempts : DEFAULT_MAX_ATTEMPTS;
        }

        public int getSemanticMaxAttempts() {
            return semanticMaxAttempts;
        }

        public void setSemanticMaxAttempts(int semanticMaxAttempts) {
            this.semanticMaxAttempts = semanticMaxAttempts >= 1 && semanticMaxAttempts <= 2
                ? semanticMaxAttempts
                : DEFAULT_SEMANTIC_MAX_ATTEMPTS;
        }

        public int getMaxSourceSegments() {
            return maxSourceSegments;
        }

        public void setMaxSourceSegments(int maxSourceSegments) {
            this.maxSourceSegments = maxSourceSegments > 0 ? maxSourceSegments : DEFAULT_MAX_SOURCE_SEGMENTS;
        }

        public int getBatchMaxSegments() {
            return batchMaxSegments;
        }

        public void setBatchMaxSegments(int batchMaxSegments) {
            this.batchMaxSegments = batchMaxSegments > 0 ? batchMaxSegments : DEFAULT_BATCH_MAX_SEGMENTS;
        }

        public int getBatchMaxInputChars() {
            return batchMaxInputChars;
        }

        public void setBatchMaxInputChars(int batchMaxInputChars) {
            this.batchMaxInputChars = batchMaxInputChars > 0 ? batchMaxInputChars : DEFAULT_BATCH_MAX_INPUT_CHARS;
        }

        public boolean isSingleSegmentSplitEnabled() {
            return singleSegmentSplitEnabled;
        }

        public void setSingleSegmentSplitEnabled(boolean singleSegmentSplitEnabled) {
            this.singleSegmentSplitEnabled = singleSegmentSplitEnabled;
        }

        public int getSingleSegmentMaxPieceChars() {
            return singleSegmentMaxPieceChars;
        }

        public void setSingleSegmentMaxPieceChars(int singleSegmentMaxPieceChars) {
            this.singleSegmentMaxPieceChars = singleSegmentMaxPieceChars > 0
                ? singleSegmentMaxPieceChars
                : DEFAULT_SINGLE_SEGMENT_MAX_PIECE_CHARS;
        }

        public int getSingleSegmentMinPieceChars() {
            return singleSegmentMinPieceChars;
        }

        public void setSingleSegmentMinPieceChars(int singleSegmentMinPieceChars) {
            this.singleSegmentMinPieceChars = singleSegmentMinPieceChars > 0
                ? singleSegmentMinPieceChars
                : DEFAULT_SINGLE_SEGMENT_MIN_PIECE_CHARS;
        }

        public int getSingleSegmentMaxDepth() {
            return singleSegmentMaxDepth;
        }

        public void setSingleSegmentMaxDepth(int singleSegmentMaxDepth) {
            this.singleSegmentMaxDepth = singleSegmentMaxDepth > 0
                ? singleSegmentMaxDepth
                : DEFAULT_SINGLE_SEGMENT_MAX_DEPTH;
        }

        private static boolean isPositive(Duration duration) {
            return duration != null && !duration.isZero() && !duration.isNegative();
        }
    }
}
