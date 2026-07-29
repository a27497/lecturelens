package com.example.courselingo.vision.adaptive;

import com.example.courselingo.common.error.ErrorCode;
import com.example.courselingo.common.exception.BusinessException;
import com.example.courselingo.media.VideoFrameBatchResult;
import com.example.courselingo.media.VideoFrameBatchSampler;
import com.example.courselingo.media.VideoFrameSampleRequest;
import com.example.courselingo.vision.keyframe.VideoKeyframeProperties;
import com.example.courselingo.vision.ocr.OcrProvider;
import com.example.courselingo.vision.ocr.OcrResult;
import com.example.courselingo.vision.ocr.OcrStatus;
import com.example.courselingo.vision.ocr.VisionOcrProperties;
import java.awt.image.BufferedImage;
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.time.Duration;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.HashMap;
import java.util.LinkedHashMap;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Map;
import java.util.Optional;
import java.util.Set;
import javax.imageio.ImageIO;

/** Bounded media/OCR preparation stage; persistence remains on the caller thread. */
public final class AdaptiveFramePreparationPipeline {

    public record PreparedFrame(
        SceneCandidate candidate,
        long timestampMillis,
        Path imagePath,
        ImageQualityAnalysis quality,
        boolean relaxed,
        OcrResult ocr
    ) {

        public PreparedFrame withOcr(OcrResult result) {
            return new PreparedFrame(candidate, timestampMillis, imagePath, quality, relaxed, result);
        }
    }

    public record Statistics(
        int plannedCandidates,
        int sampleBatches,
        int ffmpegProcessCount,
        int sampleRequests,
        int sampleSucceeded,
        int sampleFailed,
        int stableFrames,
        int blurredRejected,
        int blackRejected,
        int imageDuplicateRejected,
        int preOcrRejected,
        int ocrPlanned,
        int ocrAttempted,
        int ocrSucceeded,
        int ocrEmpty,
        int ocrFailed
    ) {
    }

    public record Result(List<PreparedFrame> frames, Statistics statistics) {

        public Result {
            frames = frames == null ? List.of() : List.copyOf(frames);
        }
    }

    private final VideoKeyframeProperties properties;
    private final VideoFrameBatchSampler batchSampler;
    private final OcrProvider ocrProvider;
    private final VisionOcrProperties ocrProperties;
    private final BoundedOcrExecutor ocrExecutor;

    public AdaptiveFramePreparationPipeline(
        VideoKeyframeProperties properties,
        VideoFrameBatchSampler batchSampler,
        OcrProvider ocrProvider,
        VisionOcrProperties ocrProperties
    ) {
        this(properties, batchSampler, ocrProvider, ocrProperties, new BoundedOcrExecutor());
    }

    AdaptiveFramePreparationPipeline(
        VideoKeyframeProperties properties,
        VideoFrameBatchSampler batchSampler,
        OcrProvider ocrProvider,
        VisionOcrProperties ocrProperties,
        BoundedOcrExecutor ocrExecutor
    ) {
        this.properties = properties == null ? new VideoKeyframeProperties() : properties;
        this.batchSampler = batchSampler;
        this.ocrProvider = ocrProvider;
        this.ocrProperties = ocrProperties == null ? new VisionOcrProperties() : ocrProperties;
        this.ocrExecutor = ocrExecutor;
    }

