package com.example.courselingo.media;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.Timeout;
import org.junit.jupiter.api.io.TempDir;
import java.nio.file.*;
import java.util.concurrent.TimeUnit;
import static org.assertj.core.api.Assertions.*;

class SilenceAudioMediaIntegrationTest {
    @TempDir Path directory;
    @Test @Timeout(40)
    void actualFfmpegSilenceAndWavIntervalsAgreeWithoutAnyProviderCall() throws Exception {
        var input=directory.resolve("synthetic.wav");
        var generate=new ProcessBuilder("ffmpeg","-hide_banner","-loglevel","error","-nostdin","-y",
            "-f","lavfi","-i","sine=frequency=440:sample_rate=16000:duration=20",
            "-f","lavfi","-i","anullsrc=r=16000:cl=mono:d=10",
            "-f","lavfi","-i","sine=frequency=880:sample_rate=16000:duration=20",
            "-filter_complex","[0:a][1:a][2:a]concat=n=3:v=0:a=1[out]","-map","[out]","-c:a","pcm_s16le",input.toString())
            .redirectError(ProcessBuilder.Redirect.DISCARD).redirectOutput(ProcessBuilder.Redirect.DISCARD).start();
        try {assertThat(generate.waitFor(20,TimeUnit.SECONDS)).isTrue();assertThat(generate.exitValue()).isZero();}
        finally {if(generate.isAlive())generate.destroyForcibly();}
        var planner=new SilenceAudioChunkPlanner(new FfmpegProperties("ffmpeg","wav",16000,1,10),new ProcessBuilderFfmpegProcessExecutor());
        var policy=SilenceAudioChunkPlannerTest.policy();var plan=planner.plan(input,50000,directory.resolve("clips"),policy,4*1024*1024);
        assertThat(plan.chunks()).hasSize(2);
        assertThat(plan.chunks().getFirst().endMillis()).isCloseTo(25000,within(200L));
        assertThat(plan.detectedSilenceMillis()).isCloseTo(10000,within(200L));
        for(var chunk:plan.chunks()) {
            assertThat(Files.exists(chunk.audioFile())).isFalse();
            planner.materialize(input,chunk,policy,plan.maxClipBytes());
            long measured=new JavaSoundAudioDurationProbe().probeDurationMillis(chunk.audioFile());
            assertThat(measured).isCloseTo(chunk.endMillis()-chunk.offsetMillis(),within(2L));
            assertThat(Files.size(chunk.audioFile())).isLessThan(plan.maxClipBytes());
            Files.delete(chunk.audioFile());
        }
    }
}
