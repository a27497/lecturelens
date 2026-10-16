package com.example.courselingo.subtitle.pipeline;

import com.example.courselingo.subtitle.domain.SubtitleSegment;
import java.util.*;

public final class TranslationBatchPlanner {
    private TranslationBatchPlanner() {}
    public static List<List<SubtitleSegment>> plan(List<SubtitleSegment> source,TranslationPolicy policy,TranslationBatchCoordinator.Codec codec) {
        var batches=new ArrayList<List<SubtitleSegment>>();var current=new ArrayList<SubtitleSegment>();
        for(var segment:source) {
            var candidate=new ArrayList<>(current);candidate.add(segment);
            if(!current.isEmpty() && TranslationTokenBudget.estimate(codec.planningRequest(candidate),policy)>policy.aimd().inputTokenBudget()) {
                batches.add(List.copyOf(current));current=new ArrayList<>();
            }
            current.add(segment);
        }
        if(!current.isEmpty())batches.add(List.copyOf(current));
        return List.copyOf(batches);
    }
}
