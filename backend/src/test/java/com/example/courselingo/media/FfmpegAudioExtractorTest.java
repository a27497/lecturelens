package com.example.courselingo.media;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import com.example.courselingo.common.error.ErrorCode;
import com.example.courselingo.common.exception.BusinessException;
import java.io.ByteArrayInputStream;
import java.io.IOException;
import java.io.InputStream;
import java.io.OutputStream;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.time.Duration;
import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.TimeUnit;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

class FfmpegAudioExtractorTest {

    @TempDir
    Path tempDir;

    @Test
    void rejectsMissingInputVideo() {
        FfmpegAudioExtractor extractor = newExtractor(new CapturingExecutor(FfmpegProcessResult.success("", "")));
        Path missingVideo = tempDir.resolve("missing.mp4");

        assertThatThrownBy(() -> extractor.extract(new AudioExtractionRequest(
            missingVideo,
            tempDir.resolve("audio"),
            "lecture.wav"
        )))
            .isInstanceOf(BusinessException.class)
            .extracting("errorCode")
            .isEqualTo(ErrorCode.MEDIA_INPUT_INVALID);
    }

    @Test
    void rejectsInputThatIsNotRegularFile() throws IOException {
        FfmpegAudioExtractor extractor = newExtractor(new CapturingExecutor(FfmpegProcessResult.success("", "")));
        Path inputDirectory = Files.createDirectory(tempDir.resolve("video-dir"));

        assertThatThrownBy(() -> extractor.extract(new AudioExtractionRequest(
            inputDirectory,
            tempDir.resolve("audio"),
            "lecture.wav"
        )))
            .isInstanceOf(BusinessException.class)
            .extracting("errorCode")
            .isEqualTo(ErrorCode.MEDIA_INPUT_INVALID);
    }

    @Test
    void createsMissingOutputDirectoryAndReturnsConfiguredAudioResult() throws IOException {
        Path inputVideo = Files.writeString(tempDir.resolve("lecture.mp4"), "video");
        Path outputDirectory = tempDir.resolve("audio").resolve("nested");
        CapturingExecutor executor = new CapturingExecutor(FfmpegProcessResult.success("ok", ""));
        FfmpegAudioExtractor extractor = newExtractor(executor);

        AudioExtractionResult result = extractor.extract(new AudioExtractionRequest(
            inputVideo,
            outputDirectory,
            "lecture.wav"
        ));

        assertThat(outputDirectory).isDirectory();
        assertThat(result.audioFile()).isEqualTo(outputDirectory.resolve("lecture.wav").toAbsolutePath().normalize());
        assertThat(result.audioFormat()).isEqualTo("wav");
        assertThat(result.sampleRate()).isEqualTo(16000);
        assertThat(result.channels()).isEqualTo(1);
        assertThat(executor.commands()).hasSize(1);
    }

    @Test
    void rejectsOutputFileNamePathTraversal() throws IOException {
        Path inputVideo = Files.writeString(tempDir.resolve("lecture.mp4"), "video");
        FfmpegAudioExtractor extractor = newExtractor(new CapturingExecutor(FfmpegProcessResult.success("", "")));

        assertThatThrownBy(() -> extractor.extract(new AudioExtractionRequest(
            inputVideo,
            tempDir.resolve("audio"),
            "..\\escape.wav"
        )))
            .isInstanceOf(BusinessException.class)
            .extracting("errorCode")
            .isEqualTo(ErrorCode.MEDIA_OUTPUT_INVALID);
    }

    @Test
    void commandUsesArgumentListAndContainsInputOutputSampleRateAndChannels() throws IOException {
        Path inputVideo = Files.writeString(tempDir.resolve("lecture.mp4"), "video");
        Path outputDirectory = tempDir.resolve("audio");
        CapturingExecutor executor = new CapturingExecutor(FfmpegProcessResult.success("", ""));
        FfmpegAudioExtractor extractor = newExtractor(executor);

        extractor.extract(new AudioExtractionRequest(inputVideo, outputDirectory, "lecture.wav"));

        List<String> command = executor.commands().getFirst();
        Path outputFile = outputDirectory.resolve("lecture.wav").toAbsolutePath().normalize();
        assertThat(command)
            .contains("ffmpeg", "-i", inputVideo.toAbsolutePath().normalize().toString(), outputFile.toString())
            .containsSubsequence("-ar", "16000")
            .containsSubsequence("-ac", "1")
            .containsSubsequence("-f", "wav");
        assertThat(command).doesNotContain("cmd", "cmd.exe", "powershell", "sh", "-c", "/c");
        assertThat(command).allSatisfy(argument -> assertThat(argument).doesNotContain(" -i "));
    }

    @Test
    void succeedsWhenFfmpegExitCodeIsZero() throws IOException {
        Path inputVideo = Files.writeString(tempDir.resolve("lecture.mp4"), "video");
        FfmpegAudioExtractor extractor = newExtractor(new CapturingExecutor(FfmpegProcessResult.success("", "")));

        AudioExtractionResult result = extractor.extract(new AudioExtractionRequest(
            inputVideo,
            tempDir.resolve("audio"),
            "lecture.wav"
        ));

        assertThat(result.audioFile().getFileName().toString()).isEqualTo("lecture.wav");
    }

