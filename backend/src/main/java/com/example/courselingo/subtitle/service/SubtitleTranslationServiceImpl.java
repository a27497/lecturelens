package com.example.courselingo.subtitle.service;

import com.example.courselingo.ai.llm.LlmProvider;
import com.example.courselingo.ai.llm.LlmProviderException;
import com.example.courselingo.ai.llm.LlmRequest;
import com.example.courselingo.ai.llm.LlmResult;
import com.example.courselingo.common.error.ErrorCode;
import com.example.courselingo.common.exception.BusinessException;
import com.example.courselingo.common.logging.SafeLogSanitizer;
import com.example.courselingo.modelrouting.AiModelRoutedLlmRequestFactory;
import com.example.courselingo.modelrouting.AiModelStage;
import com.example.courselingo.subtitle.domain.SubtitleSegment;
import com.example.courselingo.subtitle.domain.TaskFullTextResult;
import com.example.courselingo.subtitle.domain.SubtitleTranslationSegment;
import com.example.courselingo.subtitle.mapper.SubtitleSegmentMapper;
import com.example.courselingo.subtitle.mapper.TaskFullTextResultMapper;
import com.example.courselingo.subtitle.mapper.SubtitleTranslationSegmentMapper;
import java.time.Clock;
import java.time.Duration;
import java.time.LocalDateTime;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.HashSet;
import java.util.List;
import java.util.Locale;
import java.util.Set;
import java.util.function.Supplier;
import org.springframework.beans.factory.ObjectProvider;
import org.springframework.beans.factory.annotation.Autowired;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Service;

@Service
public class SubtitleTranslationServiceImpl implements SubtitleTranslationService {

    private static final Logger log = LoggerFactory.getLogger(SubtitleTranslationServiceImpl.class);
    private static final int MAX_SOURCE_SEGMENTS = 200;
    private static final int MAX_PROVIDER_LENGTH = 64;
    private static final int CHINESE_SOURCE_SKIP_MIN_CHARS = 50;
    private static final double CHINESE_SOURCE_SKIP_MIN_RATIO = 0.2d;
    private static final String SOURCE_ALREADY_TARGET_PROVIDER = "source";
    private static final String TARGET_LANGUAGE_MISMATCH = "TARGET_LANGUAGE_MISMATCH";
    private static final String UNTRANSLATED_TEXT = "UNTRANSLATED_TEXT";
    private static final Set<String> ESTABLISHED_TECHNICAL_TERMS = Set.of(
        "api", "boot", "docker", "gateway", "git", "gradle", "http", "https", "java", "junit",
        "kafka", "kotlin", "kubernetes", "linux", "maven", "minio", "mockito", "mysql", "node.js",
        "redis", "rocketmq", "spring", "typescript", "vite", "vue"
    );
    private static final List<String> ESTABLISHED_MULTI_WORD_TECHNICAL_PHRASES = List.of(
        "openai chat completions api",
        "spring cloud netflix eureka",
        "spring cloud config server",
        "spring boot admin server",
        "visual studio code",
        "intellij idea",
        "docker compose",
        "config server",
        "api gateway",
        "openai api",
        "spring cloud"
    );
    private static final Set<String> ENGLISH_PROSE_MARKERS = Set.of(
        "a", "an", "and", "are", "as", "at", "be", "by", "deploys", "explains", "for", "from",
        "has", "have", "in", "is", "it", "manages", "of", "on", "or", "provides", "that", "the",
        "this", "to", "used", "uses", "using", "with"
    );

    private final SubtitleSegmentMapper sourceMapper;
    private final Supplier<LlmProvider> llmProviderSupplier;
    private final Clock clock;
    private final SubtitleTranslationResponseParser parser;
    private final TaskFullTextResultMapper fullTextResultMapper;
    private final SubtitleTranslationProperties properties;
    private final AiModelRoutedLlmRequestFactory routedRequestFactory;
    private final SubtitleTranslationPersistenceService persistenceService;

    @Autowired
    public SubtitleTranslationServiceImpl(
        SubtitleSegmentMapper sourceMapper,
        SubtitleTranslationSegmentMapper translationMapper,
        TaskFullTextResultMapper fullTextResultMapper,
        ObjectProvider<LlmProvider> llmProviderProvider,
        ObjectProvider<AiModelRoutedLlmRequestFactory> routedRequestFactoryProvider,
        SubtitleTranslationResponseParser parser,
        SubtitleTranslationProperties properties,
        SubtitleTranslationPersistenceService persistenceService
    ) {
        this(
            sourceMapper,
            translationMapper,
            fullTextResultMapper,
            llmProviderProvider::getIfAvailable,
            Clock.systemUTC(),
            parser,
            properties,
            routedRequestFactoryProvider.getIfAvailable(),
            persistenceService
        );
    }

    public SubtitleTranslationServiceImpl(
        SubtitleSegmentMapper sourceMapper,
        SubtitleTranslationSegmentMapper translationMapper,
        LlmProvider llmProvider,
        Clock clock,
        SubtitleTranslationResponseParser parser
    ) {
        this(
            sourceMapper,
            translationMapper,
            null,
            () -> llmProvider,
            clock,
            parser,
            new SubtitleTranslationProperties(),
            null,
            new SubtitleTranslationPersistenceService(translationMapper, null)
        );
    }

    public SubtitleTranslationServiceImpl(
        SubtitleSegmentMapper sourceMapper,
        SubtitleTranslationSegmentMapper translationMapper,
        TaskFullTextResultMapper fullTextResultMapper,
        LlmProvider llmProvider,
        Clock clock,
        SubtitleTranslationResponseParser parser,
        SubtitleTranslationProperties properties
    ) {
        this(
            sourceMapper,
            translationMapper,
            fullTextResultMapper,
            () -> llmProvider,
            clock,
            parser,
            properties,
            null,
            new SubtitleTranslationPersistenceService(translationMapper, fullTextResultMapper)
        );
    }

    public SubtitleTranslationServiceImpl(
        SubtitleSegmentMapper sourceMapper,
        SubtitleTranslationSegmentMapper translationMapper,
        TaskFullTextResultMapper fullTextResultMapper,
        LlmProvider llmProvider,
        Clock clock,
        SubtitleTranslationResponseParser parser,
        SubtitleTranslationProperties properties,
        AiModelRoutedLlmRequestFactory routedRequestFactory
    ) {
        this(
            sourceMapper,
            translationMapper,
            fullTextResultMapper,
            () -> llmProvider,
            clock,
            parser,
            properties,
            routedRequestFactory,
            new SubtitleTranslationPersistenceService(translationMapper, fullTextResultMapper)
        );
    }

