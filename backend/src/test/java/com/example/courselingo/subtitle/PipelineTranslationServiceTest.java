package com.example.courselingo.subtitle;

import com.example.courselingo.ai.llm.*;
import com.example.courselingo.subtitle.domain.*;
import com.example.courselingo.subtitle.mapper.*;
import com.example.courselingo.subtitle.pipeline.*;
import com.example.courselingo.subtitle.service.*;
import com.example.courselingo.systemmodel.*;
import org.junit.jupiter.api.Test;
import java.time.*;
import java.util.*;
import java.util.concurrent.atomic.AtomicInteger;
import static org.assertj.core.api.Assertions.*;
import static org.mockito.Mockito.*;
import static org.mockito.ArgumentMatchers.*;

class PipelineTranslationServiceTest {
    @Test void v2WiringSplitsLengthAndPublishesOnlyAfterStrictCompleteValidation() {
        var sources=mock(SubtitleSegmentMapper.class);var translated=mock(SubtitleTranslationSegmentMapper.class);
        var full=mock(TaskFullTextResultMapper.class);var systems=mock(SystemModelExecutionService.class);
        var policies=mock(PipelinePolicyService.class);var calls=new AtomicInteger();
        var ref=new SystemModelExecutionRef("snapshot",10,"task",9);
        var source=new SubtitleSegment();source.setSegmentIndex(0);source.setTaskId("task");source.setUserId(9L);
        source.setStartMillis(0L);source.setEndMillis(30000L);source.setText("This is the first statement. This is the second statement.");source.setLanguage("en");
        when(sources.selectByTaskIdAndUserId("task",9L)).thenReturn(List.of(source));
        when(full.insert(any(TaskFullTextResult.class))).thenReturn(1);
        when(translated.insert(any(SubtitleTranslationSegment.class))).thenReturn(1);
        when(systems.fullText(ref)).thenReturn(true);
        when(systems.route(ref,"TRANSLATION_FULL_TEXT")).thenReturn(new SystemModelResolvedRoute("TRANSLATION_FULL_TEXT","DATABASE",SystemModelProtocol.OPENAI_CHAT,"id",1L,1L,
            "https://api.deepseek.com","deepseek-flash",Set.of("JSON_OUTPUT"),null,null,null,null,true,"1234"));
        var props=new PipelineTranslationProperties();var original=new SubtitleTranslationProperties();
        when(policies.find("task",9)).thenReturn(Optional.of(new PipelinePolicyService.Frozen(
            props.freeze(Duration.ofSeconds(120),Duration.ofMinutes(15),1,1000),"policy",Instant.now().plusSeconds(1800),ref)));
        var provider=new LlmProvider() {
            public String providerName(){return "mock";}
            public LlmResult generate(LlmRequest r) {
                if(calls.incrementAndGet()==1) throw new TranslationFailure(TranslationFailure.Reason.TRUNCATED,200,new LlmUsage(10,15,25),"length",0);
                assertThat(r.maxAttempts()).isEqualTo(1);
                return new LlmResult("mock","deepseek-flash","{\"segments\":[{\"index\":0,\"text\":\"这是课程中的完整译文。\"}]}","stop",new LlmUsage(10,15,25),Duration.ZERO,Map.of());
            }
        };
        var service=new SubtitleTranslationServiceImpl(sources,translated,full,provider,Clock.systemUTC(),new SubtitleTranslationResponseParser(),original);
        service.configureSystemModels(systems);service.configurePipelinePolicies(policies);
        var out=service.translateTaskSubtitlesWithAiCallRecord(new TranslateSubtitleCommand("task",9L,"en","zh-CN","req",ref));
        assertThat(out.savedCount()).isEqualTo(1);assertThat(calls.get()).isEqualTo(3);
        verify(translated,times(1)).insert(any(SubtitleTranslationSegment.class));verify(full,times(1)).insert(any(TaskFullTextResult.class));
    }
}
