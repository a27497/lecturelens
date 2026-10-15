package com.example.courselingo.systemmodel;

import com.example.courselingo.ai.asr.*;
import com.example.courselingo.common.error.ErrorCode;
import com.example.courselingo.common.exception.BusinessException;

import java.util.List;
import java.util.Map;
import java.util.stream.Collectors;

/** Resolves only a supplied task snapshot, never the mutable configuration head. */
public final class SystemModelAsrProvider implements SpeechToTextProvider {
    private static final org.slf4j.Logger LOGGER =
            org.slf4j.LoggerFactory.getLogger(SystemModelAsrProvider.class);
    private final SystemModelExecutionService executions;
    private final Map<SystemModelProtocol, AsrAdapterFactory> factories;

    public SystemModelAsrProvider(
            SystemModelExecutionService executions, List<AsrAdapterFactory> factories) {
        this.executions = executions;
        this.factories =
                factories.stream()
                        .collect(Collectors.toUnmodifiableMap(AsrAdapterFactory::protocol, f -> f));
    }

    @Override
    public SpeechToTextProvider forExecution(SystemModelExecutionRef execution) {
        if (execution == null)
            throw new BusinessException(ErrorCode.SYSTEM_MODEL_CONFIG_UNAVAILABLE);
        var route = executions.route(execution, "ASR_TRANSCRIPTION");
        SpeechToTextProvider delegate;
        if ("MOCK".equals(route.source())) {
            var properties = new MockAsrProperties();
            properties.setDefaultLanguage(route.asr().mockLanguage());
            properties.setDefaultText(route.asr().mockText());
            properties.setSegmentDurationMillis(route.asr().mockSegmentMillis());
            delegate = new MockAsrProvider(properties);
        } else if ("ENV".equals(route.source()) || "DATABASE".equals(route.source())) {
            var factory = factories.get(route.protocol());
            if (factory == null || route.asr() == null)
                throw new BusinessException(ErrorCode.SYSTEM_MODEL_CONFIG_UNAVAILABLE);
            delegate = factory.create(route, executions.credential(execution, "ASR_TRANSCRIPTION"));
        } else {
            throw new BusinessException(ErrorCode.SYSTEM_MODEL_CONFIG_UNAVAILABLE);
        }
        LOGGER.info(
                "event=system_model_asr_pinned taskId={} snapshotId={} configVersion={} source={}"
                    + " provider={}",
                execution.taskId(),
                execution.snapshotId(),
                execution.configVersion(),
                route.source(),
                delegate.providerName());
        return new SpeechToTextProvider() {
            public String providerName() {
                return delegate.providerName();
            }

            public Integer maxAttempts() {
                return route.maxAttempts();
            }

            public long maxAudioFileSizeBytes() {
                if ("MOCK".equals(route.source())) return Long.MAX_VALUE;
                return route.protocol() == SystemModelProtocol.BAILIAN_ASR
                        ? route.asr().bailianMaxAudioBytes()
                        : route.asr().siliconFlowMaxAudioBytes();
            }

            public SpeechToTextResult transcribe(SpeechToTextRequest request) {
                // Recheck task visibility/cancellation for every chunk and retry using the same
                // version.
                executions.route(execution, "ASR_TRANSCRIPTION");
                if (!execution.taskId().equals(request.taskId()))
                    throw new BusinessException(ErrorCode.SYSTEM_MODEL_CONFIG_INVALID);
                long started = System.nanoTime();
                try {
                    var result = delegate.transcribe(request);
                    var metadata = new java.util.LinkedHashMap<String, Object>(result.metadata());
                    metadata.put("systemModelSnapshotId", execution.snapshotId());
                    metadata.put("systemModelConfigVersion", execution.configVersion());
                    metadata.put("systemModelSource", route.source());
                    return new SpeechToTextResult(
                            result.provider(),
                            result.language(),
                            result.fullText(),
                            result.segments(),
                            result.duration(),
                            result.audioDurationMillis(),
                            metadata);
                } catch (AsrProviderException failure) {
                    var safe = AsrCallFailure.provider(failure);
                    LOGGER.info(
                            "event=system_model_asr_failed taskId={} snapshotId={} configVersion={}"
                                + " category={} status={} durationMillis={}",
                            execution.taskId(),
                            execution.snapshotId(),
                            execution.configVersion(),
                            safe.category(),
                            safe.statusCode().orElse(null),
                            (System.nanoTime() - started) / 1_000_000);
                    throw safe;
                } catch (SystemModelCallFailure failure) {
                    throw new AsrCallFailure(
                            AsrCallFailure.Category.NETWORK, failure.details().retryable(), null);
                } catch (RuntimeException failure) {
                    throw new AsrCallFailure(AsrCallFailure.Category.OUTPUT_INVALID, false, null);
                }
            }
        };
    }

    public SpeechToTextResult transcribe(SpeechToTextRequest request) {
        throw new BusinessException(ErrorCode.SYSTEM_MODEL_CONFIG_UNAVAILABLE);
    }

    public String providerName() {
        return "system-model-asr";
    }
}
