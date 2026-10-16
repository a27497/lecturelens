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
        default LlmRequest planningRequest(List<SubtitleSegment> batch) {return request(batch,null,Duration.ofSeconds(120));}
    }
    @FunctionalInterface public interface Sleeper { void sleep(long millis) throws InterruptedException; }
    private final TranslationPolicy policy;
    private final LlmProvider provider;
    private final Codec codec;
    private final Integer routeCap;
    private final String policyHash;
    private final Clock clock;
    private final Sleeper sleeper;
    private Instant deadline;
    private TranslationCheckpointStore.Session checkpoint;
    public TranslationBatchCoordinator checkpoint(TranslationCheckpointStore.Session session){checkpoint=session;return this;}
    private volatile int physicalCalls;
    private volatile long reservedTokens;
    private final java.util.concurrent.atomic.AtomicInteger nextBatch=new java.util.concurrent.atomic.AtomicInteger();
    private final List<LlmResult> responses = Collections.synchronizedList(new ArrayList<>());
    private java.util.function.Consumer<AdaptiveTranslationController.Event> events=e->{};
    private String providerKey="default";
    private AdaptiveTranslationController adaptive;

    public TranslationBatchCoordinator observe(String key,java.util.function.Consumer<AdaptiveTranslationController.Event> observer) {
        providerKey=key;events=observer;return this;
    }

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
        if(policy.aimd()!=null) {
            batches=TranslationBatchPlanner.plan(batches.stream().flatMap(List::stream).toList(),policy,codec);
        }
        if(checkpoint!=null)deadline=min(deadline,checkpoint.initialize(batches,codec));
        if(policy.aimd()!=null)return runAdaptive(batches);
        nextBatch.set(batches.size()+1);
        var translated = new ArrayList<Translated>();
        for (int i=0;i<batches.size();i++) translated.addAll(node(batches.get(i),0,i+1));
        checkActive();
        return new Outcome(List.copyOf(translated), List.copyOf(responses), batches.size(), physicalCalls);
    }
    private Outcome runAdaptive(List<List<SubtitleSegment>> batches) {
        nextBatch.set(batches.size()+1);
        var executor=java.util.concurrent.Executors.newFixedThreadPool(policy.aimd().maximum(),r->{var t=new Thread(r,"translation-v2-batch");t.setDaemon(true);return t;});
        var completion=new java.util.concurrent.ExecutorCompletionService<List<Translated>>(executor);
        var futures=new ArrayList<java.util.concurrent.Future<List<Translated>>>();
        try(var controller=new AdaptiveTranslationController(policy.aimd(),providerKey,events)) {
            adaptive=controller;
            int next=0,completed=0;
            while(next<Math.min(policy.aimd().maximum(),batches.size())) {
                int index=next++;var batch=batches.get(index);futures.add(completion.submit(()->node(batch,0,index+1)));
            }
            var translated=new ArrayList<Translated>();
            while(completed<batches.size()) {
                checkActive();
                var future=completion.poll(Math.max(1,remaining()),java.util.concurrent.TimeUnit.MILLISECONDS);
                if(future==null)throw TranslationFailure.of(DEADLINE_EXCEEDED);
                translated.addAll(future.get());completed++;
                if(next<batches.size()){int index=next++;var batch=batches.get(index);futures.add(completion.submit(()->node(batch,0,index+1)));}
            }
            translated.sort(Comparator.comparingInt(t->t.source().getSegmentIndex()));
            checkActive();
            return new Outcome(List.copyOf(translated),List.copyOf(responses),batches.size(),physicalCalls);
        } catch(InterruptedException ignored){Thread.currentThread().interrupt();throw TranslationFailure.of(CANCELED);}
        catch(java.util.concurrent.ExecutionException e){throw TranslationFailure.from(e.getCause());}
        finally {for(var f:futures)f.cancel(true);executor.shutdownNow();}
    }
    private List<Translated> node(List<SubtitleSegment> batch, int depth,int batchNo) {
        try {
            if(checkpoint!=null) {
                var stored=checkpoint.claim(batchNo);
                if("SUCCEEDED".equals(stored.status())) {responses.add(checkpoint.cached(stored));return stored.result();}
                if("SPLIT".equals(stored.status())) {
                    var translated=new ArrayList<Translated>();
                    for(var child:checkpoint.children(batchNo))translated.addAll(node(child.source(),child.depth(),child.number()));
                    var merged=merge(batch,translated);checkpoint.merged(batchNo,merged);return merged;
                }
            }
            return executeNode(batch,depth,batchNo);
        } catch(RuntimeException raw) {
            var failure=TranslationFailure.from(raw);
            if(checkpoint!=null)checkpoint.failNode(batchNo,failure);
            throw failure;
        }
    }
    private List<Translated> executeNode(List<SubtitleSegment> batch,int depth,int batchNo) {
        checkActive();
        String correction = null;
        int contentRetries = 0;
        for (int attempt=1; attempt<=policy.maxAttempts(); attempt++) {
            checkActive();
            int reserved = 0;
            AdaptiveTranslationController.Permit permit=null;
            boolean sent=false;
            TranslationCheckpointStore.Attempt persistedAttempt=null;
            LlmResult observed=null;
            long callStarted=System.nanoTime();
            try {
                var base = codec.request(batch, correction, Duration.ofMillis(Math.min(policy.requestTimeoutMillis(), remaining())));
                int input = TranslationTokenBudget.estimate(base,policy);
                if(policy.aimd()!=null && input>policy.aimd().inputTokenBudget()) throw TranslationFailure.of(OUTPUT_BUDGET_TOO_SMALL);
                int output = TranslationTokenBudget.output(input,policy,routeCap);
                reserved = input + output;
                var metadata = new LinkedHashMap<>(base.metadata());
                metadata.put("translationV2",true); metadata.put("translationPolicyHash",policyHash);
                metadata.put("modelRouting.stage","TRANSLATION_FULL_TEXT");
                metadata.put("translationTokenCounter",policy.tokenCounter()); metadata.put("estimatedInputTokens",input);
                metadata.put("translationBatchNo",batchNo);metadata.put("translationAttemptNo",attempt);
                var request = new LlmRequest(base.requestId(),base.taskId(),base.messages(),base.timeout(),base.temperature(),
                    output,1,metadata,LlmResponseFormat.JSON_OBJECT,base.execution());
                if(adaptive!=null)permit=adaptive.acquire(batchNo,attempt,remaining());
                reserve(reserved);
                if(checkpoint!=null) {
                    persistedAttempt=checkpoint.begin(batchNo,input,output);
                    metadata.put("translationAttemptNo",persistedAttempt.number());metadata.put("translationAttemptId",persistedAttempt.id());
                }
                request=new LlmRequest(request.requestId(),request.taskId(),request.messages(),
                    Duration.ofMillis(Math.max(1,Math.min(request.timeout().toMillis(),remaining()))),request.temperature(),request.maxTokens(),
                    1,metadata,request.responseFormat(),request.execution());
                sent=true;callStarted=System.nanoTime();
                LlmResult result = provider.generate(request);
                observed=result;
                if (result == null) throw TranslationFailure.of(EMPTY_OUTPUT);
                responses.add(result);
                reconcile(reserved, result.usage()); reserved=0;
                if ("length".equals(result.finishReason())) throw new TranslationFailure(TRUNCATED,200,result.usage(),"length",0);
                if (result.content().isBlank()) throw TranslationFailure.of(EMPTY_OUTPUT);
                var translated=codec.validate(batch,result);
                if(checkpoint!=null)checkpoint.succeeded(batchNo,persistedAttempt,translated,result,Duration.ofNanos(System.nanoTime()-callStarted).toMillis());
                if(permit!=null)permit.succeeded();
                return translated;
            } catch (RuntimeException raw) {
                var failure = TranslationFailure.from(raw);
                if(observed!=null)failure=new TranslationFailure(failure.reason(),failure.status()==null?200:failure.status(),observed.usage(),
                    observed.finishReason(),failure.retryAfterMillis(),failure.check());
                if(checkpoint!=null && persistedAttempt!=null)checkpoint.failed(batchNo,persistedAttempt,failure,Duration.ofNanos(System.nanoTime()-callStarted).toMillis());
                if (reserved > 0 && sent) reconcile(reserved,failure.usage());
                if(permit!=null){if(sent)permit.failed(failure);else permit.close();}
                if (failure.reason() == TRUNCATED || failure.reason() == OUTPUT_BUDGET_TOO_SMALL)
                    return split(batch,depth,batchNo,failure);
                if (failure.reason() == EMPTY_OUTPUT || failure.reason() == FORMAT_INVALID || failure.reason() == VALIDATION_INVALID) {
                    if (++contentRetries > 1 || attempt == policy.maxAttempts()) return split(batch,depth,batchNo,failure);
                    correction = failure.reason().name();
                    continue;
                }
                if (!failure.transportRetryable() || attempt == policy.maxAttempts()) throw failure;
                long exponential = Math.min(30000,1000L << (attempt-1));
                long delay = Math.max(failure.retryAfterMillis(),ThreadLocalRandom.current().nextLong(exponential+1));
                if (delay > 30000 || delay >= remaining()) throw failure;
                try { sleeper.sleep(delay); }
                catch (InterruptedException ignored) { Thread.currentThread().interrupt(); throw TranslationFailure.of(CANCELED); }
            } finally {if(permit!=null)permit.close();}
        }
        throw TranslationFailure.of(CALL_BUDGET_EXHAUSTED);
    }
    private synchronized void reserve(int amount) {
        checkActive();
        if(physicalCalls>=policy.maxCalls())throw TranslationFailure.of(CALL_BUDGET_EXHAUSTED);
        if(reservedTokens+amount>policy.tokenBudget())throw TranslationFailure.of(TOKEN_BUDGET_EXHAUSTED);
        physicalCalls++;reservedTokens+=amount;
    }
    private synchronized void reconcile(int reservation, LlmUsage usage) {
        // Unknown network outcomes retain their reservation; absence of usage is never zero cost.
        if (usage != null && usage.totalTokens()!=null)
            reservedTokens += (long) usage.totalTokens() - reservation;
    }
    private List<Translated> split(List<SubtitleSegment> batch, int depth,int batchNo, TranslationFailure original) {
        if (depth >= policy.maxDepth()) throw TranslationFailure.of(SPLIT_DEPTH_EXHAUSTED);
        if (batch.size()>1) {
            long total=batch.stream().mapToLong(s -> weight(s.getText())).sum(), weight=0;
            int middle=1;
            for (int i=0;i<batch.size()-1;i++) { weight+=weight(batch.get(i).getText()); middle=i+1; if(weight*2>=total) break; }
            return children(batch,List.of(List.copyOf(batch.subList(0,middle)),List.copyOf(batch.subList(middle,batch.size()))),depth,batchNo);
        }
        var source=batch.getFirst(); String text=source.getText();
        int points=text.codePointCount(0,text.length());
        if (points<2) throw original;
        int mid=text.offsetByCodePoints(0,points/2);
        int boundary=text.lastIndexOf(' ',mid);
        if(boundary>text.length()/4) mid=boundary;
        String left=text.substring(0,mid).strip(), right=text.substring(mid).strip();
        if(left.isBlank() || right.isBlank()) throw original;
        return children(batch,List.of(List.of(piece(source,left)),List.of(piece(source,right))),depth,batchNo);
    }
    private List<Translated> children(List<SubtitleSegment> parent,List<List<SubtitleSegment>> parts,int depth,int number) {
        var translated=new ArrayList<Translated>();
        if(checkpoint!=null) {
            for(var child:checkpoint.split(number,parts,depth+1,codec))translated.addAll(node(child.source(),child.depth(),child.number()));
        } else for(var part:parts)translated.addAll(node(part,depth+1,nextBatch.getAndIncrement()));
        var result=merge(parent,translated);
        if(checkpoint!=null)checkpoint.merged(number,result);
        return result;
    }
    private static List<Translated> merge(List<SubtitleSegment> parent,List<Translated> children) {
        if(parent.size()>1)return List.copyOf(children);
        return List.of(new Translated(parent.getFirst(),children.stream().map(Translated::text).collect(java.util.stream.Collectors.joining(" "))));
    }
    private static long weight(String s) { return s.getBytes(java.nio.charset.StandardCharsets.UTF_8).length; }
    private static SubtitleSegment piece(SubtitleSegment source,String text) {
        var s=new SubtitleSegment(); s.setTaskId(source.getTaskId()); s.setUserId(source.getUserId());
        s.setSegmentIndex(source.getSegmentIndex()); s.setText(text); s.setLanguage(source.getLanguage());
        // Text subdivisions retain the original interval, never an invented finer timestamp.
        s.setStartMillis(source.getStartMillis()); s.setEndMillis(source.getEndMillis()); s.setProvider(source.getProvider());
        s.setTimingSource(source.getTimingSource());s.setTimingReason(source.getTimingReason());
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