    private SubtitleTranslationServiceImpl(
        SubtitleSegmentMapper sourceMapper,
        SubtitleTranslationSegmentMapper translationMapper,
        TaskFullTextResultMapper fullTextResultMapper,
        Supplier<LlmProvider> llmProviderSupplier,
        Clock clock,
        SubtitleTranslationResponseParser parser,
        SubtitleTranslationProperties properties,
        AiModelRoutedLlmRequestFactory routedRequestFactory,
        SubtitleTranslationPersistenceService persistenceService
    ) {
        this.sourceMapper = sourceMapper;
        this.fullTextResultMapper = fullTextResultMapper;
        this.llmProviderSupplier = llmProviderSupplier;
        this.clock = clock == null ? Clock.systemUTC() : clock;
        this.parser = parser == null ? new SubtitleTranslationResponseParser() : parser;
        this.properties = properties == null ? new SubtitleTranslationProperties() : properties;
        this.routedRequestFactory = routedRequestFactory;
        this.persistenceService = persistenceService;
    }

    @Override
    public int translateTaskSubtitles(TranslateSubtitleCommand command) {
        return translateTaskSubtitlesWithAiCallRecord(command).savedCount();
    }

    @Override
    public SubtitleTranslationAiCallResult translateTaskSubtitlesWithAiCallRecord(TranslateSubtitleCommand command) {
        ValidatedTranslationCommand validated = SubtitleTranslationValidators.validateCommand(command);
        List<SubtitleSegment> sourceSegments = loadAndValidateSourceSegments(validated);
        if (isFullTextMode()) {
            return translateFullText(validated, sourceSegments);
        }
        LlmProvider llmProvider = resolveLlmProvider();
        List<GeneratedSubtitleTranslation> generated = generateTranslations(llmProvider, validated, sourceSegments);
        String provider = normalizeProvider(firstNonBlank(generated.getFirst().result().provider(), llmProvider.providerName()));

        LocalDateTime now = LocalDateTime.ofInstant(clock.instant(), clock.getZone());
        List<SubtitleTranslationSegment> translations = new ArrayList<>(generated.size());
        for (GeneratedSubtitleTranslation translated : generated) {
            translations.add(toEntity(
                validated,
                translated.sourceSegment(),
                translated.translatedText(),
                provider,
                now
            ));
        }
        int insertedCount = persistenceService.replaceSegmentTranslations(
            validated.taskId(), validated.userId(), validated.targetLanguage(), List.copyOf(translations)
        );
        UsageTotals usage = UsageTotals.from(generated);
        return new SubtitleTranslationAiCallResult(
            insertedCount,
            provider,
            generated.getFirst().result().model(),
            usage.duration(),
            usage.promptTokens(),
            usage.completionTokens(),
            usage.totalTokens(),
            sourceSegments.size(),
            insertedCount,
            null,
            null
        );
    }

    @Override
    public int deleteTranslations(String taskId, Long userId, String targetLanguage) {
        ValidatedTranslationScope scope = SubtitleTranslationValidators.validateScope(taskId, userId, targetLanguage);
        return persistenceService.deleteTranslations(
            scope.taskId(),
            scope.userId(),
            scope.targetLanguage()
        );
    }

    private List<SubtitleSegment> loadAndValidateSourceSegments(ValidatedTranslationCommand command) {
        List<SubtitleSegment> sourceSegments = sourceMapper.selectByTaskIdAndUserId(command.taskId(), command.userId());
        if (sourceSegments == null || sourceSegments.isEmpty()) {
            throw validationFailure("Source subtitle segments are required");
        }
        int maxSourceSegments = isFullTextMode()
            ? properties.getFullText().getMaxSourceSegments()
            : MAX_SOURCE_SEGMENTS;
        if (sourceSegments.size() > maxSourceSegments) {
            throw validationFailure("Source subtitle segment count is invalid");
        }
        Set<Integer> indexes = new HashSet<>();
        for (SubtitleSegment segment : sourceSegments) {
            validateSourceSegment(segment, command);
            if (!indexes.add(segment.getSegmentIndex())) {
                throw validationFailure("Source subtitle segment index is invalid");
            }
        }
        return sourceSegments.stream()
            .sorted(Comparator.comparing(SubtitleSegment::getSegmentIndex))
            .toList();
    }

    private boolean isFullTextMode() {
        return fullTextResultMapper != null
            && properties.getFullText() != null
            && properties.getFullText().isEnabled();
    }

    private SubtitleTranslationAiCallResult translateFullText(
        ValidatedTranslationCommand validated,
        List<SubtitleSegment> sourceSegments
    ) {
        String sourceFullText = buildSourceFullText(sourceSegments);
        if (sourceFullText.isBlank()) {
            throw validationFailure("Source full text is required");
        }
        if (shouldSkipChineseFullTextTranslation(
            validated.sourceLanguage(),
            validated.targetLanguage(),
            sourceFullText
        )) {
            return saveSkippedChineseAlignedTranslation(validated, sourceSegments, sourceFullText);
        }

        LlmProvider llmProvider = resolveLlmProvider();
        AlignedTranslationRun run = generateAlignedTranslations(llmProvider, validated, sourceSegments);
        validateTranslationCoverage(sourceSegments, run.translations());
        String translatedFullText = buildTranslatedFullText(run.translations());
        validateFullTextTranslation(validated, sourceSegments, run.translations(), sourceFullText, translatedFullText);
        LlmResult firstResult = run.results().getFirst();
        String provider = normalizeProvider(firstNonBlank(firstResult.provider(), llmProvider.providerName()));
        persistDualOutput(validated, sourceSegments, run.translations(), sourceFullText, translatedFullText, provider);
        UsageTotals usage = UsageTotals.fromResults(run.results());
        return new SubtitleTranslationAiCallResult(
            sourceSegments.size(),
            provider,
            firstResult.model(),
            usage.duration(),
            usage.promptTokens(),
            usage.completionTokens(),
            usage.totalTokens(),
            sourceSegments.size(),
            sourceSegments.size(),
            null,
            null
        );
    }

    private SubtitleTranslationAiCallResult saveSkippedChineseAlignedTranslation(
        ValidatedTranslationCommand validated,
        List<SubtitleSegment> sourceSegments,
        String sourceFullText
    ) {
        log.info(
            "event=llm_full_text_translation_skipped taskId={} sourceLanguage={} targetLanguage={} sourceFullTextLength={} skipTranslation=true reason=source_already_target_language",
            SafeLogSanitizer.sanitize(validated.taskId()),
            SafeLogSanitizer.sanitize(validated.sourceLanguage()),
            SafeLogSanitizer.sanitize(validated.targetLanguage()),
            sourceFullText.length()
        );
        String provider = normalizeProvider(SOURCE_ALREADY_TARGET_PROVIDER);
        List<GeneratedSubtitleTranslation> generated = sourceSegments.stream()
            .map(source -> new GeneratedSubtitleTranslation(source, source.getText().strip(), null))
            .toList();
        persistDualOutput(validated, sourceSegments, generated, sourceFullText, sourceFullText, provider);
        return new SubtitleTranslationAiCallResult(
            sourceSegments.size(),
            provider,
            null,
            Duration.ZERO,
            null,
            null,
            null,
            sourceSegments.size(),
            sourceSegments.size(),
            null,
            null
        );
    }

