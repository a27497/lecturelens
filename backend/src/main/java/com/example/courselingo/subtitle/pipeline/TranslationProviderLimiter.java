package com.example.courselingo.subtitle.pipeline;

import com.example.courselingo.ai.llm.TranslationFailure;
import java.util.*;
import java.util.concurrent.ConcurrentHashMap;

/** Shared per provider across tasks; no credentials are used as map keys. */
final class TranslationProviderLimiter {
    private static final ConcurrentHashMap<String,Bucket> BUCKETS=new ConcurrentHashMap<>();
    static final class Bucket {
        private final Map<String,Integer> registrations=new HashMap<>();
        private int active;
        synchronized void register(String id,int limit){registrations.put(id,limit);notifyAll();}
        synchronized void unregister(String id){registrations.remove(id);notifyAll();}
        synchronized void acquire(long deadlineNanos) throws InterruptedException {
            while(active>=registrations.values().stream().mapToInt(Integer::intValue).min().orElse(1)) {
                long remaining=deadlineNanos-System.nanoTime();
                if(remaining<=0)throw TranslationFailure.of(TranslationFailure.Reason.DEADLINE_EXCEEDED);
                java.util.concurrent.TimeUnit.NANOSECONDS.timedWait(this,remaining);
            }
            active++;
        }
        synchronized void release(){active--;notifyAll();}
    }
    static Bucket register(String key,String id,int limit) {
        // Registration and removal serialize through compute, preventing detached buckets.
        return BUCKETS.compute(key,(k,b)->{if(b==null)b=new Bucket();b.register(id,limit);return b;});
    }
    static void unregister(String key,String id) {
        BUCKETS.computeIfPresent(key,(k,b)->{synchronized(b){b.unregister(id);return b.registrations.isEmpty() && b.active==0?null:b;}});
    }
    static void cleanUp(String key,Bucket expected) {
        BUCKETS.computeIfPresent(key,(k,b)->{synchronized(b){return b==expected && b.registrations.isEmpty() && b.active==0?null:b;}});
    }
}