    public Result prepare(
        Path sourceVideo,
        Path outputDirectory,
        long durationMillis,
        List<SceneCandidate> candidates
    ) {
        if (batchSampler == null) {
            throw new BusinessException(ErrorCode.MEDIA_CONFIGURATION_INVALID, "Batch frame sampler is unavailable");
        }
        long deadline = System.nanoTime() + Duration.ofSeconds(properties.getTimeoutSeconds()).toNanos();
        MutableStatistics stats = new MutableStatistics();
        List<SceneCandidate> safeCandidates = candidates == null ? List.of() : List.copyOf(candidates);
        stats.plannedCandidates = safeCandidates.size();
        List<PreparedFrame> stable = sampleStableFrames(
            sourceVideo,
            outputDirectory,
            Math.max(0L, durationMillis),
            safeCandidates,
            stats,
            deadline
        );
        List<PreparedFrame> imageDistinct = imageOnlyDeduplicate(stable, stats);
        if (!ocrProperties.isEnabled() || ocrProvider == null) {
            OcrResult disabled = disabledOcr();
            return new Result(
                imageDistinct.stream().map(frame -> frame.withOcr(disabled)).toList(),
                stats.snapshot()
            );
        }

        PreOcrFrameBudgetAllocator allocator = preOcrAllocator();
        List<PreOcrFrameBudgetAllocator.FrameSignal<PreparedFrame>> signals = imageDistinct.stream()
            .map(frame -> new PreOcrFrameBudgetAllocator.FrameSignal<>(
                frame,
                frame.timestampMillis(),
                frame.candidate().source(),
                frame.candidate().score(),
                frame.quality().edgeDensity(),
                frame.quality().totalScore(),
                visualOnlyEligible(frame)
            ))
            .toList();
        PreOcrFrameBudgetAllocator.Allocation<PreparedFrame> allocation = allocator.allocate(signals);
        int ocrLimit = Math.min(properties.getPreOcrMaxFramesTotal(), ocrProperties.getMaxKeyframesPerTask());
        List<PreparedFrame> ocrFrames = allocation.ocrFrames().stream().limit(ocrLimit).toList();
        List<PreparedFrame> overflow = allocation.ocrFrames().stream().skip(ocrLimit).toList();
        List<PreparedFrame> rejected = new ArrayList<>(allocation.rejectedFrames());
        rejected.addAll(overflow);
        rejected.forEach(frame -> deleteFileBestEffort(frame.imagePath()));
        stats.preOcrRejected += rejected.size();
        stats.ocrPlanned = ocrFrames.size();

        Map<PreparedFrame, Path> ocrSources = prepareOcrSources(
            sourceVideo,
            outputDirectory,
            ocrFrames,
            stats,
            deadline
        );
        List<BoundedOcrExecutor.Job<PreparedFrame>> jobs = new ArrayList<>();
        for (int index = 0; index < ocrFrames.size(); index++) {
            PreparedFrame frame = ocrFrames.get(index);
            jobs.add(new BoundedOcrExecutor.Job<>(
                frame,
                frame.timestampMillis(),
                ocrSources.getOrDefault(frame, frame.imagePath()),
                outputDirectory.resolve("ocr-%04d".formatted(index))
            ));
        }
        BoundedOcrExecutor.Execution<PreparedFrame> execution = ocrExecutor.execute(
            jobs,
            ocrProvider,
            ocrProperties,
            remaining(deadline)
        );
        stats.ocrAttempted = execution.attemptedCount();
        List<PreparedFrame> result = new ArrayList<>();
        for (BoundedOcrExecutor.Outcome<PreparedFrame> outcome : execution.outcomes()) {
            OcrResult ocr = outcome.ocrResult();
            countOcr(ocr, stats);
            result.add(outcome.payload().withOcr(ocr));
        }
        OcrResult disabled = disabledOcr();
        allocation.visualOnlyFrames().stream().map(frame -> frame.withOcr(disabled)).forEach(result::add);
        ocrSources.forEach((frame, path) -> {
            if (!path.equals(frame.imagePath())) {
                deleteFileBestEffort(path);
            }
        });
        result.sort(Comparator.comparingLong(PreparedFrame::timestampMillis));
        return new Result(result, stats.snapshot());
    }

