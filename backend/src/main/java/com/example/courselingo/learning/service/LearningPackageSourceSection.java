package com.example.courselingo.learning.service;

/** Offsets cover the exact evidence string; source identity is independent of map chunk boundaries. */
record LearningPackageSourceSection(int start, int end, int segmentIndex,
    long startMillis, long endMillis, String contentHash) {}
