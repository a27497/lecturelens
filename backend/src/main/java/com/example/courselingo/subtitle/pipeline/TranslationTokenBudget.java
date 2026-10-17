package com.example.courselingo.subtitle.pipeline;

import com.example.courselingo.ai.llm.*;
import java.nio.charset.StandardCharsets;

/** An explicit conservative estimate, never reported as provider usage or an exact tokenizer. */
public final class TranslationTokenBudget {
    private TranslationTokenBudget() {}

    public static int estimate(LlmRequest request, TranslationPolicy policy) {
        long bytes = 32;
        for (var message : request.messages())
            bytes += 16L + message.role().name().length() + message.content().getBytes(StandardCharsets.UTF_8).length;
        double estimate = Math.ceil(bytes * policy.safetyFactor());
        if (estimate > Integer.MAX_VALUE) throw TranslationFailure.of(TranslationFailure.Reason.OUTPUT_BUDGET_TOO_SMALL);
        return (int) estimate;
    }

    public static int output(int input, TranslationPolicy policy, Integer routeCap) {
        int target = (int) Math.min(policy.outputMax(), Math.max(policy.outputMin(),
            Math.ceil(policy.outputRatio() * input + policy.outputSlack())));
        int effective = routeCap == null ? target : Math.min(target, routeCap);
        if (effective < policy.outputMin() || (long) input + effective + policy.contextReserve() > policy.contextLimit())
            throw TranslationFailure.of(TranslationFailure.Reason.OUTPUT_BUDGET_TOO_SMALL);
        return effective;
    }
}
