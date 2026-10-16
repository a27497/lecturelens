package com.example.courselingo.subtitle.pipeline;

import com.example.courselingo.ai.llm.*;
import com.example.courselingo.subtitle.domain.SubtitleSegment;
import java.time.*;
import java.util.*;
import java.util.concurrent.ThreadLocalRandom;
import static com.example.courselingo.ai.llm.TranslationFailure.Reason.*;

public final class TranslationBatchCoordinator {
    public record Translated(SubtitleSegment source, String text) {}
    public record Outcome(List<Translated> translations, List<LlmResult> responses, int plannedBatches, int physicalCalls) {}
    public interface Codec {
        LlmRequest request(List<SubtitleSegment> batch, String correction, Duration timeout);
        List<Translated> validate(List<SubtitleSegment> batch, LlmResult result);
    }
    @FunctionalInterface public interface Sleeper { void sleep(long millis) throws InterruptedException; }
    private final TranslationPolicy policy;
    private final LlmProvider provider;
    private final Codec codec;
    private final Integer routeCap;
    private final String policyHash;
    private final Clock clock;
    private final Sleeper sleeper;
    private final Instant deadline;
    private int physicalCalls;
    private long reservedTokens;
    private final List<LlmResult> responses = new ArrayList<>();

    public TranslationBatchCoordinator(PipelinePolicyService.Frozen frozen, LlmProvider provider, Codec codec, Integer routeCap) {
        this(frozen,provider,codec,routeCap,Clock.systemUTC(),Thread::sleep);
    }
    public TranslationBatchCoordinator(PipelinePolicyService.Frozen frozen, LlmProvider provider, Codec codec,
            Integer routeCap, Clock clock, Sleeper sleeper) {
        this.policy=frozen.policy(); this.provider=provider; this.codec=codec; this.routeCap=routeCap;
        this.policyHash=frozen.hash(); this.clock=clock; this.sleeper=sleeper;
        this.deadline = min(frozen.deadline(), clock.instant().plusMillis(policy.totalTimeoutMillis()));
    }
    public Outcome run(List<List<SubtitleSegment>> batches) {
        var translated = new ArrayList<Translated>();
        for (var batch : batches) translated.addAll(node(batch,0));
        return new Outcome(List.copyOf(translated), List.copyOf(responses), batches.size(), physicalCalls);
    }
    private List<Translated> node(List<SubtitleSegment> batch, int depth) {
        checkActive();
        String correction = null;
        int contentRetries = 0;
        for (int attempt=1; attempt<=policy.maxAttempts(); attempt++) {
            checkActive();
            int reserved = 0;
            try {
                var base = codec.request(batch, correction, Duration.ofMillis(Math.min(policy.requestTimeoutMillis(), remaining())));
                int input = TranslationTokenBudget.estimate(base,policy);
                int output = TranslationTokenBudget.output(input,policy,routeCap);
                if (physicalCalls >= policy.maxCalls()) throw TranslationFailure.of(CALL_BUDGET_EXHAUSTED);
                reserved = input + output;
                if (reservedTokens + reserved > policy.tokenBudget()) throw TranslationFailure.of(TOKEN_BUDGET_EXHAUSTED);
                var metadata = new LinkedHashMap<>(base.metadata());
                metadata.put("translationV2",true); metadata.put("translationPolicyHash",policyHash);
                metadata.put("modelRouting.stage","TRANSLATION_FULL_TEXT");
                metadata.put("translationTokenCounter",policy.tokenCounter()); metadata.put("estimatedInputTokens",input);
                var request = new LlmRequest(base.requestId(),base.taskId(),base.messages(),base.timeout(),base.temperature(),
                    output,1,metadata,LlmResponseFormat.JSON_OBJECT,base.execution());
                physicalCalls++; reservedTokens += reserved;
                LlmResult result = provider.generate(request);
                if (result == null) throw TranslationFailure.of(EMPTY_OUTPUT);
                responses.add(result);
                reconcile(reserved, result.usage()); reserved=0;
                if ("length".equals(result.finishReason())) throw new TranslationFailure(TRUNCATED,200,result.usage(),"length",0);
                if (result.content().isBlank()) throw TranslationFailure.of(EMPTY_OUTPUT);
                return codec.validate(batch,result);
            } catch (RuntimeException raw) {
                var failure = TranslationFailure.from(raw);
                if (reserved > 0) reconcile(reserved,failure.usage());
                if (failure.reason() == TRUNCATED || failure.reason() == OUTPUT_BUDGET_TOO_SMALL)
                    return split(batch,depth,failure);
                if (failure.reason() == EMPTY_OUTPUT || failure.reason() == FORMAT_INVALID || failure.reason() == VALIDATION_INVALID) {
                    if (++contentRetries > 1 || attempt == policy.maxAttempts()) return split(batch,depth,failure);
                    correction = failure.reason().name();
                    continue;
                }
                if (!failure.transportRetryable() || attempt == policy.maxAttempts()) throw failure;
                long exponential = Math.min(30000,1000L << (attempt-1));
                long delay = Math.max(failure.retryAfterMillis(),ThreadLocalRandom.current().nextLong(exponential+1));
                if (delay > 30000 || delay >= remaining()) throw failure;
                try { sleeper.sleep(delay); }
                catch (InterruptedException ignored) { Thread.currentThread().interrupt(); throw TranslationFailure.of(CANCELED); }
            }
        }
        throw TranslationFailure.of(CALL_BUDGET_EXHAUSTED);
    }
    private void reconcile(int reservation, LlmUsage usage) {
        // Unknown network outcomes retain their reservation; absence of usage is never zero cost.
        if (usage != null && usage.totalTokens()!=null)
            reservedTokens += (long) usage.totalTokens() - reservation;
    }
    private List<Translated> split(List<SubtitleSegment> batch, int depth, TranslationFailure original) {
        if (depth >= policy.maxDepth()) throw TranslationFailure.of(SPLIT_DEPTH_EXHAUSTED);
        if (batch.size()>1) {
            long total=batch.stream().mapToLong(s -> weight(s.getText())).sum(), weight=0;
            int middle=1;
            for (int i=0;i<batch.size()-1;i++) { weight+=weight(batch.get(i).getText()); middle=i+1; if(weight*2>=total) break; }
            var result=new ArrayList<Translated>(node(List.copyOf(batch.subList(0,middle)),depth+1));
            result.addAll(node(List.copyOf(batch.subList(middle,batch.size())),depth+1));
            return List.copyOf(result);
        }
        var source=batch.getFirst(); String text=source.getText();
        int points=text.codePointCount(0,text.length());
        if (points<2) throw original;
        int mid=text.offsetByCodePoints(0,points/2);
        int boundary=text.lastIndexOf(' ',mid);
        if(boundary>text.length()/4) mid=boundary;
        String left=text.substring(0,mid).strip(), right=text.substring(mid).strip();
        if(left.isBlank() || right.isBlank()) throw original;
        var a=node(List.of(piece(source,left)),depth+1);
        var b=node(List.of(piece(source,right)),depth+1);
        return List.of(new Translated(source,a.getFirst().text()+" "+b.getFirst().text()));
    }
    private static long weight(String s) { return s.getBytes(java.nio.charset.StandardCharsets.UTF_8).length; }
    private static SubtitleSegment piece(SubtitleSegment source,String text) {
        var s=new SubtitleSegment(); s.setTaskId(source.getTaskId()); s.setUserId(source.getUserId());
        s.setSegmentIndex(source.getSegmentIndex()); s.setText(text); s.setLanguage(source.getLanguage());
        // Text subdivisions retain the original interval, never an invented finer timestamp.
        s.setStartMillis(source.getStartMillis()); s.setEndMillis(source.getEndMillis()); s.setProvider(source.getProvider());
        return s;
    }
    private long remaining() { return Duration.between(clock.instant(),deadline).toMillis(); }
    private void checkActive() {
        if(Thread.currentThread().isInterrupted()) throw TranslationFailure.of(CANCELED);
        if(remaining()<=0) throw TranslationFailure.of(DEADLINE_EXCEEDED);
        if(reservedTokens>policy.tokenBudget()) throw TranslationFailure.of(TOKEN_BUDGET_EXHAUSTED);
    }
    private static Instant min(Instant a,Instant b) { return a.isBefore(b)?a:b; }
}
