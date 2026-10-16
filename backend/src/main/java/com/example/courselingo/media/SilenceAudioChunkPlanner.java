package com.example.courselingo.media;

import com.example.courselingo.ai.asr.TranscriptTimingSource;
import com.example.courselingo.common.error.ErrorCode;
import com.example.courselingo.common.exception.BusinessException;
import org.springframework.stereotype.Service;
import java.nio.file.*;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.time.Duration;
import java.util.*;
import java.util.regex.Pattern;

@Service
public class SilenceAudioChunkPlanner {
    public record Silence(long start,long end) {}
    public record Plan(List<AudioChunk> chunks,String hash,long detectedSilenceMillis,long maxClipBytes) {}
    private static final Pattern EVENT=Pattern.compile("silence_(start|end):\\s*(\\S+)");
    private final FfmpegProperties properties;
    private final FfmpegProcessExecutor processes;
    public SilenceAudioChunkPlanner(FfmpegProperties properties,FfmpegProcessExecutor processes) {
        this.properties=properties;this.processes=processes;
    }

    public Plan plan(Path audio,long duration,Path directory,SilenceSegmentationPolicy policy,long providerMaxBytes) {
        properties.validate();
        if(duration<=0 || !Files.isRegularFile(audio)) throw failure("Invalid audio for silence planning");
        var command=List.of(properties.executable(),"-hide_banner","-nostdin","-i",audio.toAbsolutePath().toString(),
            "-af","silencedetect=noise="+policy.noiseDb()+"dB:d="+seconds(policy.pauseMillis()),"-f","null","-");
        var result=execute(command,true);
        if(result.stderr().contains("[OUTPUT_TRUNCATED]")) throw failure("Silence observations exceeded capture limit");
        var silences=parse(result.stderr(),duration);
        return partition(duration,silences,directory,policy,Math.min(providerMaxBytes,policy.maxClipBytes()));
    }

    static List<Silence> parse(String stderr,long duration) {
        var result=new ArrayList<Silence>();var matcher=EVENT.matcher(stderr);Long start=null;
        while(matcher.find()) {
            double seconds;
            try {seconds=Double.parseDouble(matcher.group(2));}catch(NumberFormatException ignored){throw failure("Invalid silence interval");}
            if(!Double.isFinite(seconds) || seconds<0 || seconds*1000>duration+1000) throw failure("Invalid silence interval");
            long time=Math.min(duration,Math.round(seconds*1000));
            if(matcher.group(1).equals("start")) {
                if(start!=null || !result.isEmpty() && time<result.getLast().end()) throw failure("Invalid silence ordering");
                start=time;
            } else {
                if(start==null || time<start) throw failure("Invalid silence ordering");
                if(time>start) result.add(new Silence(start,time));start=null;
            }
            if(result.size()>10000) throw failure("Too many silence intervals");
        }
        if(start!=null && start<duration) result.add(new Silence(start,duration));
        return List.copyOf(result);
    }