    private List<PreparedFrame> sampleStableFrames(
        Path sourceVideo,
        Path outputDirectory,
        long durationMillis,
        List<SceneCandidate> candidates,
        MutableStatistics stats,
        long deadline
    ) {
        ImageQualityAnalyzer analyzer = qualityAnalyzer();
        StableFrameSelector selector = stableFrameSelector(analyzer);
        List<PreparedFrame> result = new ArrayList<>();
        int nextCandidate = 0;
        while (nextCandidate < candidates.size()) {
            ensureNotInterrupted();
            List<PlannedSample> batchPlan = new ArrayList<>();
            List<Integer> batchCandidates = new ArrayList<>();
            while (nextCandidate < candidates.size()) {
                SceneCandidate candidate = candidates.get(nextCandidate);
                List<Double> timestamps = selector.sampleTimestamps(
                    candidate.timestampSeconds(), durationMillis / 1_000.0d
                );
                if (!batchPlan.isEmpty()
                    && batchPlan.size() + timestamps.size() > properties.getFrameSamplingBatchSize()) {
                    break;
                }
                batchCandidates.add(nextCandidate);
                for (int sampleIndex = 0; sampleIndex < timestamps.size(); sampleIndex++) {
                    batchPlan.add(new PlannedSample(
                        nextCandidate,
                        candidate,
                        timestamps.get(sampleIndex),
                        outputDirectory.resolve(
                            "candidate-%04d-%03d.png".formatted(nextCandidate, sampleIndex)
                        )
                    ));
                }
                nextCandidate++;
            }
            Set<Path> succeeded = samplePlan(
                sourceVideo,
                batchPlan.stream().map(PlannedSample::request).toList(),
                properties.getAnalysisMaxWidth(),
                stats,
                deadline
            );
            Map<Integer, List<SampleFile>> byCandidate = readBatchSamples(batchPlan, succeeded);
            for (int candidateIndex : batchCandidates) {
                SceneCandidate candidate = candidates.get(candidateIndex);
                List<SampleFile> sampleFiles = byCandidate.getOrDefault(candidateIndex, List.of()).stream()
                    .sorted(Comparator.comparingDouble(SampleFile::timestampSeconds)).toList();
                List<StableFrameSelector.FrameSample> samples = sampleFiles.stream()
                    .map(sample -> new StableFrameSelector.FrameSample(sample.timestampSeconds(), sample.image()))
                    .toList();
                Optional<StableFrameSelector.SelectedStableFrame> selected = selector.select(candidate, samples);
                if (selected.isEmpty()) {
                    if (!samples.isEmpty()
                        && samples.stream().allMatch(sample -> analyzer.analyze(sample.image()).black())) {
                        stats.blackRejected++;
                    } else {
                        stats.blurredRejected++;
                    }
                    deleteSampleFiles(sampleFiles, null);
                    continue;
                }
                StableFrameSelector.SelectedStableFrame stable = selected.get();
                Path retained = sampleFiles.stream()
                    .filter(sample -> Math.abs(sample.timestampSeconds() - stable.timestampSeconds()) < 0.0005d)
                    .map(SampleFile::path)
                    .findFirst()
                    .orElseThrow();
                result.add(new PreparedFrame(
                    candidate,
                    Math.round(stable.timestampSeconds() * 1_000.0d),
                    retained,
                    stable.quality(),
                    stable.relaxed(),
                    disabledOcr()
                ));
                stats.stableFrames++;
                deleteSampleFiles(sampleFiles, retained);
            }
        }
        return List.copyOf(result);
    }

    private Map<Integer, List<SampleFile>> readBatchSamples(List<PlannedSample> plan, Set<Path> succeeded) {
        Map<Integer, List<SampleFile>> byCandidate = new LinkedHashMap<>();
        for (PlannedSample planned : plan) {
            if (!succeeded.contains(planned.path().toAbsolutePath().normalize())) {
                continue;
            }
            try {
                BufferedImage image = ImageIO.read(planned.path().toFile());
                if (image != null) {
                    byCandidate.computeIfAbsent(planned.candidateIndex(), ignored -> new ArrayList<>())
                        .add(new SampleFile(planned.timestampSeconds(), planned.path(), image));
                }
            } catch (IOException ignored) {
                deleteFileBestEffort(planned.path());
            }
        }
        return byCandidate;
    }

    private Set<Path> samplePlan(
        Path sourceVideo,
        List<VideoFrameSampleRequest> requests,
        int width,
        MutableStatistics stats,
        long deadline
    ) {
        Set<Path> succeeded = new LinkedHashSet<>();
        int batchSize = properties.getFrameSamplingBatchSize();
        for (int start = 0; start < requests.size(); start += batchSize) {
            ensureNotInterrupted();
            int end = Math.min(requests.size(), start + batchSize);
            List<VideoFrameSampleRequest> batch = requests.subList(start, end);
            stats.sampleBatches++;
            stats.sampleRequests += batch.size();
            try {
                VideoFrameBatchResult result = batchSampler.sample(
                    sourceVideo,
                    batch,
                    width,
                    min(Duration.ofSeconds(45), remaining(deadline))
                );
                stats.ffmpegProcessCount += result.ffmpegProcessCount();
                stats.sampleSucceeded += result.succeededCount();
                stats.sampleFailed += result.failedCount();
                result.samples().forEach(sample -> succeeded.add(sample.imagePath().toAbsolutePath().normalize()));
            } catch (RuntimeException failure) {
                stats.sampleFailed += batch.size();
                if (Thread.currentThread().isInterrupted()
                    || failure instanceof BusinessException business
                    && business.errorCode() == ErrorCode.MEDIA_FFMPEG_TIMEOUT) {
                    throw failure;
                }
            }
        }
        return Set.copyOf(succeeded);
    }