    private AlignedTranslationRun generateAlignedTranslations(
        LlmProvider llmProvider,
        ValidatedTranslationCommand command,
        List<SubtitleSegment> sourceSegments
    ) {
        List<List<SubtitleSegment>> batches = createTranslationBatches(
            sourceSegments,
            properties.getFullText().getBatchMaxSegments(),
            properties.getFullText().getBatchMaxInputChars()
        );
        List<LlmResult> results = new ArrayList<>();
        List<GeneratedSubtitleTranslation> generated = new ArrayList<>(sourceSegments.size());
        for (List<SubtitleSegment> batch : batches) {
            generated.addAll(generateAlignedBatchWithSplitRetry(llmProvider, command, batch, 0, results));
        }
        generated.sort(Comparator.comparing(item -> item.sourceSegment().getSegmentIndex()));
        return new AlignedTranslationRun(List.copyOf(generated), List.copyOf(results));
    }

    private List<GeneratedSubtitleTranslation> generateAlignedBatchWithSplitRetry(
        LlmProvider llmProvider,
        ValidatedTranslationCommand command,
        List<SubtitleSegment> batch,
        int depth,
        List<LlmResult> observedResults
    ) {
        if (depth > properties.getFullText().getSingleSegmentMaxDepth()) {
            throw new BusinessException(ErrorCode.AI_PROVIDER_FAILED, "Aligned subtitle translation split depth exceeded");
        }
        int semanticMaxAttempts = properties.getFullText().getSemanticMaxAttempts();
        String semanticRetryReason = null;
        for (int semanticAttempt = 1; semanticAttempt <= semanticMaxAttempts; semanticAttempt++) {
            LlmResult result;
            try {
                result = generateAlignedBatchTranslation(
                    llmProvider,
                    command,
                    batch,
                    semanticAttempt,
                    semanticRetryReason
                );
                if (result != null) {
                    observedResults.add(result);
                }
            } catch (BusinessException ex) {
                if (isRetryableOutputFailure(ex)) {
                    return splitAndRetryAlignedBatch(llmProvider, command, batch, depth, observedResults, ex);
                }
                throw ex;
            }
            if (result == null || isTruncatedResult(result)) {
                return splitAndRetryAlignedBatch(
                    llmProvider,
                    command,
                    batch,
                    depth,
                    observedResults,
                    new BusinessException(
                        ErrorCode.AI_PROVIDER_FAILED,
                        "OUTPUT_TRUNCATED Aligned translation output is incomplete"
                    )
                );
            }
            List<GeneratedSubtitleTranslation> generated;
            try {
                List<SubtitleTranslationResponseParser.ParsedTranslationSegment> parsed = parser.parse(
                    result.content(),
                    batch
                );
                generated = new ArrayList<>(parsed.size());
                for (SubtitleTranslationResponseParser.ParsedTranslationSegment translated : parsed) {
                    generated.add(new GeneratedSubtitleTranslation(
                        sourceByIndex(batch, translated.segmentIndex()),
                        translated.text(),
                        null
                    ));
                }
            } catch (BusinessException ex) {
                if (SubtitleTranslationResponseParser.classifyBatchOutputException(ex).retryable()) {
                    return splitAndRetryAlignedBatch(llmProvider, command, batch, depth, observedResults, ex);
                }
                throw ex;
            }
            SemanticValidation validation = validateAlignedBatchSemantics(command, batch, generated);
            if (validation.valid()) {
                return List.copyOf(generated);
            }
            logSemanticRetry(command, batch, generated, validation, semanticAttempt, depth);
            semanticRetryReason = validation.reason();
            if (semanticAttempt == semanticMaxAttempts) {
                return splitAndRetryAlignedBatch(
                    llmProvider,
                    command,
                    batch,
                    depth,
                    observedResults,
                    semanticFailure(validation.reason())
                );
            }
        }
        throw new BusinessException(ErrorCode.AI_PROVIDER_FAILED, "Aligned subtitle semantic retry exhausted");
    }

    private LlmResult generateAlignedBatchTranslation(
        LlmProvider llmProvider,
        ValidatedTranslationCommand command,
        List<SubtitleSegment> batch,
        int semanticAttempt,
        String semanticRetryReason
    ) {
        LlmRequest request = routeRequest(
            AiModelStage.TRANSLATION_FULL_TEXT,
            semanticAttempt <= 1
                ? SubtitleTranslationPromptFactory.buildAlignedBatch(
                    command,
                    batch,
                    properties.getFullText().getRequestTimeout(),
                    properties.getFullText().getMaxTokens(),
                    properties.getFullText().getMaxAttempts()
                )
                : SubtitleTranslationPromptFactory.buildAlignedBatchSemanticRetry(
                    command,
                    batch,
                    properties.getFullText().getRequestTimeout(),
                    properties.getFullText().getMaxTokens(),
                    properties.getFullText().getMaxAttempts(),
                    semanticAttempt,
                    semanticRetryReason
                )
        );
        log.info(
            "event=llm_aligned_batch_translation_started taskId={} mode=alignedBatch segmentCount={} inputCharCount={} requestTimeoutMillis={} maxTokens={} maxAttempts={} promptChars={} model={} stream=false",
            SafeLogSanitizer.sanitize(command.taskId()),
            batch.size(),
            inputCharCount(batch),
            request.timeout().toMillis(),
            request.maxTokens(),
            request.maxAttempts(),
            promptChars(request),
            SafeLogSanitizer.sanitize(llmProvider.modelNameForDiagnostics())
        );
        long startedNanos = System.nanoTime();
        try {
            LlmResult result = llmProvider.generate(request);
            log.info(
                "event=llm_aligned_batch_translation_completed taskId={} mode=alignedBatch segmentCount={} durationMillis={} totalTokens={} outputLength={}",
                SafeLogSanitizer.sanitize(command.taskId()),
                batch.size(),
                elapsedMillis(startedNanos, result == null ? null : result.duration()),
                result == null || result.usage() == null ? null : result.usage().totalTokens(),
                result == null || result.content() == null ? 0 : result.content().length()
            );
            return result;
        } catch (BusinessException ex) {
            throw ex;
        } catch (LlmProviderException ex) {
            throw new BusinessException(ErrorCode.AI_PROVIDER_FAILED, "Aligned subtitle translation provider failed", ex);
        } catch (RuntimeException ex) {
            throw new BusinessException(ErrorCode.AI_PROVIDER_FAILED, "Aligned subtitle translation provider failed", ex);
        }
    }

