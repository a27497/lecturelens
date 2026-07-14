package com.example.courselingo.artifact.service;

public record SrtCue(
    int segmentIndex,
    long startMillis,
    long endMillis,
    String text
) {
}