    static Plan partition(long duration,List<Silence> silences,Path directory,SilenceSegmentationPolicy policy,long maxBytes) {
        long rate=(long)policy.sampleRate()*policy.channels()*2;
        long fileMillis=(maxBytes-4096)*1000/rate;
        long max=Math.min(policy.maxMillis(),fileMillis);
        if(max<1000) throw failure("Provider audio file limit is too small");
        var spans=new ArrayList<Silence>();long from=0;
        for(var silence:silences) {
            if(silence.start()==0 || silence.end()==duration || silence.end()-silence.start()>=policy.minMillis()) {
                if(silence.start()>from) spans.add(new Silence(from,silence.start()));
                from=silence.end();
            }
        }
        if(from<duration) spans.add(new Silence(from,duration));
        var chunks=new ArrayList<AudioChunk>();
        for(var span:spans) {
            long start=span.start();
            while(start<span.end()) {
                long upper=Math.min(span.end(),start+max), end=upper;
                boolean atSilence=silences.stream().anyMatch(s->s.start()==span.end());
                if(upper<span.end() || upper-start>policy.targetMillis()) {
                    long best=Long.MAX_VALUE;boolean found=false;
                    for(var silence:silences) {
                        long cut=silence.start()+(silence.end()-silence.start())/2;
                        if(cut<start+policy.minMillis() || cut>upper) continue;
                        long distance=Math.abs(cut-start-policy.targetMillis());
                        if(distance<best) {best=distance;end=cut;found=true;}
                    }
                    atSilence=found;
                }
                String reason=end-start<policy.minMillis() ? (fileMillis<policy.minMillis()?"FILE_SIZE_LIMIT":
                    end==duration?"TRAILING_FRAGMENT":"SHORT_SPEECH_ISLAND") : !atSilence && end<span.end()?"MAX_DURATION":null;
                if(chunks.size()>=policy.maxClips()) throw failure("Silence clip count exceeded policy limit");
                int index=chunks.size();
                chunks.add(new AudioChunk(index,start,directory.resolve("silence-"+index+".wav"),end,
                    atSilence?TranscriptTimingSource.SILENCE_SPLIT:TranscriptTimingSource.AUDIO_CLIP,reason));
                start=end;
            }
        }
        if(chunks.isEmpty()) throw new BusinessException(ErrorCode.AI_PROVIDER_FAILED,"NO_SPEECH");
        String identity=chunks.stream().map(c->c.index()+":"+c.offsetMillis()+":"+c.endMillis()+":"+c.timingSource()+":"+c.timingReason())
            .collect(java.util.stream.Collectors.joining("|"));
        return new Plan(List.copyOf(chunks),hash(policy.toString()+"|"+identity),
            silences.stream().mapToLong(s->s.end()-s.start()).sum(),maxBytes);
    }

    /** Materialized inside a bounded ASR worker and deleted after each attempt. */
    public void materialize(Path source,AudioChunk clip,SilenceSegmentationPolicy policy,long maxBytes) {
        try {
            Files.createDirectories(clip.audioFile().getParent());
            var command=List.of(properties.executable(),"-hide_banner","-nostdin","-y","-ss",seconds(clip.offsetMillis()),
                "-i",source.toAbsolutePath().toString(),"-t",seconds(clip.endMillis()-clip.offsetMillis()),
                "-vn","-c:a","pcm_s16le","-ar",String.valueOf(policy.sampleRate()),"-ac",String.valueOf(policy.channels()),
                "-f","wav",clip.audioFile().toAbsolutePath().toString());
            execute(command,false);
            long size=Files.size(clip.audioFile());
            if(size<=44 || size>maxBytes) throw failure("Materialized audio clip violates file size limit");
        } catch(BusinessException safe) {throw safe;}
        catch(Exception ignored) {throw failure("Audio clip could not be materialized");}
    }
    private FfmpegProcessResult execute(List<String> command,boolean capture) {
        try {
            var r=capture?processes.executeBounded(command,Duration.ofSeconds(Math.min(300,properties.timeoutSeconds())),256*1024)
                :processes.execute(command,Duration.ofSeconds(Math.min(300,properties.timeoutSeconds())));
            if(r.timedOut()) throw new BusinessException(ErrorCode.MEDIA_FFMPEG_TIMEOUT,"Audio segmentation timed out");
            if(r.exitCode()!=0) throw failure("Audio segmentation failed");
            return r;
        } catch(InterruptedException ignored) {Thread.currentThread().interrupt();throw failure("Audio segmentation interrupted");}
        catch(java.io.IOException ignored) {throw failure("Audio segmentation failed");}
    }
    private static String seconds(long millis) {return java.math.BigDecimal.valueOf(millis,3).toPlainString();}
    private static String hash(String text) {
        try{return HexFormat.of().formatHex(MessageDigest.getInstance("SHA-256").digest(text.getBytes(StandardCharsets.UTF_8)));}
        catch(Exception ignored){throw new IllegalStateException("SHA-256 unavailable");}
    }
    private static BusinessException failure(String message) {return new BusinessException(ErrorCode.MEDIA_FFMPEG_FAILED,message);}
}