    private static SemanticValidation validateAlignedBatchSemantics(
        ValidatedTranslationCommand command,
        List<SubtitleSegment> sourceSegments,
        List<GeneratedSubtitleTranslation> generated
    ) {
        String sourceText = sourceSegments.stream()
            .map(SubtitleSegment::getText)
            .map(text -> text == null ? "" : text.strip())
            .reduce("", (left, right) -> left.isBlank() ? right : left + "\n" + right)
            .strip();
        String translatedText = generated.stream()
            .map(GeneratedSubtitleTranslation::translatedText)
            .map(text -> text == null ? "" : text.strip())
            .reduce("", (left, right) -> left.isBlank() ? right : left + "\n" + right)
            .strip();
        SemanticMetrics metrics = semanticMetrics(translatedText);
        if (isTechnicalTermOnlyBatch(sourceSegments, generated)) {
            return SemanticValidation.passed(metrics);
        }
        boolean languagesDiffer = !command.sourceLanguage().equalsIgnoreCase(command.targetLanguage());
        boolean validateChinese = isChineseLanguage(command.targetLanguage())
            && !isChineseLanguage(command.sourceLanguage());
        if (languagesDiffer) {
            for (GeneratedSubtitleTranslation translation : generated) {
                if (isTechnicalTermPair(translation)) {
                    continue;
                }
                String segmentSource = translation.sourceSegment().getText();
                String segmentTranslation = translation.translatedText();
                if (isTooSimilarToSource(segmentSource, segmentTranslation)) {
                    return SemanticValidation.failed(UNTRANSLATED_TEXT, metrics);
                }
                if (validateChinese && containsCompleteEnglishProse(segmentTranslation)) {
                    return SemanticValidation.failed(TARGET_LANGUAGE_MISMATCH, metrics);
                }
            }
            if (isTooSimilarToSource(sourceText, translatedText)) {
                return SemanticValidation.failed(UNTRANSLATED_TEXT, metrics);
            }
        }
        if (validateChinese && !hasEnoughChineseText(translatedText)) {
            return SemanticValidation.failed(TARGET_LANGUAGE_MISMATCH, metrics);
        }
        return SemanticValidation.passed(metrics);
    }

    private static boolean isTechnicalTermOnlyBatch(
        List<SubtitleSegment> sourceSegments,
        List<GeneratedSubtitleTranslation> generated
    ) {
        if (sourceSegments == null || generated == null || sourceSegments.size() != generated.size()) {
            return false;
        }
        for (GeneratedSubtitleTranslation translation : generated) {
            if (!isTechnicalTermPair(translation)) {
                return false;
            }
        }
        return true;
    }

    private static boolean isTechnicalTermPair(GeneratedSubtitleTranslation translation) {
        return translation != null && translation.sourceSegment() != null
            && isTechnicalTermFragment(translation.sourceSegment().getText())
            && isTechnicalTermFragment(translation.translatedText());
    }

    private static boolean isTechnicalTermFragment(String value) {
        if (value == null || value.isBlank()) {
            return false;
        }
        String text = value.strip();
        if (text.length() > 80 || text.indexOf('\n') >= 0 || text.indexOf('\r') >= 0
            || text.matches(".*[!?;\\u3002\\uff01\\uff1f\\uff1b].*")) {
            return false;
        }
        if (isEstablishedMultiWordTechnicalPhrase(text)) {
            return true;
        }
        String[] tokens = text.split("\\s+");
        if (tokens.length == 0 || tokens.length > 5) {
            return false;
        }
        for (String rawToken : tokens) {
            if (!isTechnicalFragmentToken(rawToken)) {
                return false;
            }
        }
        return true;
    }

    private static boolean isTechnicalFragmentToken(String rawToken) {
        if (rawToken == null || rawToken.isBlank()) {
            return false;
        }
        String token = rawToken.replaceAll("^[\\[\\]{},:.]+|[\\[\\]{},:.]+$", "")
            .replaceAll("^`+|`+$", "");
        if (isExplicitCodeIdentifier(token)) {
            return true;
        }
        token = token.replaceAll("^[()]+|[()]+$", "");
        return !token.isBlank() && isTechnicalToken(token);
    }

    private static boolean isExplicitCodeIdentifier(String token) {
        return token != null && (token.matches("@[A-Za-z_$][A-Za-z0-9_$]*")
            || token.matches("[A-Za-z_$][A-Za-z0-9_$]*\\(\\)"));
    }

    private static boolean isTechnicalToken(String token) {
        String normalized = token.toLowerCase(Locale.ROOT);
        if (ESTABLISHED_TECHNICAL_TERMS.contains(normalized) || token.matches("[0-9]+(?:\\.[0-9]+)*")) {
            return true;
        }
        if (token.matches("[A-Z][A-Z0-9_-]{1,}") || token.matches(".*[0-9].*")) {
            return true;
        }
        if (token.matches("[A-Z][a-z0-9]+(?:[A-Z][A-Za-z0-9]*)+")
            || token.matches("[a-z][a-z0-9]+(?:[A-Z][A-Za-z0-9]*)+")) {
            return true;
        }
        return token.matches("[A-Za-z_$][A-Za-z0-9_$]*(?:[._+#/:-][A-Za-z0-9_$]+)+");
    }

    private static boolean containsCompleteEnglishProse(String value) {
        if (value == null || value.isBlank()) {
            return false;
        }
        String valueWithoutTechnicalPhrases = removeEstablishedMultiWordTechnicalPhrases(value);
        boolean establishedTechnicalPhraseRemoved = !valueWithoutTechnicalPhrases.equals(value);
        java.util.regex.Matcher matcher = java.util.regex.Pattern.compile(
            "@?[A-Za-z][A-Za-z0-9._+#/:'-]*(?:\\(\\))?"
                + "(?:\\s+@?[A-Za-z][A-Za-z0-9._+#/:'-]*(?:\\(\\))?)*"
        ).matcher(valueWithoutTechnicalPhrases);
        while (matcher.find()) {
            String[] words = matcher.group().strip().split("\\s+");
            int nonTechnicalWords = 0;
            boolean containsProseMarker = false;
            for (String word : words) {
                String normalizedWord = word.replaceAll("^[^A-Za-z]+|[^A-Za-z]+$", "")
                    .toLowerCase(Locale.ROOT);
                if (ENGLISH_PROSE_MARKERS.contains(normalizedWord)) {
                    containsProseMarker = true;
                }
                if (!isTechnicalFragmentToken(word)) {
                    nonTechnicalWords++;
                }
            }
            if (containsProseMarker
                || (words.length >= 2 && nonTechnicalWords > 0)
                || (establishedTechnicalPhraseRemoved && nonTechnicalWords > 0)) {
                return true;
            }
        }
        return false;
    }

