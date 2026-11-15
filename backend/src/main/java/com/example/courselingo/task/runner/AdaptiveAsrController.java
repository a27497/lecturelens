package com.example.courselingo.task.runner;

import com.example.courselingo.ai.asr.*;
import com.example.courselingo.task.service.AsrExecutionStore;

import com.example.courselingo.ai.llm.TranslationFailure;
import java.nio.file.*;
import java.security.MessageDigest;
import java.time.*;
import java.util.HexFormat;
import java.util.function.Supplier;

/** Cache/restore precede permits; every physical retry reserves persisted task and shared provider capacity. */
public final class AdaptiveAsrController implements AutoCloseable {
    private final AsrExecutionStore.Session session;
    private final AsrProviderLimiter.Registration shared;
    private final long deadline;
    public AdaptiveAsrController(AsrExecutionStore.Session session) {
        this.session=session;shared=AsrProviderLimiter.register(session.policy());
        deadline=System.nanoTime()+Math.max(0,Duration.between(Instant.now(),session.deadline()).toNanos());
    }
    public SpeechToTextResult transcribe(int index,Path file,Supplier<SpeechToTextResult> call) {
        var restored=session.reusable(index,audioHash(file));
        if(restored.isPresent())return restored.get();
        while(true) {
            try(AutoCloseable processPermit=shared.acquire(deadline)) {
                var permit=session.tryAcquire(index);
                if(permit!=null) {
                    SpeechToTextResult result;
                    try {result=call.get();AsrExecutionStore.Stored.from(result);}
                    catch(RuntimeException failure) {
                        var safe=failure instanceof AsrProviderException provider?AsrCallFailure.provider(provider):
                            new AsrCallFailure(AsrCallFailure.Category.NETWORK,false,null);
                        session.failed(permit,safe);throw safe;
                    }
                    // A failed completion fence is not a retryable provider failure.
                    session.succeeded(permit,result);return result;
                }
            } catch(InterruptedException interrupted) {
                Thread.currentThread().interrupt();throw TranslationFailure.of(TranslationFailure.Reason.CANCELED);
            } catch(RuntimeException safe){throw safe;}
            catch(Exception ignored){throw TranslationFailure.of(TranslationFailure.Reason.CANCELED);}
            try {Thread.sleep(25);}catch(InterruptedException interrupted){Thread.currentThread().interrupt();throw TranslationFailure.of(TranslationFailure.Reason.CANCELED);}
        }
    }
    public Duration remainingTimeout(Duration configured) {
        long remaining=deadline-System.nanoTime();
        if(remaining<=0)throw TranslationFailure.of(TranslationFailure.Reason.DEADLINE_EXCEEDED);
        return Duration.ofNanos(Math.min(configured.toNanos(),remaining));
    }
    public static String audioHash(Path file) {
        try(var input=Files.newInputStream(file)) {
            var digest=MessageDigest.getInstance("SHA-256");byte[] block=new byte[1024*1024];int count;
            while((count=input.read(block))!=-1)digest.update(block,0,count);
            return HexFormat.of().formatHex(digest.digest());
        } catch(Exception ignored){throw new AsrCallFailure(AsrCallFailure.Category.INVALID_REQUEST,false,null);}
    }
    public void close(){shared.close();}
}
