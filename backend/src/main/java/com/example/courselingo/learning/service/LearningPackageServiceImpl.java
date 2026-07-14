package com.example.courselingo.learning.service;

import com.example.courselingo.ai.llm.LlmProvider;
import com.example.courselingo.ai.llm.LlmProviderException;
import com.example.courselingo.ai.llm.LlmRequest;
import com.example.courselingo.ai.llm.LlmResult;
import com.example.courselingo.common.error.ErrorCode;
import com.example.courselingo.common.exception.BusinessException;
import com.example.courselingo.common.logging.SafeLogSanitizer;
import com.example.courselingo.learning.domain.LearningPackage;
import com.example.courselingo.learning.dto.KeyPointItem;
import com.example.courselingo.learning.mapper.LearningPackageMapper;
import com.example.courselingo.modelrouting.AiModelRoutedLlmRequestFactory;
import com.example.courselingo.modelrouting.AiModelStage;
import com.example.courselingo.subtitle.domain.SubtitleSegment;
import com.example.courselingo.subtitle.domain.TaskFullTextResult;
import com.example.courselingo.subtitle.domain.SubtitleTranslationSegment;
import com.example.courselingo.subtitle.mapper.SubtitleSegmentMapper;
import com.example.courselingo.subtitle.mapper.TaskFullTextResultMapper;
import com.example.courselingo.subtitle.mapper.SubtitleTranslationSegmentMapper;
import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.ObjectMapper;
import java.time.Clock;
import java.time.Duration;
import java.time.LocalDateTime;
import java.util.ArrayList;
import java.util.HashSet;
import java.util.List;
import java.util.Set;
import java.util.function.Supplier;
import java.util.stream.Collectors;
import org.springframework.beans.factory.ObjectProvider;
import org.springframework.beans.factory.annotation.Autowired;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class LearningPackageServiceImpl implements LearningPackageService {

    private static final Logger log = LoggerFactory.getLogger(LearningPackageServiceImpl.class);
    private static final ObjectMapper OBJECT_MAPPER = new ObjectMapper();
    private static final int RAW_CONTENT_PREVIEW_LIMIT = 1000;
    private static final int FALLBACK_SUMMARY_LIMIT = 240;
    private static final int FALLBACK_KEY_POINT_LIMIT = 120;
    private static final int MAX_SEGMENTS = 200;
    private static final int MAX_PROVIDER_LENGTH = 64;
    private static final String SCHEMA_VERSION = "learning-package.v1";

    private final SubtitleSegmentMapper sourceMapper;
    private final SubtitleTranslationSegmentMapper translationMapper;
    private final TaskFullTextResultMapper fullTextResultMapper;
    private final LearningPackageMapper learningPackageMapper;
    private final Supplier<LlmProvider> llmProviderSupplier;
    private final Clock clock;
    private final LearningPackageResponseParser parser;
    private final LearningPackageProperties properties;
    private final AiModelRoutedLlmRequestFactory routedRequestFactory;

    @Autowired
    public LearningPackageServiceImpl(
        SubtitleSegmentMapper sourceMapper,
        SubtitleTranslationSegmentMapper translationMapper,
        TaskFullTextResultMapper fullTextResultMapper,
        LearningPackageMapper learningPackageMapper,
        ObjectProvider<LlmProvider> llmProviderProvider,
        ObjectProvider<AiModelRoutedLlmRequestFactory> routedRequestFactoryProvider,
        LearningPackageResponseParser parser,
        LearningPackageProperties properties
    ) {
        this(
            sourceMapper,
            translationMapper,
            fullTextResultMapper,
            learningPackageMapper,
            llmProviderProvider::getIfAvailable,
            Clock.systemUTC(),
            parser,
            properties,
            routedRequestFactoryProvider.getIfAvailable()
        );
    }

    public LearningPackageServiceImpl(
        SubtitleSegmentMapper sourceMapper,
        SubtitleTranslationSegmentMapper translationMapper,
        LearningPackageMapper learningPackageMapper,
        LlmProvider llmProvider,
        Clock clock,
        LearningPackageResponseParser parser
    ) {
        this(
            sourceMapper,
            translationMapper,
            null,
            learningPackageMapper,
            () -> llmProvider,
            clock,
            parser,
            new LearningPackageProperties(),
            null
        );
    }

    public LearningPackageServiceImpl(
        SubtitleSegmentMapper sourceMapper,
        SubtitleTranslationSegmentMapper translationMapper,
        LearningPackageMapper learningPackageMapper,
        LlmProvider llmProvider,
        Clock clock,
        LearningPackageResponseParser parser,
        LearningPackageProperties properties
    ) {
        this(sourceMapper, translationMapper, null, learningPackageMapper, () -> llmProvider, clock, parser, properties, null);
    }

    public LearningPackageServiceImpl(
        SubtitleSegmentMapper sourceMapper,
        SubtitleTranslationSegmentMapper translationMapper,
        LearningPackageMapper learningPackageMapper,
        LlmProvider llmProvider,
        Clock clock,
        LearningPackageResponseParser parser,
        LearningPackageProperties properties,
        AiModelRoutedLlmRequestFactory routedRequestFactory
    ) {
        this(
            sourceMapper,
            translationMapper,
            null,
            learningPackageMapper,
            () -> llmProvider,
            clock,
            parser,
            properties,
            routedRequestFactory
        );
    }

    private LearningPackageServiceImpl(
        SubtitleSegmentMapper sourceMapper,
        SubtitleTranslationSegmentMapper translationMapper,
        TaskFullTextResultMapper fullTextResultMapper,
        LearningPackageMapper learningPackageMapper,
        Supplier<LlmProvider> llmProviderSupplier,
        Clock clock,
        LearningPackageResponseParser parser,
        LearningPackageProperties properties,
        AiModelRoutedLlmRequestFactory routedRequestFactory
    ) {
        this.sourceMapper = sourceMapper;
        this.translationMapper = translationMapper;
        this.fullTextResultMapper = fullTextResultMapper;
        this.learningPackageMapper = learningPackageMapper;
        this.llmProviderSupplier = llmProviderSupplier;
        this.clock = clock == null ? Clock.systemUTC() : clock;
        this.parser = parser == null ? new LearningPackageResponseParser() : parser;
        this.properties = properties == null ? new LearningPackageProperties() : properties;
        this.routedRequestFactory = routedRequestFactory;
    }

    @Override
    @Transactional
    public int generateLearningPackage(GenerateLearningPackageCommand command) {
        return generateLearningPackageWithAiCallRecord(command).savedCount();
    }

    @Override
    @Transactional
    public LearningPackageAiCallResult generateLearningPackageWithAiCallRecord(GenerateLearningPackageCommand command) {
        ValidatedLearningPackageCommand validated = LearningPackageValidators.validateCommand(command);
        List<SubtitleSegment> sourceSegments = loadAndValidateSourceSegments(validated);
        TaskFullTextResult fullTextResult = loadFullTextResult(validated);
        List<SubtitleTranslationSegment> translationSegments = fullTextResult == null
            ? loadAndValidateTranslationSegments(validated, sourceSegments)
            : List.of();
        LlmProvider llmProvider = resolveLlmProvider();
        LlmResult result = fullTextResult == null
            ? generateLearningPackage(llmProvider, validated, sourceSegments, translationSegments)
            : generateLearningPackageFromFullText(llmProvider, validated, fullTextResult);
        String provider = normalizeProvider(firstNonBlank(result.provider(), llmProvider.providerName()));
        LearningPackageResponseParser.ParsedLearningPackage parsed;
        try {
            parsed = parser.parse(result.content());
        } catch (RuntimeException ex) {
            if (!isRecoverableLearningPackageContentFailure(ex)) {
                throw ex;
            }
            logRecoverableContentFailure(validated, result, provider, ex, "start");
            LlmResult retryResult = fullTextResult == null
                ? generateLearningPackageRetry(llmProvider, validated, sourceSegments, translationSegments)
                : generateLearningPackageRetryFromFullText(llmProvider, validated, fullTextResult);
            String retryProvider = normalizeProvider(firstNonBlank(retryResult.provider(), provider));
            try {
                parsed = parser.parse(retryResult.content());
                result = retryResult;
                provider = retryProvider;
            } catch (RuntimeException retryException) {
                if (!isRecoverableLearningPackageContentFailure(retryException)) {
                    throw retryException;
                }
                logRecoverableContentFailure(validated, retryResult, retryProvider, retryException, "fallback");
                parsed = fullTextResult == null
                    ? buildFallbackPackage(sourceSegments, translationSegments)
                    : buildFallbackPackageFromFullText(fullTextResult);
                result = retryResult;
                provider = retryProvider;
                logFallbackUsed(validated, provider, result.model(), fallbackReason(retryException));
            }
        }

        learningPackageMapper.deleteByTaskIdUserIdAndTargetLanguage(
            validated.taskId(),
            validated.userId(),
            validated.targetLanguage()
        );
        int inserted = learningPackageMapper.insert(toEntity(validated, parsed, provider));
        if (inserted != 1) {
            throw new BusinessException(ErrorCode.COMMON_INTERNAL_ERROR, "Learning package persistence failed");
        }
        return new LearningPackageAiCallResult(
            inserted,
            provider,
            result.model(),
            result.duration(),
            result.usage().promptTokens(),
            result.usage().completionTokens(),
            result.usage().totalTokens(),
            fullTextResult == null ? sourceSegments.size() + translationSegments.size() : 1,
            inserted,
            null,
            null
        );
    }

    @Override
    public int deleteLearningPackage(String taskId, Long userId, String targetLanguage) {
        ValidatedLearningPackageScope scope = LearningPackageValidators.validateScope(taskId, userId, targetLanguage);
        return learningPackageMapper.deleteByTaskIdUserIdAndTargetLanguage(
            scope.taskId(),
            scope.userId(),
            scope.targetLanguage()
        );
    }

    private List<SubtitleSegment> loadAndValidateSourceSegments(ValidatedLearningPackageCommand command) {
        List<SubtitleSegment> sourceSegments = sourceMapper.selectByTaskIdAndUserId(command.taskId(), command.userId());
        if (sourceSegments == null || sourceSegments.isEmpty()) {
            throw validationFailure("Source subtitle segments are required");
        }
        if (fullTextResultMapper == null && sourceSegments.size() > MAX_SEGMENTS) {
            throw validationFailure("Source subtitle segment count is invalid");
        }
        Set<Integer> indexes = new HashSet<>();
        for (SubtitleSegment segment : sourceSegments) {
            validateSourceSegment(segment, command, indexes);
        }
        return sourceSegments;
    }

    private TaskFullTextResult loadFullTextResult(ValidatedLearningPackageCommand command) {
        if (fullTextResultMapper == null) {
            return null;
        }
        TaskFullTextResult result = fullTextResultMapper.selectByTaskIdUserIdAndTargetLanguage(
            command.taskId(),
            command.userId(),
            command.targetLanguage()
        );
        if (result == null || result.getTranslatedFullText() == null || result.getTranslatedFullText().isBlank()) {
            return null;
        }
        validateText(result.getSourceFullText(), "Full source text is invalid");
        validateText(result.getTranslatedFullText(), "Full translated text is invalid");
        return result;
    }

    private List<SubtitleTranslationSegment> loadAndValidateTranslationSegments(
        ValidatedLearningPackageCommand command,
        List<SubtitleSegment> sourceSegments
    ) {
        List<SubtitleTranslationSegment> translations = translationMapper.selectByTaskIdUserIdAndTargetLanguage(
            command.taskId(),
            command.userId(),
            command.targetLanguage()
        );
        if (translations == null || translations.isEmpty()) {
            throw validationFailure("Translated subtitle segments are required");
        }
        if (translations.size() != sourceSegments.size()) {
            throw validationFailure("Translated subtitle segments are invalid");
        }
        Set<Integer> sourceIndexes = new HashSet<>();
        for (SubtitleSegment source : sourceSegments) {
            sourceIndexes.add(source.getSegmentIndex());
        }
        Set<Integer> translationIndexes = new HashSet<>();
        for (SubtitleTranslationSegment translation : translations) {
            validateTranslationSegment(translation, command, sourceIndexes, translationIndexes);
        }
        return translations;
    }

    private static void validateSourceSegment(
        SubtitleSegment segment,
        ValidatedLearningPackageCommand command,
        Set<Integer> indexes
    ) {
        if (segment == null
            || segment.getSegmentIndex() == null
            || segment.getStartMillis() == null
            || segment.getEndMillis() == null) {
            throw validationFailure("Source subtitle segment is invalid");
        }
        if (!command.taskId().equals(segment.getTaskId()) || !command.userId().equals(segment.getUserId())) {
            throw validationFailure("Source subtitle segment is invalid");
        }
        if (!indexes.add(segment.getSegmentIndex()) || segment.getSegmentIndex() < 0) {
            throw validationFailure("Source subtitle segment index is invalid");
        }
        validateTimeRange(segment.getStartMillis(), segment.getEndMillis(), "Source subtitle segment time is invalid");
        validateText(segment.getText(), "Source subtitle segment text is invalid");
    }

    private static void validateTranslationSegment(
        SubtitleTranslationSegment segment,
        ValidatedLearningPackageCommand command,
        Set<Integer> sourceIndexes,
        Set<Integer> translationIndexes
    ) {
        if (segment == null
            || segment.getSegmentIndex() == null
            || segment.getStartMillis() == null
            || segment.getEndMillis() == null) {
            throw validationFailure("Translated subtitle segment is invalid");
        }
        if (!command.taskId().equals(segment.getTaskId())
            || !command.userId().equals(segment.getUserId())
            || !command.targetLanguage().equals(segment.getTargetLanguage())) {
            throw validationFailure("Translated subtitle segment is invalid");
        }
        if (!sourceIndexes.contains(segment.getSegmentIndex()) || !translationIndexes.add(segment.getSegmentIndex())) {
            throw validationFailure("Translated subtitle segment index is invalid");
        }
        validateTimeRange(segment.getStartMillis(), segment.getEndMillis(), "Translated subtitle segment time is invalid");
        validateText(segment.getTranslatedText(), "Translated subtitle segment text is invalid");
    }

    private LlmProvider resolveLlmProvider() {
        LlmProvider llmProvider = llmProviderSupplier == null ? null : llmProviderSupplier.get();
        if (llmProvider == null) {
            throw new BusinessException(ErrorCode.AI_PROVIDER_FAILED, "Learning package provider is not configured");
        }
        return llmProvider;
    }

    private LlmResult generateLearningPackage(
        LlmProvider llmProvider,
        ValidatedLearningPackageCommand command,
        List<SubtitleSegment> sourceSegments,
        List<SubtitleTranslationSegment> translationSegments
    ) {
        try {
            LlmRequest request = routeRequest(
                LearningPackagePromptFactory.build(
                    command,
                    sourceSegments,
                    translationSegments,
                    properties.llmTimeout()
                )
            );
            return generateWithDiagnostics(
                llmProvider,
                request,
                command,
                "translatedSubtitles",
                joinedLength(translationSegments.stream().map(SubtitleTranslationSegment::getTranslatedText).toList())
            );
        } catch (BusinessException ex) {
            throw ex;
        } catch (LlmProviderException ex) {
            throw new BusinessException(ErrorCode.AI_PROVIDER_FAILED, ex.getMessage(), ex);
        } catch (RuntimeException ex) {
            throw new BusinessException(ErrorCode.AI_PROVIDER_FAILED, "Learning package provider failed", ex);
        }
    }

    private LlmResult generateLearningPackageRetry(
        LlmProvider llmProvider,
        ValidatedLearningPackageCommand command,
        List<SubtitleSegment> sourceSegments,
        List<SubtitleTranslationSegment> translationSegments
    ) {
        try {
            LlmRequest request = routeRequest(
                LearningPackagePromptFactory.buildRetry(
                    command,
                    sourceSegments,
                    translationSegments,
                    properties.llmTimeout()
                )
            );
            return generateWithDiagnostics(
                llmProvider,
                request,
                command,
                "translatedSubtitles",
                joinedLength(translationSegments.stream().map(SubtitleTranslationSegment::getTranslatedText).toList())
            );
        } catch (BusinessException ex) {
            throw ex;
        } catch (LlmProviderException ex) {
            throw new BusinessException(ErrorCode.AI_PROVIDER_FAILED, ex.getMessage(), ex);
        } catch (RuntimeException ex) {
            throw new BusinessException(ErrorCode.AI_PROVIDER_FAILED, "Learning package provider failed", ex);
        }
    }

    private LlmResult generateLearningPackageFromFullText(
        LlmProvider llmProvider,
        ValidatedLearningPackageCommand command,
        TaskFullTextResult fullTextResult
    ) {
        try {
            LlmRequest request = routeRequest(
                LearningPackagePromptFactory.buildFromFullText(
                    command,
                    fullTextResult.getSourceFullText(),
                    fullTextResult.getTranslatedFullText(),
                    properties.llmTimeout()
                )
            );
            return generateWithDiagnostics(
                llmProvider,
                request,
                command,
                "translatedFullText",
                safeLength(fullTextResult.getTranslatedFullText())
            );
        } catch (BusinessException ex) {
            throw ex;
        } catch (LlmProviderException ex) {
            throw new BusinessException(ErrorCode.AI_PROVIDER_FAILED, ex.getMessage(), ex);
        } catch (RuntimeException ex) {
            throw new BusinessException(ErrorCode.AI_PROVIDER_FAILED, "Learning package provider failed", ex);
        }
    }

    private LlmResult generateLearningPackageRetryFromFullText(
        LlmProvider llmProvider,
        ValidatedLearningPackageCommand command,
        TaskFullTextResult fullTextResult
    ) {
        try {
            LlmRequest request = routeRequest(
                LearningPackagePromptFactory.buildRetryFromFullText(
                    command,
                    fullTextResult.getSourceFullText(),
                    fullTextResult.getTranslatedFullText(),
                    properties.llmTimeout()
                )
            );
            return generateWithDiagnostics(
                llmProvider,
                request,
                command,
                "translatedFullText",
                safeLength(fullTextResult.getTranslatedFullText())
            );
        } catch (BusinessException ex) {
            throw ex;
        } catch (LlmProviderException ex) {
            throw new BusinessException(ErrorCode.AI_PROVIDER_FAILED, ex.getMessage(), ex);
        } catch (RuntimeException ex) {
            throw new BusinessException(ErrorCode.AI_PROVIDER_FAILED, "Learning package provider failed", ex);
        }
    }

    private static LearningPackageResponseParser.ParsedLearningPackage buildFallbackPackageFromFullText(
        TaskFullTextResult fullTextResult
    ) {
        List<String> sentences = extractSentences(fullTextResult.getTranslatedFullText());
        String summary = sentences.stream().limit(2).collect(Collectors.joining(" ")).strip();
        if (summary.isBlank()) {
            summary = "Learning package generated from the uploaded course video.";
        }
        summary = limitText(summary, FALLBACK_SUMMARY_LIMIT);
        List<KeyPointItem> keyPoints = new ArrayList<>();
        int index = 1;
        for (String sentence : sentences) {
            String point = stripTerminalPunctuation(limitText(sentence, FALLBACK_KEY_POINT_LIMIT));
            if (!point.isBlank()) {
                keyPoints.add(new KeyPointItem(index++, point));
            }
            if (keyPoints.size() == 3) {
                break;
            }
        }
        return new LearningPackageResponseParser.ParsedLearningPackage(
            "Learning Package",
            summary,
            writeJson(keyPoints),
            "[]",
            "[]"
        );
    }

    private static LearningPackageResponseParser.ParsedLearningPackage buildFallbackPackage(
        List<SubtitleSegment> sourceSegments,
        List<SubtitleTranslationSegment> translationSegments
    ) {
        List<String> sentences = extractSentences(preferredFallbackText(sourceSegments, translationSegments));
        String summary = sentences.stream()
            .limit(2)
            .collect(Collectors.joining(" "))
            .strip();
        if (summary.isBlank()) {
            summary = "Learning package generated from the uploaded course video.";
        }
        summary = limitText(summary, FALLBACK_SUMMARY_LIMIT);
        List<KeyPointItem> keyPoints = new ArrayList<>();
        int index = 1;
        for (String sentence : sentences) {
            String point = stripTerminalPunctuation(limitText(sentence, FALLBACK_KEY_POINT_LIMIT));
            if (!point.isBlank()) {
                keyPoints.add(new KeyPointItem(index++, point));
            }
            if (keyPoints.size() == 3) {
                break;
            }
        }
        return new LearningPackageResponseParser.ParsedLearningPackage(
            "Learning Package",
            summary,
            writeJson(keyPoints),
            "[]",
            "[]"
        );
    }

    private static String preferredFallbackText(
        List<SubtitleSegment> sourceSegments,
        List<SubtitleTranslationSegment> translationSegments
    ) {
        String translatedText = translationSegments.stream()
            .map(SubtitleTranslationSegment::getTranslatedText)
            .filter(text -> text != null && !text.isBlank())
            .collect(Collectors.joining(" "))
            .strip();
        if (!translatedText.isBlank()) {
            return translatedText;
        }
        return sourceSegments.stream()
            .map(SubtitleSegment::getText)
            .filter(text -> text != null && !text.isBlank())
            .collect(Collectors.joining(" "))
            .strip();
    }

    private static List<String> extractSentences(String text) {
        if (text == null || text.isBlank()) {
            return List.of();
        }
        List<String> sentences = new ArrayList<>();
        for (String sentence : text.strip().split("(?<=[.!?])\\s+|(?<=[。！？])\\s*")) {
            String normalized = sentence.strip();
            if (!normalized.isBlank()) {
                sentences.add(normalized);
            }
        }
        if (sentences.isEmpty()) {
            sentences.add(text.strip());
        }
        return sentences;
    }

    private static String limitText(String text, int limit) {
        if (text == null) {
            return "";
        }
        String normalized = text.replaceAll("\\s+", " ").strip();
        if (normalized.length() <= limit) {
            return normalized;
        }
        return normalized.substring(0, limit).strip();
    }

    private static String stripTerminalPunctuation(String text) {
        return text == null ? "" : text.replaceAll("[.!?。！？]+$", "").strip();
    }

    private static String writeJson(Object value) {
        try {
            return OBJECT_MAPPER.writeValueAsString(value);
        } catch (JsonProcessingException ex) {
            throw new BusinessException(ErrorCode.COMMON_INTERNAL_ERROR, "Learning package JSON serialization failed");
        }
    }

    private static LlmResult generateWithDiagnostics(
        LlmProvider llmProvider,
        LlmRequest request,
        ValidatedLearningPackageCommand command,
        String inputSource,
        int inputLength
    ) {
        log.info(
            "event=learning_package_llm_started taskId={} inputSource={} inputLength={}",
            SafeLogSanitizer.sanitize(command.taskId()),
            SafeLogSanitizer.sanitize(inputSource),
            inputLength
        );
        long startedNanos = System.nanoTime();
        LlmResult result = llmProvider.generate(request);
        log.info(
            "event=learning_package_llm_completed taskId={} inputSource={} inputLength={} durationMillis={} totalTokens={} outputLength={}",
            SafeLogSanitizer.sanitize(command.taskId()),
            SafeLogSanitizer.sanitize(inputSource),
            inputLength,
            elapsedMillis(startedNanos, result.duration()),
            result.usage().totalTokens(),
            result.content().length()
        );
        return result;
    }

    private static int joinedLength(List<String> values) {
        if (values == null || values.isEmpty()) {
            return 0;
        }
        return values.stream()
            .filter(value -> value != null && !value.isBlank())
            .mapToInt(String::length)
            .sum();
    }

    private static int safeLength(String value) {
        return value == null ? 0 : value.length();
    }

    private static long elapsedMillis(long startedNanos, Duration providerDuration) {
        if (providerDuration != null && !providerDuration.isNegative()) {
            return providerDuration.toMillis();
        }
        return Duration.ofNanos(System.nanoTime() - startedNanos).toMillis();
    }

    private LlmRequest routeRequest(LlmRequest request) {
        return routedRequestFactory == null
            ? request
            : routedRequestFactory.apply(AiModelStage.LEARNING_PACKAGE, request);
    }

    private LearningPackage toEntity(
        ValidatedLearningPackageCommand command,
        LearningPackageResponseParser.ParsedLearningPackage parsed,
        String provider
    ) {
        LocalDateTime now = LocalDateTime.ofInstant(clock.instant(), clock.getZone());
        LearningPackage entity = new LearningPackage();
        entity.setTaskId(command.taskId());
        entity.setUserId(command.userId());
        entity.setSourceLanguage(command.sourceLanguage());
        entity.setTargetLanguage(command.targetLanguage());
        entity.setTitle(parsed.title());
        entity.setSummary(parsed.summary());
        entity.setKeyPointsJson(parsed.keyPointsJson());
        entity.setGlossaryJson(parsed.glossaryJson());
        entity.setQaJson(parsed.qaJson());
        entity.setProvider(provider);
        entity.setSchemaVersion(SCHEMA_VERSION);
        entity.setCreatedAt(now);
        entity.setUpdatedAt(now);
        return entity;
    }

    private static void validateTimeRange(Long startMillis, Long endMillis, String message) {
        if (startMillis < 0 || endMillis < startMillis) {
            throw validationFailure(message);
        }
    }

    private static void validateText(String text, String message) {
        if (text == null || text.isBlank() || LearningPackageSensitiveDataValidator.containsSensitiveData(text)) {
            throw validationFailure(message);
        }
    }

    private static String normalizeProvider(String provider) {
        if (provider == null || provider.isBlank()) {
            return null;
        }
        String normalized = provider.strip();
        if (normalized.length() > MAX_PROVIDER_LENGTH
            || LearningPackageSensitiveDataValidator.containsSensitiveData(normalized)) {
            throw validationFailure("Learning package provider is invalid");
        }
        return normalized;
    }

    private static String firstNonBlank(String first, String fallback) {
        return first == null || first.isBlank() ? fallback : first;
    }

    private static void logRecoverableContentFailure(
        ValidatedLearningPackageCommand command,
        LlmResult result,
        String provider,
        RuntimeException exception,
        String retry
    ) {
        if (exception == null || exception.getMessage() == null) {
            return;
        }
        String errorCode = isJsonParseError(exception) ? "JSON_PARSE_ERROR" : "VALIDATION_FAILED";
        log.warn(
            "event=learning_package_parse_failed taskId={} provider={} model={} errorCode={} retry={} rawContentPreview={}",
            SafeLogSanitizer.sanitize(command.taskId()),
            SafeLogSanitizer.sanitize(provider),
            SafeLogSanitizer.sanitize(result.model()),
            errorCode,
            SafeLogSanitizer.sanitize(retry),
            SafeLogSanitizer.sanitizeAndLimit(result.content(), RAW_CONTENT_PREVIEW_LIMIT)
        );
    }

    private static void logFallbackUsed(
        ValidatedLearningPackageCommand command,
        String provider,
        String model,
        String reason
    ) {
        log.warn(
            "event=learning_package_fallback_used taskId={} provider={} model={} reason={}",
            SafeLogSanitizer.sanitize(command.taskId()),
            SafeLogSanitizer.sanitize(provider),
            SafeLogSanitizer.sanitize(model),
            SafeLogSanitizer.sanitize(reason)
        );
    }

    private static boolean isJsonParseError(RuntimeException exception) {
        return exception != null && exception.getMessage() != null && exception.getMessage().contains("JSON_PARSE_ERROR");
    }

    private static boolean isRecoverableLearningPackageContentFailure(RuntimeException exception) {
        if (exception == null) {
            return false;
        }
        String message = exception.getMessage();
        if (message == null) {
            return false;
        }
        return message.contains("JSON_PARSE_ERROR")
            || message.contains("Learning package glossary item is invalid")
            || message.contains("Learning package qa item is invalid")
            || message.contains("Learning package key point is invalid")
            || message.contains("Learning package validation failed");
    }

    private static String fallbackReason(RuntimeException exception) {
        return isJsonParseError(exception) ? "json_parse_failed" : "validation_failed";
    }

    private static BusinessException validationFailure(String message) {
        return LearningPackageValidators.validationFailure(message);
    }
}