    private static boolean isEstablishedMultiWordTechnicalPhrase(String value) {
        String normalized = value.strip()
            .replaceAll("^[\\s\\[\\](){}.,:]+|[\\s\\[\\](){}.,:]+$", "")
            .replaceAll("\\s+", " ")
            .toLowerCase(Locale.ROOT);
        return ESTABLISHED_MULTI_WORD_TECHNICAL_PHRASES.contains(normalized);
    }

    private static String removeEstablishedMultiWordTechnicalPhrases(String value) {
        String remaining = value;
        for (String phrase : ESTABLISHED_MULTI_WORD_TECHNICAL_PHRASES) {
            String phrasePattern = phrase.replace(" ", "\\s+");
            remaining = remaining.replaceAll(
                "(?i)(?<![A-Za-z0-9])" + phrasePattern + "(?![A-Za-z0-9])",
                " "
            );
        }
        return remaining;
    }

    private static SemanticMetrics semanticMetrics(String translatedText) {
        int translatedCharCount = translatedText == null ? 0 : translatedText.length();
        long cjkCharCount = translatedText == null
            ? 0
            : translatedText.chars().filter(SubtitleTranslationServiceImpl::isCjk).count();
        long letterOrCjkCount = translatedText == null
            ? 0
            : translatedText.chars().filter(value -> Character.isLetter(value) || isCjk(value)).count();
        double cjkRatio = letterOrCjkCount == 0 ? 0.0d : cjkCharCount / (double) letterOrCjkCount;
        return new SemanticMetrics(translatedCharCount, cjkCharCount, cjkRatio);
    }

    private static void logSemanticRetry(
        ValidatedTranslationCommand command,
        List<SubtitleSegment> batch,
        List<GeneratedSubtitleTranslation> generated,
        SemanticValidation validation,
        int semanticAttempt,
        int depth
    ) {
        log.info(
            "event=llm_aligned_batch_semantic_retry taskId={} reason={} semanticAttempt={} segmentCount={} inputCharCount={} translatedCharCount={} cjkCharCount={} cjkRatio={} depth={}",
            SafeLogSanitizer.sanitize(command.taskId()),
            validation.reason(),
            semanticAttempt,
            batch.size(),
            inputCharCount(batch),
            validation.metrics().translatedCharCount(),
            validation.metrics().cjkCharCount(),
            validation.metrics().cjkRatio(),
            depth
        );
    }

    private static BusinessException semanticFailure(String reason) {
        String message = UNTRANSLATED_TEXT.equals(reason)
            ? "UNTRANSLATED_TEXT Subtitle translation provider returned untranslated text"
            : "TARGET_LANGUAGE_MISMATCH Subtitle translation provider returned non-Chinese text";
        return new BusinessException(ErrorCode.AI_PROVIDER_FAILED, message);
    }

    private List<GeneratedSubtitleTranslation> splitAndRetryAlignedBatch(
        LlmProvider llmProvider,
        ValidatedTranslationCommand command,
        List<SubtitleSegment> batch,
        int depth,
        List<LlmResult> observedResults,
        BusinessException original
    ) {
        if (depth >= properties.getFullText().getSingleSegmentMaxDepth()) {
            throw original;
        }
        if (batch.size() > 1) {
            int splitPoint = batch.size() / 2;
            List<GeneratedSubtitleTranslation> generated = new ArrayList<>(batch.size());
            generated.addAll(generateAlignedBatchWithSplitRetry(
                llmProvider,
                command,
                List.copyOf(batch.subList(0, splitPoint)),
                depth + 1,
                observedResults
            ));
            generated.addAll(generateAlignedBatchWithSplitRetry(
                llmProvider,
                command,
                List.copyOf(batch.subList(splitPoint, batch.size())),
                depth + 1,
                observedResults
            ));
            return List.copyOf(generated);
        }
        SubtitleSegment source = batch.getFirst();
        int maxPieceChars = Math.max(2, properties.getFullText().getSingleSegmentMaxPieceChars());
        if (!properties.getFullText().isSingleSegmentSplitEnabled()
            || source.getText().length() <= maxPieceChars) {
            throw original;
        }
        int minPieceChars = Math.min(
            Math.max(1, properties.getFullText().getSingleSegmentMinPieceChars()),
            maxPieceChars - 1
        );
        List<String> pieces = splitSingleSegmentText(source.getText(), maxPieceChars, minPieceChars);
        if (pieces.size() < 2) {
            throw original;
        }
        List<GeneratedSubtitleTranslation> pieceTranslations = new ArrayList<>(pieces.size());
        for (SubtitleSegment piece : temporaryPieceSegments(source, pieces)) {
            pieceTranslations.addAll(generateAlignedBatchWithSplitRetry(
                llmProvider,
                command,
                List.of(piece),
                depth + 1,
                observedResults
            ));
        }
        String translated = pieceTranslations.stream()
            .sorted(Comparator.comparing(item -> item.sourceSegment().getSegmentIndex()))
            .map(GeneratedSubtitleTranslation::translatedText)
            .reduce("", (left, right) -> left.isBlank() ? right.strip() : left + " " + right.strip())
            .strip();
        if (translated.isBlank()) {
            throw original;
        }
        return List.of(new GeneratedSubtitleTranslation(source, translated, null));
    }

    static List<List<SubtitleSegment>> createTranslationBatches(
        List<SubtitleSegment> sourceSegments,
        int maxSegments,
        int maxInputChars
    ) {
        int segmentLimit = Math.max(1, maxSegments);
        int charLimit = Math.max(1, maxInputChars);
        List<List<SubtitleSegment>> batches = new ArrayList<>();
        List<SubtitleSegment> current = new ArrayList<>();
        int currentChars = 0;
        for (SubtitleSegment source : sourceSegments) {
            int textChars = source.getText().length();
            if (!current.isEmpty() && (current.size() >= segmentLimit || (long) currentChars + textChars > charLimit)) {
                batches.add(List.copyOf(current));
                current.clear();
                currentChars = 0;
            }
            current.add(source);
            currentChars += textChars;
        }
        if (!current.isEmpty()) {
            batches.add(List.copyOf(current));
        }
        return List.copyOf(batches);
    }

    private static List<String> splitSingleSegmentText(String text, int maxPieceChars, int minPieceChars) {
        String sourceText = text == null ? "" : text.strip();
        if (sourceText.length() <= maxPieceChars) {
            return List.of(sourceText);
        }
        List<String> pieces = new ArrayList<>();
        int cursor = 0;
        while (cursor < sourceText.length()) {
            int maxEnd = Math.min(sourceText.length(), cursor + maxPieceChars);
            int end = maxEnd == sourceText.length()
                ? maxEnd
                : naturalBoundary(sourceText, cursor, maxEnd, minPieceChars);
            String piece = sourceText.substring(cursor, end).strip();
            if (!piece.isBlank()) {
                pieces.add(piece);
            }
            cursor = end;
            while (cursor < sourceText.length() && Character.isWhitespace(sourceText.charAt(cursor))) {
                cursor++;
            }
        }
        return List.copyOf(pieces);
    }

