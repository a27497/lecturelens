package com.example.courselingo.artifact.service;

public record VttCue(
    int segmentIndex,
    long startMillis,
    long endMillis,
    String text
) {
}
