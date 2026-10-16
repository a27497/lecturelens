package com.example.courselingo.subtitle.pipeline;

import com.example.courselingo.ai.llm.TranslationFailure;
import java.time.*;
import java.util.UUID;
import java.util.function.Consumer;

public final class AdaptiveTranslationController implements AutoCloseable {
    public record Event(long localSequence,Instant time,int oldWindow,int window,int inflight,long windowEpoch,
        int streak,String reason,int batchNo,int attemptNo,long cooldownUntilMillis) {}
    private final TranslationAimdPolicy policy;
    private final Consumer<Event> observer;
    private final String key,id=UUID.randomUUID().toString();
    private final TranslationProviderLimiter.Bucket shared;
    private int window,slots,inflight,streak;
    private long epoch,sequence,cooldown;
    private boolean closed;

    public AdaptiveTranslationController(TranslationAimdPolicy policy,String providerKey,Consumer<Event> observer) {
        this.policy=policy;this.key=providerKey;this.observer=observer;
        this.window=policy.initial();shared=TranslationProviderLimiter.register(key,id,policy.processMaximum());
        try {event("START",window,0,0);}catch(RuntimeException e){TranslationProviderLimiter.unregister(key,id);throw e;}
    }
    public synchronized int window(){return window;}
    public synchronized int inflight(){return inflight;}
    public Permit acquire(int batch,int attempt,long remainingMillis) {
        long deadline=System.nanoTime()+Math.max(0,remainingMillis)*1_000_000;
        for(;;) {
        boolean slot=false,global=false,counted=false,transferred=false;
        try {
            synchronized(this) {
                while(!closed && (slots>=window || System.currentTimeMillis()<cooldown)) {
                    long remaining=deadline-System.nanoTime();
                    if(remaining<=0) throw TranslationFailure.of(TranslationFailure.Reason.DEADLINE_EXCEEDED);
                    long wait=System.currentTimeMillis()<cooldown?Math.min(remaining,(cooldown-System.currentTimeMillis())*1_000_000):remaining;
                    java.util.concurrent.TimeUnit.NANOSECONDS.timedWait(this,Math.max(1,wait));
                }
                if(closed) throw TranslationFailure.of(TranslationFailure.Reason.CANCELED);
                if(deadline-System.nanoTime()<=0)throw TranslationFailure.of(TranslationFailure.Reason.DEADLINE_EXCEEDED);
                slots++;slot=true;
            }
            shared.acquire(deadline);global=true;
            synchronized(this) {
                if(closed)throw TranslationFailure.of(TranslationFailure.Reason.CANCELED);
                // A reduction/cooldown may have happened while waiting for the shared provider slot.
                if(inflight>=window || System.currentTimeMillis()<cooldown) continue;
                inflight++;counted=true;event("REQUEST_STARTED",window,batch,attempt);
                transferred=true;
                return new Permit(epoch,batch,attempt);
            }
        } catch(InterruptedException ignored) {Thread.currentThread().interrupt();throw TranslationFailure.of(TranslationFailure.Reason.CANCELED);}
        finally {
            // A successful acquisition transfers both permits to Permit.close().
            if(slot && !transferred) {synchronized(this){slots--;if(counted)inflight--;notifyAll();}
                if(global){shared.release();TranslationProviderLimiter.cleanUp(key,shared);}}
        }
        }
    }
    public final class Permit implements AutoCloseable {
        private final long dispatchedEpoch;
        private final int batch,attempt;
        private boolean finished;
        private Permit(long epoch,int batch,int attempt){dispatchedEpoch=epoch;this.batch=batch;this.attempt=attempt;}
        public void succeeded(){finish(null);}
        public void failed(TranslationFailure failure){finish(failure);}
        private void finish(TranslationFailure failure) {
            synchronized(AdaptiveTranslationController.this) {
                if(finished)return;
                int old=window;
                if(failure==null && dispatchedEpoch==epoch) {
                    if(++streak>=policy.successStreak()){window=Math.min(policy.maximum(),window+1);streak=0;}
                } else if(failure!=null) {
                    streak=0;
                    if(failure.reason()==TranslationFailure.Reason.RATE_LIMITED || failure.reason()==TranslationFailure.Reason.TIMEOUT) {
                        if(dispatchedEpoch==epoch){window=Math.max(policy.minimum(),window/2);epoch++;}
                        cooldown=Math.max(cooldown,System.currentTimeMillis()+Math.min(30000,Math.max(1000,failure.retryAfterMillis())));
                    }
                }
                try {event(failure==null?"SUCCESS":failure.reason().name(),old,batch,attempt);}
                finally {close();}
            }
        }
        @Override public void close() {
            synchronized(AdaptiveTranslationController.this) {
                if(finished)return;finished=true;inflight--;slots--;AdaptiveTranslationController.this.notifyAll();
            }
            shared.release();
            TranslationProviderLimiter.cleanUp(key,shared);
        }
    }
    private void event(String reason,int old,int batch,int attempt) {
        observer.accept(new Event(++sequence,Instant.now(),old,window,inflight,epoch,streak,reason,batch,attempt,cooldown));
    }
    @Override public void close() {
        synchronized(this){closed=true;notifyAll();}
        TranslationProviderLimiter.unregister(key,id);
    }
}