    private static int naturalBoundary(String text, int start, int maxEnd, int minPieceChars) {
        int earliest = Math.min(maxEnd, start + Math.max(1, minPieceChars));
        for (int index = maxEnd - 1; index >= earliest; index--) {
            if (".!?;,:\u3002\uff01\uff1f\uff1b\uff0c\u3001\uff1a".indexOf(text.charAt(index)) >= 0) {
                return index + 1;
            }
        }
        return maxEnd;
    }

    private static List<SubtitleSegment> temporaryPieceSegments(SubtitleSegment source, List<String> pieces) {
        List<SubtitleSegment> segments = new ArrayList<>(pieces.size());
        for (int index = 0; index < pieces.size(); index++) {
            SubtitleSegment piece = new SubtitleSegment();
            piece.setTaskId(source.getTaskId());
            piece.setUserId(source.getUserId());
            piece.setSegmentIndex(index);
            piece.setStartMillis(source.getStartMillis());
            piece.setEndMillis(source.getEndMillis());
            piece.setLanguage(source.getLanguage());
            piece.setText(pieces.get(index));
            piece.setProvider(source.getProvider());
            segments.add(piece);
        }
        return List.copyOf(segments);
    }

    private static SubtitleSegment sourceByIndex(List<SubtitleSegment> sourceSegments, int segmentIndex) {
        return sourceSegments.stream()
            .filter(source -> source.getSegmentIndex() == segmentIndex)
            .findFirst()
            .orElseThrow(() -> new BusinessException(ErrorCode.AI_PROVIDER_FAILED, "Translation coverage validation failed"));
    }

    private static boolean isRetryableOutputFailure(Throwable error) {
        if (SubtitleTranslationResponseParser.classifyBatchOutputException(error).retryable()) {
            return true;
        }
        Throwable current = error;
        int depth = 0;
        while (current != null && depth < 16) {
            if (current instanceof BusinessException businessException
                && businessException.errorCode() == ErrorCode.AI_PROVIDER_TIMEOUT) {
                return false;
            }
            String message = current.getMessage();
            if (message != null) {
                String normalized = message.toLowerCase(java.util.Locale.ROOT).replace('-', '_');
                if (normalized.contains("timeout") || normalized.contains("unauthorized")
                    || normalized.contains("forbidden") || normalized.contains("api_key")
                    || normalized.contains("not configured")) {
                    return false;
                }
                if (normalized.contains("output truncated") || normalized.contains("output was truncated")
                    || normalized.contains("finishreason=length") || normalized.contains("finish_reason=length")
                    || normalized.contains("max_tokens")) {
                    return true;
                }
            }
            current = current.getCause();
            depth++;
        }
        return false;
    }

    private static boolean isTruncatedResult(LlmResult result) {
        if (result == null || result.finishReason() == null) {
            return false;
        }
        String reason = result.finishReason().strip().toLowerCase(java.util.Locale.ROOT).replace('-', '_');
        return "length".equals(reason) || "max_tokens".equals(reason);
    }

    private static int inputCharCount(List<SubtitleSegment> batch) {
        return batch.stream().map(SubtitleSegment::getText).mapToInt(String::length).sum();
    }

    private void persistDualOutput(
        ValidatedTranslationCommand validated,
        List<SubtitleSegment> sourceSegments,
        List<GeneratedSubtitleTranslation> generated,
        String sourceFullText,
        String translatedFullText,
        String provider
    ) {
        validateTranslationCoverage(sourceSegments, generated);
        LocalDateTime now = LocalDateTime.ofInstant(clock.instant(), clock.getZone());
        List<SubtitleTranslationSegment> translations = new ArrayList<>(generated.size());
        for (GeneratedSubtitleTranslation translation : generated) {
            translations.add(toEntity(
                validated,
                translation.sourceSegment(),
                translation.translatedText(),
                provider,
                now
            ));
        }
        persistenceService.replaceDualOutput(
            validated.taskId(),
            validated.userId(),
            validated.targetLanguage(),
            List.copyOf(translations),
            toFullTextEntity(validated, sourceFullText, translatedFullText, provider)
        );
    }

    private static void validateTranslationCoverage(
        List<SubtitleSegment> sourceSegments,
        List<GeneratedSubtitleTranslation> generated
    ) {
        if (sourceSegments == null || sourceSegments.isEmpty() || generated == null
            || generated.size() != sourceSegments.size()) {
            throw new BusinessException(ErrorCode.AI_PROVIDER_FAILED, "Translation coverage validation failed");
        }
        Set<Integer> sourceIndexes = new HashSet<>();
        Set<Integer> translatedIndexes = new HashSet<>();
        for (SubtitleSegment source : sourceSegments) {
            sourceIndexes.add(source.getSegmentIndex());
        }
        for (GeneratedSubtitleTranslation translation : generated) {
            if (translation == null || translation.sourceSegment() == null
                || translation.translatedText() == null || translation.translatedText().isBlank()
                || !translatedIndexes.add(translation.sourceSegment().getSegmentIndex())) {
                throw new BusinessException(ErrorCode.AI_PROVIDER_FAILED, "Translation coverage validation failed");
            }
        }
        if (!sourceIndexes.equals(translatedIndexes)) {
            throw new BusinessException(ErrorCode.AI_PROVIDER_FAILED, "Translation coverage validation failed");
        }
    }

    private static String buildTranslatedFullText(List<GeneratedSubtitleTranslation> generated) {
        return generated.stream()
            .sorted(Comparator.comparing(item -> item.sourceSegment().getSegmentIndex()))
            .map(GeneratedSubtitleTranslation::translatedText)
            .map(text -> text.replaceAll("\\s+", " ").strip())
            .reduce("", (left, right) -> left.isBlank() ? right : left + "\n\n" + right)
            .strip();
    }

    private static int promptChars(LlmRequest request) {
        return request.messages().stream()
            .mapToInt(message -> message.content().length())
            .sum();
    }

    private static String buildSourceFullText(List<SubtitleSegment> sourceSegments) {
        return sourceSegments.stream()
            .map(SubtitleSegment::getText)
            .filter(text -> text != null && !text.isBlank())
            .map(text -> text.replaceAll("\\s+", " ").strip())
            .reduce("", (left, right) -> left.isBlank() ? right : left + "\n\n" + right)
            .strip();
    }

