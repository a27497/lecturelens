package com.example.courselingo.systemmodel;

import static org.assertj.core.api.Assertions.*;
import static org.mockito.Mockito.*;

import com.example.courselingo.ai.llm.*;
import com.example.courselingo.modelrouting.*;
import com.example.courselingo.vision.analysis.*;
import java.awt.image.BufferedImage;
import java.nio.file.Path;
import java.time.Duration;
import java.util.Map;
import java.util.Set;
import java.util.concurrent.atomic.AtomicInteger;
import javax.imageio.ImageIO;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

class SystemModelVisionBoundsTest {
    @TempDir Path directory;

    @Test
    void failuresDoNotResetTheFrozenAttemptLimit() throws Exception {
        verifyFrozenBounds(false);
    }

    @Test
    void retriesDoNotResetTheFrozenTotalDeadline() throws Exception {
        verifyFrozenBounds(true);
    }

    private void verifyFrozenBounds(boolean exhaustDeadline) throws Exception {
        var ref = new SystemModelExecutionRef("snapshot", 1, "task", 1);
        var resolved = new SystemModelResolvedRoute(
                "VISION_FRAME_ANALYSIS", "DATABASE", SystemModelProtocol.OPENAI_CHAT,
                "1", 1L, 1L, "https://vision.invalid", "synthetic", Set.of("VISION"),
                0d, 32, 1000L, 3, true, "test");
        var executions = mock(SystemModelExecutionService.class);
        when(executions.route(ref, "VISION_FRAME_ANALYSIS")).thenReturn(resolved);
        when(executions.credential(ref, "VISION_FRAME_ANALYSIS")).thenReturn("synthetic-key");
        var calls = new AtomicInteger();
        OpenAiCompatibleLlmClient wire = request -> {
            int attempt = calls.incrementAndGet();
            if (exhaustDeadline) {
                java.util.concurrent.locks.LockSupport.parkNanos(Duration.ofMillis(1200).toNanos());
            } else if (attempt == 2) {
                throw new SystemModelCallFailure("NETWORK", LlmProviderFailureCategory.NETWORK, null, true);
            }
            return new OpenAiCompatibleClientResponse(500, "{}", Map.of(), Duration.ZERO);
        };
        var provider = new SystemModelVisionProvider(
                executions, wire, new VisionAnalysisProperties(), new SystemModelUrlPolicy());
        Path image = directory.resolve("synthetic.png");
        ImageIO.write(new BufferedImage(2, 2, BufferedImage.TYPE_INT_RGB), "png", image.toFile());
        var route = new AiModelRoute(
                AiModelStage.VISION_FRAME_ANALYSIS, "test", "test", "openai-compatible",
                resolved.baseUrl(), resolved.model(), "test", Set.of(ModelCapability.VISION),
                0d, 32, Duration.ofSeconds(1), 3, ref);
        var result = provider.analyze(new VisionAnalysisRequest("task", 1L, 0L, image, "", "", route));
        assertThat(result.status()).isEqualTo(VisionAnalysisStatus.FAILED);
        assertThat(calls.get()).isEqualTo(exhaustDeadline ? 1 : 3);
    }
}
