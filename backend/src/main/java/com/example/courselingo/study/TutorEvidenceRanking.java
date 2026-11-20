package com.example.courselingo.study;

import com.example.courselingo.evidence.CourseEvidence;
import java.util.*;
import java.util.regex.Pattern;

final class TutorEvidenceRanking {
    static final int SEARCH_PAGE = 8;
    static final int MAX_CONTEXT = 2 * SEARCH_PAGE;
    private static final double K1 = 1.2;
    private static final double B = 0.75;
    private static final int RRF_K = 60;
    private static final Pattern TERMS = Pattern.compile("[\\p{IsHan}]|[\\p{L}\\p{N}&&[^\\p{IsHan}]]+");
    private static final Comparator<CourseEvidence> TIMELINE = Comparator.comparingLong(CourseEvidence::startMs)
        .thenComparingLong(CourseEvidence::endMs).thenComparing(CourseEvidence::evidenceId);

    private TutorEvidenceRanking() {}

    private static List<String> terms(String text) {
        return TERMS.matcher(text.toLowerCase(Locale.ROOT)).results().map(m -> m.group()).toList();
    }

    static List<CourseEvidence> hybrid(List<CourseEvidence> all, List<CourseEvidence> dense,
                                        String query, int limit) {
        var queryTerms = new TreeSet<>(terms(query));
        var documents = all.stream().map(e -> terms(e.normalizedText())).toList();
        var averageLength = documents.stream().mapToInt(List::size).average().orElse(1);
        var frequencies = new HashMap<String,Integer>();
        for (var document : documents) {
            for (var term : new HashSet<>(document)) {
                if (queryTerms.contains(term)) frequencies.merge(term, 1, Integer::sum);
            }
        }

        var lexical = new HashMap<CourseEvidence,Double>();
        for (int i = 0; i < all.size(); i++) {
            var document = documents.get(i);
            var counts = new HashMap<String,Integer>();
            for (var term : document) {
                if (queryTerms.contains(term)) counts.merge(term, 1, Integer::sum);
            }
            double score = 0;
            for (var term : queryTerms) {
                int count = counts.getOrDefault(term, 0);
                if (count == 0) continue;
                int df = frequencies.get(term);
                double idf = Math.log1p((all.size() - df + 0.5) / (df + 0.5));
                score += idf * count * (K1 + 1) / (count + K1 * (1 - B + B * document.size() / averageLength));
            }
            if (score > 0) lexical.put(all.get(i), score);
        }

        var scores = new HashMap<CourseEvidence,Double>();
        addRanks(scores, canonical(all, dense));
        addRanks(scores, canonical(all, ranked(lexical)).stream().limit(MAX_CONTEXT).toList());
        return ranked(scores).stream().limit(limit).toList();
    }

    private static List<CourseEvidence> ranked(Map<CourseEvidence,Double> scores) {
        return scores.keySet().stream()
            .sorted(Comparator.<CourseEvidence>comparingDouble(scores::get).reversed()
                .thenComparing(CourseEvidence::evidenceId)).toList();
    }

    private static void addRanks(Map<CourseEvidence,Double> scores, List<CourseEvidence> ranked) {
        for (int i = 0; i < ranked.size(); i++) scores.merge(ranked.get(i), 1.0 / (RRF_K + i + 1), Double::sum);
    }

    private record Interval(long start, long end) {}

    private static List<CourseEvidence> canonical(List<CourseEvidence> all, List<CourseEvidence> ranked) {
        var originals = new HashMap<Interval,CourseEvidence>();
        all.stream().filter(e -> "SUBTITLE".equals(e.sourceType())).sorted(TIMELINE)
            .forEach(e -> originals.putIfAbsent(new Interval(e.startMs(), e.endMs()), e));
        return ranked.stream().map(e -> "SUBTITLE_TRANSLATION".equals(e.sourceType())
            ? originals.getOrDefault(new Interval(e.startMs(), e.endMs()), e) : e).distinct().toList();
    }

    static List<CourseEvidence> adjacent(List<CourseEvidence> all, List<CourseEvidence> anchors) {
        var selected = new LinkedHashSet<>(anchors);
        var timelines = new HashMap<String,List<CourseEvidence>>();
        for (var row : all.stream().sorted(TIMELINE).toList()) {
            timelines.computeIfAbsent(row.sourceType(), key -> new ArrayList<>()).add(row);
        }
        for (int direction : new int[]{1, -1}) {
            for (var anchor : anchors) {
                var timeline = timelines.get(anchor.sourceType());
                int neighbor = timeline.indexOf(anchor) + direction;
                if (neighbor >= 0 && neighbor < timeline.size()) selected.add(timeline.get(neighbor));
                if (selected.size() >= MAX_CONTEXT) return List.copyOf(selected);
            }
        }
        return List.copyOf(selected);
    }
}
