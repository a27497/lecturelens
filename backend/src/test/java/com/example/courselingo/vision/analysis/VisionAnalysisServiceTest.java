package com.example.courselingo.vision.analysis;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.doAnswer;
import static org.mockito.Mockito.lenient;
import static org.mockito.Mockito.when;

import com.example.courselingo.modelrouting.AiModelProfile;
import com.example.courselingo.modelrouting.AiModelRoute;
import com.example.courselingo.modelrouting.AiModelRouter;
import com.example.courselingo.modelrouting.AiModelRoutingProperties;
import com.example.courselingo.modelrouting.AiModelStage;
import com.example.courselingo.modelrouting.ModelCapability;
import com.example.courselingo.storage.StorageService;
import com.example.courselingo.vision.analysis.mapper.VideoKeyframeAnalysisMapper;
import com.example.courselingo.vision.keyframe.KeyframeSelectionReason;
import com.example.courselingo.vision.keyframe.VideoKeyframe;
import com.example.courselingo.vision.keyframe.mapper.VideoKeyframeMapper;
import com.example.courselingo.vision.ocr.OcrStatus;
import com.example.courselingo.vision.ocr.VideoKeyframeOcr;
import com.example.courselingo.vision.ocr.mapper.VideoKeyframeOcrMapper;
import com.fasterxml.jackson.databind.ObjectMapper;
import java.io.ByteArrayInputStream;
import java.io.InputStream;
import java.nio.charset.StandardCharsets;
import java.nio.file.Path;
import java.time.Clock;
import java.time.Duration;
import java.time.Instant;
import java.time.LocalDateTime;
import java.time.ZoneOffset;
import java.util.ArrayList;
import java.util.EnumSet;
import java.util.List;
import java.util.Map;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;

@ExtendWith(MockitoExtension.class)
class VisionAnalysisServiceTest {

    private static final Clock CLOCK = Clock.fixed(Instant.parse("2026-07-06T10:00:00Z"), ZoneOffset.UTC);

    @Mock
    private VideoKeyframeMapper keyframeMapper;

    @Mock
    private VideoKeyframeOcrMapper ocrMapper;

    @Mock
    private VideoKeyframeAnalysisMapper analysisMapper;

    private List<VideoKeyframeAnalysis> rows;
    private int deleteCalls;
    private VisionAnalysisProperties properties;

    @BeforeEach
    void setUp() {
        rows = new ArrayList<>();
        deleteCalls = 0;
        lenient().doAnswer(invocation -> {
            rows.add(invocation.getArgument(0, VideoKeyframeAnalysis.class));
            return 1;
        }).when(analysisMapper).insert(any(VideoKeyframeAnalysis.class));
        lenient().doAnswer(invocation -> {
            deleteCalls++;
            rows.clear();
            return 1;
        }).when(analysisMapper).deleteByTaskIdAndUserId("task_1", 42L);
        properties = new VisionAnalysisProperties();
        properties.setEnabled(true);
        properties.setMaxFramesTotal(2);
        properties.setMaxFramesPerMinute(2);
    }

    @Test
    void disabledDoesNotReadImagesOrRouteModels() {
        properties.setEnabled(false);
        VisionAnalysisService service = newService(new VisionModelProvider() {
            @Override
            public String providerName() {
                return "fake-vision";
            }

            @Override
            public VisionAnalysisResult analyze(VisionAnalysisRequest request) {
                throw new AssertionError("provider must not be called when disabled");
            }
        });

        VisionAnalysisScanResult result = service.scan("task_1", 42L);

        assertThat(result.saved()).isZero();
        assertThat(rows).isEmpty();
        assertThat(deleteCalls).isZero();
    }

    @Test
    void fakeProviderSucceededAndEmptyRowsArePersistedIdempotently() {
        when(keyframeMapper.selectByTaskIdAndUserId("task_1", 42L))
            .thenReturn(List.of(
                keyframe(9L, 0L, KeyframeSelectionReason.SCENE_CHANGE),
                keyframe(10L, 30_000L, KeyframeSelectionReason.CONTENT_CHANGE)
            ));
        when(ocrMapper.selectByKeyframeIds("task_1", 42L, List.of(9L, 10L)))
            .thenReturn(List.of(ocr(9L, "Course intro"), ocr(10L, "")));
        VisionAnalysisService service = newService(new VisionModelProvider() {
            @Override
            public String providerName() {
                return "fake-vision";
            }

            @Override
            public VisionAnalysisResult analyze(VisionAnalysisRequest request) {
                if (request.keyframeId().equals(9L)) {
                    return new VisionAnalysisResult(
                        VisionAnalysisStatus.SUCCEEDED,
                        "PPT",
                        "Course intro slide",
                        List.of("title"),
                        providerName(),
                        request.route().modelName(),
                        25L,
                        null,
                        null
                    );
                }
                return VisionAnalysisResult.empty(providerName(), request.route().modelName(), 10L);
            }
        });

        VisionAnalysisScanResult first = service.scan("task_1", 42L);
        VisionAnalysisScanResult retry = service.scan("task_1", 42L);

        assertThat(first.saved()).isEqualTo(2);
        assertThat(retry.saved()).isEqualTo(2);
        assertThat(deleteCalls).isEqualTo(2);
        assertThat(rows).extracting(VideoKeyframeAnalysis::getStatus)
            .containsExactly(VisionAnalysisStatus.SUCCEEDED.name(), VisionAnalysisStatus.EMPTY.name());
        assertThat(rows.getFirst().getVisualSummary()).isEqualTo("Course intro slide");
        assertThat(rows.getFirst().getDetectedElementsJson()).contains("title");
        assertThat(rows.toString())
            .doesNotContain("objectKey")
            .doesNotContain("keyframes/42")
            .doesNotContain("localPath")
            .doesNotContain("apiKey");
    }

