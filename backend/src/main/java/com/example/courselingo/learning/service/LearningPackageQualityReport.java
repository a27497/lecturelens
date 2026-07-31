package com.example.courselingo.learning.service;

import java.util.List;

record LearningPackageQualityReport(boolean valid, List<String> deficits) {
    LearningPackageQualityReport {
        deficits = deficits == null ? List.of() : List.copyOf(deficits);
    }

    static LearningPackageQualityReport parseFailure(String reason) {
        return new LearningPackageQualityReport(false, List.of(reason));
    }

    String promptText() {
        return String.join("; ", deficits);
    }
}