    private static void validateFullTextTranslation(
        ValidatedTranslationCommand command,
        List<SubtitleSegment> sourceSegments,
        List<GeneratedSubtitleTranslation> generated,
        String sourceFullText,
        String translatedText
    ) {
        if (translatedText.isBlank()) {
            throw new BusinessException(ErrorCode.AI_PROVIDER_FAILED, "Subtitle translation provider returned EMPTY_RESPONSE");
        }
        if (isTechnicalTermOnlyBatch(sourceSegments, generated)) {
            return;
        }
        if (!command.sourceLanguage().equalsIgnoreCase(command.targetLanguage())
            && isTooSimilarToSource(sourceFullText, translatedText)) {
            throw new BusinessException(ErrorCode.AI_PROVIDER_FAILED, "Subtitle translation provider returned untranslated text");
        }
        if (command.targetLanguage().toLowerCase(java.util.Locale.ROOT).startsWith("zh")
            && !hasEnoughChineseText(translatedText)) {
            throw new BusinessException(ErrorCode.AI_PROVIDER_FAILED, "Subtitle translation provider returned non-Chinese text");
        }
    }

    private static boolean hasEnoughChineseText(String translatedText) {
        long cjkCount = translatedText.chars().filter(SubtitleTranslationServiceImpl::isCjk).count();
        if (cjkCount >= 20) {
            return true;
        }
        long letterOrCjkCount = translatedText.chars()
            .filter(value -> Character.isLetter(value) || isCjk(value))
            .count();
        return cjkCount >= 2 && letterOrCjkCount > 0 && cjkCount / (double) letterOrCjkCount >= 0.05;
    }

    private static boolean shouldSkipChineseFullTextTranslation(
        String sourceLanguage,
        String targetLanguage,
        String sourceFullText
    ) {
        if (!isChineseLanguage(sourceLanguage) || !isChineseLanguage(targetLanguage)
            || sourceFullText == null || sourceFullText.isBlank()) {
            return false;
        }
        long cjkCount = sourceFullText.chars().filter(SubtitleTranslationServiceImpl::isCjk).count();
        if (cjkCount < CHINESE_SOURCE_SKIP_MIN_CHARS) {
            return false;
        }
        long effectiveTextChars = sourceFullText.chars()
            .filter(Character::isLetterOrDigit)
            .count();
        return effectiveTextChars > 0 && cjkCount / (double) effectiveTextChars >= CHINESE_SOURCE_SKIP_MIN_RATIO;
    }

    private static boolean isChineseLanguage(String language) {
        if (language == null || language.isBlank()) {
            return false;
        }
        String normalized = language.strip().replace('_', '-').toLowerCase(java.util.Locale.ROOT);
        return normalized.equals("zh") || normalized.startsWith("zh-");
    }

    private static boolean isCjk(int value) {
        return value >= 0x4E00 && value <= 0x9FFF;
    }

    private static long elapsedMillis(long startedNanos, Duration providerDuration) {
        if (providerDuration != null && !providerDuration.isNegative()) {
            return providerDuration.toMillis();
        }
        return Duration.ofNanos(System.nanoTime() - startedNanos).toMillis();
    }

    private static String normalizedForComparison(String value) {
        return value == null
            ? ""
            : value.toLowerCase(java.util.Locale.ROOT).replaceAll("[\\p{P}\\p{S}\\s]+", "");
    }

    private static boolean isTooSimilarToSource(String sourceFullText, String translatedText) {
        String normalizedSource = normalizedForComparison(sourceFullText);
        String normalizedTranslation = normalizedForComparison(translatedText);
        if (normalizedSource.isBlank() || normalizedTranslation.isBlank()) {
            return false;
        }
        if (normalizedSource.equals(normalizedTranslation)) {
            return true;
        }
        int minLength = Math.min(normalizedSource.length(), normalizedTranslation.length());
        int maxLength = Math.max(normalizedSource.length(), normalizedTranslation.length());
        if (minLength < 8 || minLength / (double) maxLength < 0.85) {
            return false;
        }
        return normalizedSource.contains(normalizedTranslation)
            || normalizedTranslation.contains(normalizedSource)
            || hasHighTrigramSimilarity(normalizedSource, normalizedTranslation);
    }

    private static boolean hasHighTrigramSimilarity(String left, String right) {
        if (left.length() > 4096 || right.length() > 4096) {
            return false;
        }
        Set<String> leftTrigrams = trigrams(left);
        Set<String> rightTrigrams = trigrams(right);
        if (leftTrigrams.isEmpty() || rightTrigrams.isEmpty()) {
            return false;
        }
        int intersection = 0;
        for (String trigram : leftTrigrams) {
            if (rightTrigrams.contains(trigram)) {
                intersection++;
            }
        }
        return (2.0d * intersection) / (leftTrigrams.size() + rightTrigrams.size()) >= 0.9d;
    }

    private static Set<String> trigrams(String value) {
        Set<String> trigrams = new HashSet<>();
        for (int index = 0; index <= value.length() - 3; index++) {
            trigrams.add(value.substring(index, index + 3));
        }
        return trigrams;
    }

    private TaskFullTextResult toFullTextEntity(
        ValidatedTranslationCommand command,
        String sourceFullText,
        String translatedFullText,
        String provider
    ) {
        LocalDateTime now = LocalDateTime.ofInstant(clock.instant(), clock.getZone());
        TaskFullTextResult entity = new TaskFullTextResult();
        entity.setTaskId(command.taskId());
        entity.setUserId(command.userId());
        entity.setSourceLanguage(command.sourceLanguage());
        entity.setTargetLanguage(command.targetLanguage());
        entity.setSourceFullText(sourceFullText);
        entity.setTranslatedFullText(translatedFullText);
        entity.setProvider(provider);
        entity.setCreatedAt(now);
        entity.setUpdatedAt(now);
        return entity;
    }

    private static void validateSourceSegment(SubtitleSegment segment, ValidatedTranslationCommand command) {
        if (segment == null
            || segment.getSegmentIndex() == null
            || segment.getStartMillis() == null
            || segment.getEndMillis() == null) {
            throw validationFailure("Source subtitle segment is invalid");
        }
        if (!command.taskId().equals(segment.getTaskId()) || !command.userId().equals(segment.getUserId())) {
            throw validationFailure("Source subtitle segment is invalid");
        }
        if (segment.getSegmentIndex() < 0) {
            throw validationFailure("Source subtitle segment index is invalid");
        }
        if (segment.getStartMillis() < 0) {
            throw validationFailure("Source subtitle segment start is invalid");
        }
        if (segment.getEndMillis() < segment.getStartMillis()) {
            throw validationFailure("Source subtitle segment end is invalid");
        }
        String text = requiredText(segment.getText(), "Source subtitle segment text is required");
        if (SubtitleSensitiveDataValidator.containsSensitiveData(text)) {
            throw validationFailure("Source subtitle segment text is invalid");
        }
    }

