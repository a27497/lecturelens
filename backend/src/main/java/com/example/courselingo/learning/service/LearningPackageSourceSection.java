package com.example.courselingo.learning.service;

import java.util.List;

/** Offsets cover the exact evidence string; source identity is independent of map chunk boundaries. */
public record LearningPackageSourceSection(
    int start,
    int end,
    int segmentIndex,
    long startMillis,
    long endMillis,
    String contentHash,
    List<Integer> memberIndexes
) {
    public LearningPackageSourceSection {
        memberIndexes = memberIndexes == null || memberIndexes.isEmpty()
            ? List.of(segmentIndex)
            : List.copyOf(memberIndexes);
    }

    public LearningPackageSourceSection(
        int start,
        int end,
        int segmentIndex,
        long startMillis,
        long endMillis,
        String contentHash
    ) {
        this(start, end, segmentIndex, startMillis, endMillis, contentHash, List.of(segmentIndex));
    }
}