    @Test
    void providerFailureIsPersistedWithoutStoppingRemainingFrames() {
        when(keyframeMapper.selectByTaskIdAndUserId("task_1", 42L))
            .thenReturn(List.of(
                keyframe(9L, 0L, KeyframeSelectionReason.SCENE_CHANGE),
                keyframe(10L, 30_000L, KeyframeSelectionReason.CONTENT_CHANGE)
            ));
        when(ocrMapper.selectByKeyframeIds("task_1", 42L, List.of(9L, 10L)))
            .thenReturn(List.of(ocr(9L, "A"), ocr(10L, "B")));
        VisionAnalysisService service = newService(new VisionModelProvider() {
            private int calls;

            @Override
            public String providerName() {
                return "fake-vision";
            }

            @Override
            public VisionAnalysisResult analyze(VisionAnalysisRequest request) {
                calls++;
                if (calls == 1) {
                    throw new IllegalStateException("objectKey=keyframes/42/task_1/frame.jpg token=abc");
                }
                return VisionAnalysisResult.empty(providerName(), request.route().modelName(), 10L);
            }
        });

        VisionAnalysisScanResult result = service.scan("task_1", 42L);

        assertThat(result.failed()).isEqualTo(1);
        assertThat(result.empty()).isEqualTo(1);
        assertThat(rows).extracting(VideoKeyframeAnalysis::getStatus)
            .containsExactly(VisionAnalysisStatus.FAILED.name(), VisionAnalysisStatus.EMPTY.name());
        assertThat(rows.getFirst().getErrorMessage())
            .doesNotContain("objectKey")
            .doesNotContain("keyframes/42")
            .doesNotContain("token")
            .doesNotContain("abc");
    }

    private VisionAnalysisService newService(VisionModelProvider provider) {
        return new VisionAnalysisServiceImpl(
            keyframeMapper,
            ocrMapper,
            analysisMapper,
            new MemoryStorageService(),
            provider,
            new AiModelRouter(routingProperties()),
            new HighValueKeyframeSelector(),
            properties,
            new ObjectMapper(),
            CLOCK
        );
    }

    private static AiModelRoutingProperties routingProperties() {
        AiModelRoutingProperties properties = new AiModelRoutingProperties();
        properties.setEnabled(true);
        properties.setRoutes(Map.of(
            AiModelStage.TRANSLATION_FULL_TEXT, "text",
            AiModelStage.SUBTITLE_TRANSLATION, "text",
            AiModelStage.LEARNING_PACKAGE, "text",
            AiModelStage.COURSE_QA, "text",
            AiModelStage.COURSE_CHAPTER, "text",
            AiModelStage.VISION_FRAME_ANALYSIS, "vision"
        ));
        properties.setProfiles(Map.of(
            "text", profile("openai-compatible", "model", EnumSet.of(ModelCapability.TEXT_CHAT, ModelCapability.JSON_OUTPUT)),
            "vision", profile("openai-compatible-vision", "qwen-vl", EnumSet.of(ModelCapability.VISION, ModelCapability.JSON_OUTPUT))
        ));
        return properties;
    }

    private static AiModelProfile profile(String providerType, String model, EnumSet<ModelCapability> capabilities) {
        AiModelProfile profile = new AiModelProfile();
        profile.setProviderType(providerType);
        profile.setBaseUrl("https://api.example.com/v1");
        profile.setModelName(model);
        profile.setApiKeyEnvName("TEST_KEY");
        profile.setCapabilities(capabilities);
        profile.setTemperature(0.0d);
        profile.setMaxTokens(1024);
        profile.setTimeout(Duration.ofSeconds(30));
        profile.setMaxAttempts(1);
        profile.setEnabled(true);
        return profile;
    }

    private static VideoKeyframe keyframe(Long id, Long timestampMillis, KeyframeSelectionReason reason) {
        VideoKeyframe keyframe = new VideoKeyframe();
        keyframe.setId(id);
        keyframe.setTaskId("task_1");
        keyframe.setUserId(42L);
        keyframe.setTimestampMillis(timestampMillis);
        keyframe.setSelectReason(reason.name());
        keyframe.setObjectKey("keyframes/42/task_1/frame-" + id + ".jpg");
        return keyframe;
    }

    private static VideoKeyframeOcr ocr(Long keyframeId, String text) {
        VideoKeyframeOcr row = new VideoKeyframeOcr();
        row.setTaskId("task_1");
        row.setUserId(42L);
        row.setKeyframeId(keyframeId);
        row.setStatus(text == null || text.isBlank() ? OcrStatus.EMPTY.name() : OcrStatus.SUCCEEDED.name());
        row.setOcrText(text);
        row.setCreatedAt(LocalDateTime.ofInstant(CLOCK.instant(), CLOCK.getZone()));
        return row;
    }

    private static final class MemoryStorageService implements StorageService {

        @Override
        public void putObject(String objectKey, Path sourceFile, long sizeBytes, String contentType) {
        }

        @Override
        public boolean objectExists(String objectKey) {
            return true;
        }

        @Override
        public InputStream openObject(String objectKey) {
            return new ByteArrayInputStream("image".getBytes(StandardCharsets.UTF_8));
        }

        @Override
        public void deleteObject(String objectKey) {
        }
    }
}