    @Test
    void failsWhenFfmpegExitCodeIsNonZero() throws IOException {
        Path inputVideo = Files.writeString(tempDir.resolve("lecture.mp4"), "video");
        FfmpegAudioExtractor extractor = newExtractor(new CapturingExecutor(
            new FfmpegProcessResult(2, "", "codec failed", false)
        ));

        assertThatThrownBy(() -> extractor.extract(new AudioExtractionRequest(
            inputVideo,
            tempDir.resolve("audio"),
            "lecture.wav"
        )))
            .isInstanceOf(BusinessException.class)
            .extracting("errorCode")
            .isEqualTo(ErrorCode.MEDIA_FFMPEG_FAILED);
    }

    @Test
    void destroysProcessWhenTimedOut() throws Exception {
        FakeProcess process = new FakeProcess(false, "", "still running");
        ProcessBuilderFfmpegProcessExecutor executor = new ProcessBuilderFfmpegProcessExecutor(command -> process);

        FfmpegProcessResult result = executor.execute(List.of("ffmpeg", "-version"), Duration.ofMillis(1));

        assertThat(result.timedOut()).isTrue();
        assertThat(process.destroyedForcibly()).isTrue();
    }

    @Test
    void capturesStdoutAndStderrFromProcess() throws Exception {
        FakeProcess process = new FakeProcess(true, "stdout text", "stderr text");
        ProcessBuilderFfmpegProcessExecutor executor = new ProcessBuilderFfmpegProcessExecutor(command -> process);

        FfmpegProcessResult result = executor.execute(List.of("ffmpeg", "-version"), Duration.ofSeconds(1));

        assertThat(result.exitCode()).isZero();
        assertThat(result.stdout()).contains("stdout text");
        assertThat(result.stderr()).contains("stderr text");
    }

    @Test
    void truncatesLongStderrAndRedactsSensitiveDetails() throws IOException {
        Path inputVideo = Files.writeString(tempDir.resolve("lecture.mp4"), "video");
        String stderr = "C:\\Users\\demo\\private\\lecture.mp4 token=abc secret=def apiKey=ghi API_KEY=jkl "
            + "x".repeat(2_000);
        FfmpegAudioExtractor extractor = newExtractor(new CapturingExecutor(
            new FfmpegProcessResult(1, "", stderr, false)
        ));

        assertThatThrownBy(() -> extractor.extract(new AudioExtractionRequest(
            inputVideo,
            tempDir.resolve("audio"),
            "lecture.wav"
        )))
            .isInstanceOf(BusinessException.class)
            .satisfies(error -> {
                String message = error.getMessage();
                assertThat(message).hasSizeLessThanOrEqualTo(700);
                assertThat(message).doesNotContain("abc", "def", "ghi", "jkl", "C:\\Users", "demo");
                assertThat(message.toLowerCase()).doesNotContain("token", "secret", "apikey", "api_key", "api key");
            });
    }

    @Test
    void mediaComponentDoesNotReferenceForbiddenPipelineIntegrations() throws IOException {
        Path mediaSource = Path.of("src/main/java/com/example/courselingo/media");

        String source = readJavaSources(mediaSource);

        assertThat(source)
            .doesNotContain("SpeechToText")
            .doesNotContain("LLM")
            .doesNotContain("LangChain4j")
            .doesNotContain("AnalysisTaskRunner")
            .doesNotContain("Subtitle")
            .doesNotContain("Artifact");
    }

    private FfmpegAudioExtractor newExtractor(FfmpegProcessExecutor executor) {
        return new FfmpegAudioExtractorImpl(
            new FfmpegProperties("ffmpeg", "wav", 16000, 1, 300),
            executor
        );
    }

    private static String readJavaSources(Path directory) throws IOException {
        if (!Files.exists(directory)) {
            return "";
        }
        StringBuilder source = new StringBuilder();
        try (var paths = Files.walk(directory)) {
            for (Path path : paths.filter(path -> path.toString().endsWith(".java")).toList()) {
                if (path.getFileName().toString().startsWith("EmbeddedSubtitle")) {
                    continue;
                }
                source.append(Files.readString(path)).append('\n');
            }
        }
        return source.toString();
    }

    private static final class CapturingExecutor implements FfmpegProcessExecutor {

        private final FfmpegProcessResult result;
        private final List<List<String>> commands = new ArrayList<>();

        private CapturingExecutor(FfmpegProcessResult result) {
            this.result = result;
        }

        @Override
        public FfmpegProcessResult execute(List<String> command, Duration timeout) {
            commands.add(List.copyOf(command));
            return result;
        }

        List<List<String>> commands() {
            return commands;
        }
    }

    private static final class FakeProcess extends Process {

        private final boolean finishes;
        private final InputStream stdout;
        private final InputStream stderr;
        private boolean destroyedForcibly;

        private FakeProcess(boolean finishes, String stdout, String stderr) {
            this.finishes = finishes;
            this.stdout = new ByteArrayInputStream(stdout.getBytes(StandardCharsets.UTF_8));
            this.stderr = new ByteArrayInputStream(stderr.getBytes(StandardCharsets.UTF_8));
        }

        @Override
        public OutputStream getOutputStream() {
            return OutputStream.nullOutputStream();
        }

        @Override
        public InputStream getInputStream() {
            return stdout;
        }

        @Override
        public InputStream getErrorStream() {
            return stderr;
        }

        @Override
        public int waitFor() {
            return 0;
        }

        @Override
        public boolean waitFor(long timeout, TimeUnit unit) {
            return finishes;
        }

        @Override
        public int exitValue() {
            return 0;
        }

        @Override
        public void destroy() {
            destroyedForcibly = true;
        }

        @Override
        public Process destroyForcibly() {
            destroyedForcibly = true;
            return this;
        }

        boolean destroyedForcibly() {
            return destroyedForcibly;
        }
    }
}