    private List<PreparedFrame> imageOnlyDeduplicate(List<PreparedFrame> frames, MutableStatistics stats) {
        List<PreparedFrame> kept = new ArrayList<>();
        long windowMillis = properties.getWindowSeconds() * 1_000L;
        for (PreparedFrame candidate : frames.stream().sorted(Comparator.comparingLong(PreparedFrame::timestampMillis)).toList()) {
            boolean duplicate = kept.stream().anyMatch(previous -> {
                if (Math.abs(previous.timestampMillis() - candidate.timestampMillis()) > 120_000L) {
                    return false;
                }
                boolean exactFingerprint = !previous.quality().contentFingerprint().isBlank()
                    && previous.quality().contentFingerprint().equals(candidate.quality().contentFingerprint());
                int hashDistance = PerceptualHashDeduplicator.hammingDistance(
                    previous.quality().perceptualHash(),
                    candidate.quality().perceptualHash()
                );
                boolean detectedChange = candidate.candidate().source() == SceneCandidate.Source.CONTENT_CHANGE
                    || candidate.candidate().source() == SceneCandidate.Source.SCENE_CHANGE;
                if (filesIdentical(previous.imagePath(), candidate.imagePath())) {
                    return true;
                }
                if (detectedChange
                    && Math.abs(previous.timestampMillis() - candidate.timestampMillis())
                        >= properties.getMinKeyframeGapSeconds() * 1_000L) {
                    return false;
                }
                if (exactFingerprint || hashDistance == 0) {
                    return true;
                }
                if (previous.timestampMillis() / windowMillis != candidate.timestampMillis() / windowMillis
                    || hashDistance > properties.getPerceptualHashDistance()) {
                    return false;
                }
                return !detectedChange;
            });
            if (duplicate) {
                stats.imageDuplicateRejected++;
                deleteFileBestEffort(candidate.imagePath());
            } else {
                kept.add(candidate);
            }
        }
        return List.copyOf(kept);
    }

    private Map<PreparedFrame, Path> prepareOcrSources(
        Path sourceVideo,
        Path outputDirectory,
        List<PreparedFrame> frames,
        MutableStatistics stats,
        long deadline
    ) {
        Map<PreparedFrame, Path> sources = new HashMap<>();
        frames.forEach(frame -> sources.put(frame, frame.imagePath()));
        if (ocrProperties.getPreprocessMaxWidth() <= properties.getAnalysisMaxWidth() || frames.isEmpty()) {
            return sources;
        }
        List<VideoFrameSampleRequest> requests = new ArrayList<>();
        Map<Path, PreparedFrame> frameByOutput = new HashMap<>();
        for (int index = 0; index < frames.size(); index++) {
            PreparedFrame frame = frames.get(index);
            Path output = outputDirectory.resolve("ocr-source-%04d.png".formatted(index));
            requests.add(new VideoFrameSampleRequest(frame.timestampMillis(), output));
            frameByOutput.put(output.toAbsolutePath().normalize(), frame);
        }
        Set<Path> succeeded = samplePlan(
            sourceVideo,
            requests,
            ocrProperties.getPreprocessMaxWidth(),
            stats,
            deadline
        );
        succeeded.forEach(path -> {
            PreparedFrame frame = frameByOutput.get(path);
            if (frame != null) {
                sources.put(frame, path);
            }
        });
        return sources;
    }

    private PreOcrFrameBudgetAllocator preOcrAllocator() {
        return new PreOcrFrameBudgetAllocator(new PreOcrFrameBudgetAllocator.Config(
            properties.getWindowSeconds(),
            properties.getPreOcrMaxFramesPerWindow(),
            properties.getPreOcrContentChangeMaxFramesPerWindow(),
            properties.getPreOcrLowInformationMaxFramesPerWindow(),
            properties.getPreOcrMaxFramesTotal()
        ));
    }

    private boolean visualOnlyEligible(PreparedFrame frame) {
        double threshold = Math.max(0.07d, properties.getContentVisualEdgeDensityThreshold() * 2.0d);
        return frame.candidate().source() == SceneCandidate.Source.SCENE_CHANGE
            && frame.candidate().score() >= properties.getContentVisualSceneScoreThreshold()
            && frame.quality().edgeDensity() >= threshold
            && frame.quality().brightnessVariance() >= 120.0d;
    }

