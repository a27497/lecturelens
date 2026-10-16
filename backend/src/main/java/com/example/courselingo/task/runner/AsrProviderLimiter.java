package com.example.courselingo.task.runner;

import com.example.courselingo.ai.asr.AsrPipelinePolicy;

import com.example.courselingo.ai.llm.TranslationFailure;
import java.util.*;
import java.util.concurrent.*;

/** Registrations share the strictest active task cap; keys contain no credentials. */
final class AsrProviderLimiter {
    private static final ConcurrentHashMap<String,Bucket> BUCKETS=new ConcurrentHashMap<>();
    private record Limits(int maximum,int rate) {}
    private static final class Bucket {
        private final Map<String,Limits> registrations=new HashMap<>();
        private int active;
        private long nextNanos;
        synchronized void acquire(String id,long deadline) throws InterruptedException {
            while(true) {
                if(!registrations.containsKey(id))throw TranslationFailure.of(TranslationFailure.Reason.CANCELED);
                long now=System.nanoTime(),remaining=deadline-now;
                if(remaining<=0)throw TranslationFailure.of(TranslationFailure.Reason.DEADLINE_EXCEEDED);
                int maximum=registrations.values().stream().mapToInt(Limits::maximum).min().orElse(1);
                if(active<maximum && now>=nextNanos) {
                    active++;
                    int rate=registrations.values().stream().mapToInt(Limits::rate).min().orElse(1);
                    nextNanos=now+TimeUnit.SECONDS.toNanos(1)/rate;return;
                }
                TimeUnit.NANOSECONDS.timedWait(this,Math.min(remaining,TimeUnit.MILLISECONDS.toNanos(50)));
            }
        }
    }
    static Registration register(AsrPipelinePolicy policy) {
        String id=UUID.randomUUID().toString(),key=policy.limiterKey();
        var bucket=BUCKETS.compute(key,(k,b)->{
            if(b==null)b=new Bucket();synchronized(b){b.registrations.put(id,new Limits(policy.maximum(),policy.requestsPerSecond()));b.notifyAll();}return b;
        });
        return new Registration(key,id,bucket);
    }
    static final class Registration implements AutoCloseable {
        private final String key,id;
        private final Bucket bucket;
        private boolean closed;
        Registration(String key,String id,Bucket bucket){this.key=key;this.id=id;this.bucket=bucket;}
        AutoCloseable acquire(long deadline) throws InterruptedException {
            synchronized(this){if(closed)throw TranslationFailure.of(TranslationFailure.Reason.CANCELED);}
            bucket.acquire(id,deadline);
            return ()->{synchronized(bucket){bucket.active--;bucket.notifyAll();}clean(key,bucket);};
        }
        public synchronized void close() {
            if(closed)return;closed=true;
            BUCKETS.computeIfPresent(key,(k,b)->{synchronized(b){b.registrations.remove(id);b.notifyAll();return b.registrations.isEmpty()&&b.active==0?null:b;}});
        }
    }
    private static void clean(String key,Bucket expected) {
        BUCKETS.computeIfPresent(key,(k,b)->{synchronized(b){return b==expected&&b.registrations.isEmpty()&&b.active==0?null:b;}});
    }
}
