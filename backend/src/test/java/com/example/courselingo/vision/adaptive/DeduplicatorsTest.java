package com.example.courselingo.vision.adaptive;

import static org.assertj.core.api.Assertions.assertThat;

import java.util.List;
import org.junit.jupiter.api.Test;

class DeduplicatorsTest {

    @Test
    void hammingDistanceAndImageDedupUseBothHashAndTime() {
        PerceptualHashDeduplicator deduplicator = new PerceptualHashDeduplicator(2, 30.0);
        long first = 0b1010L;
        long oneBitDifferent = 0b1011L;

        assertThat(PerceptualHashDeduplicator.hammingDistance(first, oneBitDifferent)).isEqualTo(1);
        assertThat(deduplicator.isDuplicate(first, 10, oneBitDifferent, 20)).isTrue();
        assertThat(deduplicator.isDuplicate(first, 10, oneBitDifferent, 50)).isFalse();

        List<PerceptualHashDeduplicator.HashedFrame<String>> result = deduplicator.deduplicate(List.of(
            new PerceptualHashDeduplicator.HashedFrame<>("first", 10, first),
            new PerceptualHashDeduplicator.HashedFrame<>("duplicate", 20, oneBitDifferent),
            new PerceptualHashDeduplicator.HashedFrame<>("later", 50, oneBitDifferent)
        ));
        assertThat(result).extracting(PerceptualHashDeduplicator.HashedFrame::value)
            .containsExactly("first", "later");
    }

    @Test
    void ocrRequiresImageTextAndTimeSimilarityTogether() {
        OcrTextDeduplicator deduplicator = new OcrTextDeduplicator();
        String text = "Three steps: parse, validate, persist";
        var previous = new OcrTextDeduplicator.OcrFrame(60, 0xF0L, text);

        assertThat(deduplicator.isDuplicate(previous,
            new OcrTextDeduplicator.OcrFrame(70, 0xF1L, " three  STEPS: parse, validate, persist "))).isTrue();
        assertThat(deduplicator.isDuplicate(previous,
            new OcrTextDeduplicator.OcrFrame(400, 0xF1L, text))).isFalse();
        assertThat(deduplicator.isDuplicate(previous,
            new OcrTextDeduplicator.OcrFrame(70, ~0xF0L, text))).isFalse();
        assertThat(deduplicator.isDuplicate(previous,
            new OcrTextDeduplicator.OcrFrame(70, 0xF1L, "A completely unrelated slide"))).isFalse();
    }

    @Test
    void retainsIncrementallyRevealedCodeEvenWhenImageAndMostTextAreSimilar() {
        OcrTextDeduplicator deduplicator = new OcrTextDeduplicator(new OcrTextDeduplicator.Config(
            6, 0.75, 120, 4));
        var first = new OcrTextDeduplicator.OcrFrame(10, 0L, "int total = 0;\nfor (Item item : items) {");
        var revealed = new OcrTextDeduplicator.OcrFrame(12, 1L,
            "int total = 0;\nfor (Item item : items) {\n    total += item.value();");

        assertThat(deduplicator.isDuplicate(first, revealed)).isFalse();
        assertThat(deduplicator.hasMeaningfulAddition(first.text(), revealed.text())).isTrue();
        assertThat(deduplicator.deduplicate(List.of(first, revealed))).containsExactly(first, revealed);
    }

    @Test
    void textNormalizationAndSimilarityAreDeterministic() {
        assertThat(OcrTextDeduplicator.normalize("ＡＢＣ\n  Value  ")).isEqualTo("abc value");
        assertThat(OcrTextDeduplicator.textSimilarity("alpha  beta", "alpha\nbeta")).isEqualTo(1.0);
    }

    @Test
    void identicalVisualDemoFramesStillProduceOnlyOneRepresentative() {
        PerceptualHashDeduplicator deduplicator = new PerceptualHashDeduplicator(0, 120.0d);

        List<PerceptualHashDeduplicator.HashedFrame<String>> result = deduplicator.deduplicate(List.of(
            new PerceptualHashDeduplicator.HashedFrame<>("diagram-representative", 10.0d, 0xCAFE_BABEL),
            new PerceptualHashDeduplicator.HashedFrame<>("diagram-duplicate", 20.0d, 0xCAFE_BABEL)
        ));

        assertThat(result).extracting(PerceptualHashDeduplicator.HashedFrame::value)
            .containsExactly("diagram-representative");
    }

    @Test
    void exactDuplicateAcrossMinuteBoundaryIsStillRecognizedWithinRetryWindow() {
        PerceptualHashDeduplicator deduplicator = new PerceptualHashDeduplicator(0, 120.0d);

        assertThat(deduplicator.isDuplicate(0x1234L, 46.0d, 0x1234L, 90.0d)).isTrue();
    }
}