    private LlmProvider resolveLlmProvider() {
        LlmProvider llmProvider = llmProviderSupplier == null ? null : llmProviderSupplier.get();
        if (llmProvider == null) {
            throw new BusinessException(ErrorCode.AI_PROVIDER_FAILED, "Subtitle translation provider is not configured");
        }
        return llmProvider;
    }

    private List<GeneratedSubtitleTranslation> generateTranslations(
        LlmProvider llmProvider,
        ValidatedTranslationCommand command,
        List<SubtitleSegment> sourceSegments
    ) {
        List<GeneratedSubtitleTranslation> generated = new ArrayList<>();
        for (SubtitleSegment sourceSegment : sourceSegments) {
            LlmResult result = generateTranslation(llmProvider, command, sourceSegment);
            generated.add(new GeneratedSubtitleTranslation(
                sourceSegment,
                cleanPlainTextResponse(result.content()),
                result
            ));
        }
        return generated;
    }

    private LlmResult generateTranslation(
        LlmProvider llmProvider,
        ValidatedTranslationCommand command,
        SubtitleSegment sourceSegment
    ) {
        try {
            LlmRequest request = routeRequest(
                AiModelStage.SUBTITLE_TRANSLATION,
                SubtitleTranslationPromptFactory.build(command, sourceSegment)
            );
            return llmProvider.generate(request);
        } catch (BusinessException ex) {
            throw ex;
        } catch (LlmProviderException ex) {
            throw new BusinessException(ErrorCode.AI_PROVIDER_FAILED, "Subtitle translation provider failed", ex);
        } catch (RuntimeException ex) {
            throw new BusinessException(ErrorCode.AI_PROVIDER_FAILED, "Subtitle translation provider failed", ex);
        }
    }

    private LlmRequest routeRequest(AiModelStage stage, LlmRequest request) {
        return routedRequestFactory == null ? request : routedRequestFactory.apply(stage, request);
    }

    private static String cleanPlainTextResponse(String content) {
        String cleaned = stripMarkdownFence(content == null ? "" : content).strip();
        if (cleaned.isBlank()) {
            throw new BusinessException(ErrorCode.AI_PROVIDER_FAILED, "Subtitle translation provider returned EMPTY_RESPONSE");
        }
        return cleaned;
    }

    private static String stripMarkdownFence(String content) {
        String stripped = content.strip();
        if (!stripped.startsWith("```")) {
            return stripped;
        }
        int firstLineEnd = stripped.indexOf('\n');
        if (firstLineEnd < 0) {
            return stripped;
        }
        int closingFence = stripped.lastIndexOf("```");
        if (closingFence <= firstLineEnd) {
            return stripped;
        }
        return stripped.substring(firstLineEnd + 1, closingFence);
    }

    private static String normalizeProvider(String provider) {
        if (provider == null || provider.isBlank()) {
            return null;
        }
        String normalized = provider.strip();
        if (normalized.length() > MAX_PROVIDER_LENGTH || SubtitleSensitiveDataValidator.containsSensitiveData(normalized)) {
            throw validationFailure("Subtitle translation provider is invalid");
        }
        return normalized;
    }

    private static SubtitleTranslationSegment toEntity(
        ValidatedTranslationCommand command,
        SubtitleSegment source,
        String translatedText,
        String provider,
        LocalDateTime now
    ) {
        SubtitleTranslationSegment entity = new SubtitleTranslationSegment();
        entity.setTaskId(command.taskId());
        entity.setUserId(command.userId());
        entity.setSegmentIndex(source.getSegmentIndex());
        entity.setStartMillis(source.getStartMillis());
        entity.setEndMillis(source.getEndMillis());
        entity.setSourceLanguage(command.sourceLanguage());
        entity.setTargetLanguage(command.targetLanguage());
        entity.setTranslatedText(translatedText.strip());
        entity.setProvider(provider);
        entity.setCreatedAt(now);
        entity.setUpdatedAt(now);
        return entity;
    }

    private static String firstNonBlank(String first, String fallback) {
        return first == null || first.isBlank() ? fallback : first;
    }

    private static String requiredText(String value, String message) {
        if (value == null || value.isBlank()) {
            throw validationFailure(message);
        }
        return value.strip();
    }

    private static BusinessException validationFailure(String message) {
        return new BusinessException(ErrorCode.COMMON_VALIDATION_FAILED, message);
    }

    private record GeneratedSubtitleTranslation(
        SubtitleSegment sourceSegment,
        String translatedText,
        LlmResult result
    ) {
    }

    private record AlignedTranslationRun(
        List<GeneratedSubtitleTranslation> translations,
        List<LlmResult> results
    ) {
    }

    private record SemanticMetrics(int translatedCharCount, long cjkCharCount, double cjkRatio) {
    }

    private record SemanticValidation(boolean valid, String reason, SemanticMetrics metrics) {

        private static SemanticValidation passed(SemanticMetrics metrics) {
            return new SemanticValidation(true, null, metrics);
        }

        private static SemanticValidation failed(String reason, SemanticMetrics metrics) {
            return new SemanticValidation(false, reason, metrics);
        }
    }

    private record UsageTotals(
        Duration duration,
        Integer promptTokens,
        Integer completionTokens,
        Integer totalTokens
    ) {

        private static UsageTotals from(List<GeneratedSubtitleTranslation> generated) {
            Duration duration = Duration.ZERO;
            Integer promptTokens = null;
            Integer completionTokens = null;
            Integer totalTokens = null;
            for (GeneratedSubtitleTranslation translation : generated) {
                LlmResult result = translation.result();
                duration = duration.plus(result.duration());
                promptTokens = addNullable(promptTokens, result.usage().promptTokens());
                completionTokens = addNullable(completionTokens, result.usage().completionTokens());
                totalTokens = addNullable(totalTokens, result.usage().totalTokens());
            }
            return new UsageTotals(duration, promptTokens, completionTokens, totalTokens);
        }

        private static UsageTotals fromResults(List<LlmResult> results) {
            Duration duration = Duration.ZERO;
            Integer promptTokens = null;
            Integer completionTokens = null;
            Integer totalTokens = null;
            for (LlmResult result : results) {
                duration = duration.plus(result.duration());
                promptTokens = addNullable(promptTokens, result.usage().promptTokens());
                completionTokens = addNullable(completionTokens, result.usage().completionTokens());
                totalTokens = addNullable(totalTokens, result.usage().totalTokens());
            }
            return new UsageTotals(duration, promptTokens, completionTokens, totalTokens);
        }

        private static Integer addNullable(Integer current, Integer value) {
            if (value == null) {
                return current;
            }
            return current == null ? value : current + value;
        }
    }
}