    private ImageQualityAnalyzer qualityAnalyzer() {
        return new ImageQualityAnalyzer(new ImageQualityAnalyzer.Config(
            256,
            properties.getBlackBrightnessThreshold(),
            80.0d,
            properties.getBlankVarianceThreshold(),
            0.006d,
            28.0d,
            Math.max(100.0d, properties.getSharpnessThreshold() * 15.0d)
        ));
    }

    private StableFrameSelector stableFrameSelector(ImageQualityAnalyzer analyzer) {
        return new StableFrameSelector(new StableFrameSelector.Config(
            properties.getNearbySampleOffsetsSeconds(),
            properties.getSharpnessThreshold(),
            0.002d,
            28.0d,
            0.35d
        ), analyzer);
    }

    private OcrResult disabledOcr() {
        return new OcrResult(
            OcrStatus.DISABLED,
            "",
            null,
            ocrProperties.getProvider(),
            ocrProperties.getLanguage(),
            0L,
            null,
            null
        );
    }

    private static void countOcr(OcrResult result, MutableStatistics stats) {
        OcrStatus status = result == null || result.status() == null ? OcrStatus.FAILED : result.status();
        switch (status) {
            case SUCCEEDED -> stats.ocrSucceeded++;
            case EMPTY -> stats.ocrEmpty++;
            case FAILED -> stats.ocrFailed++;
            default -> {
            }
        }
    }

    private static Duration remaining(long deadline) {
        long nanos = deadline - System.nanoTime();
        if (nanos <= 0L) {
            throw new BusinessException(ErrorCode.TASK_EXECUTOR_TIMEOUT, "Adaptive video branch timed out");
        }
        return Duration.ofNanos(nanos);
    }

    private static Duration min(Duration first, Duration second) {
        return first.compareTo(second) <= 0 ? first : second;
    }

    private static void ensureNotInterrupted() {
        if (Thread.currentThread().isInterrupted()) {
            throw new BusinessException(ErrorCode.MEDIA_FFMPEG_FAILED, "Adaptive video branch was interrupted");
        }
    }

    private static void deleteSampleFiles(List<SampleFile> samples, Path retained) {
        for (SampleFile sample : samples) {
            if (retained != null && retained.equals(sample.path())) {
                continue;
            }
            deleteFileBestEffort(sample.path());
        }
    }

    private static void deleteFileBestEffort(Path path) {
        if (path == null) {
            return;
        }
        try {
            Files.deleteIfExists(path);
        } catch (IOException ignored) {
            // The task-workspace cleanup provides the final retry.
        }
    }

    private static boolean filesIdentical(Path first, Path second) {
        try {
            return first != null && second != null
                && Files.size(first) == Files.size(second)
                && Files.mismatch(first, second) == -1L;
        } catch (IOException ignored) {
            return false;
        }
    }

    private record PlannedSample(
        int candidateIndex,
        SceneCandidate candidate,
        double timestampSeconds,
        Path path
    ) {

        private VideoFrameSampleRequest request() {
            return new VideoFrameSampleRequest(Math.round(timestampSeconds * 1_000.0d), path);
        }
    }

    private record SampleFile(double timestampSeconds, Path path, BufferedImage image) {
    }

    private static final class MutableStatistics {
        private int plannedCandidates;
        private int sampleBatches;
        private int ffmpegProcessCount;
        private int sampleRequests;
        private int sampleSucceeded;
        private int sampleFailed;
        private int stableFrames;
        private int blurredRejected;
        private int blackRejected;
        private int imageDuplicateRejected;
        private int preOcrRejected;
        private int ocrPlanned;
        private int ocrAttempted;
        private int ocrSucceeded;
        private int ocrEmpty;
        private int ocrFailed;

        private Statistics snapshot() {
            return new Statistics(
                plannedCandidates,
                sampleBatches,
                ffmpegProcessCount,
                sampleRequests,
                sampleSucceeded,
                sampleFailed,
                stableFrames,
                blurredRejected,
                blackRejected,
                imageDuplicateRejected,
                preOcrRejected,
                ocrPlanned,
                ocrAttempted,
                ocrSucceeded,
                ocrEmpty,
                ocrFailed
            );
        }
    }
}
