package com.example.courselingo.subtitle.pipeline;

import com.example.courselingo.subtitle.service.SubtitleTranslationProperties;
import org.junit.jupiter.api.Test;
import static org.assertj.core.api.Assertions.*;
import static org.mockito.Mockito.*;

class PreparationFlowPolicyTest {
    @Test void unqualifiedOverlapCannotBeActivatedOrDeserialized() throws Exception {
        assertThatThrownBy(()->new PreparationFlowPolicy(true,true,false)).hasMessageContaining("not qualified");
        assertThatThrownBy(()->new PreparationFlowPolicy(true,false,true)).hasMessageContaining("not qualified");
        var json=new com.fasterxml.jackson.databind.ObjectMapper();
        assertThatThrownBy(()->json.readValue("{\"sourceOnly\":true,\"streamingTranslation\":true,\"materialsParallel\":false}",PreparationFlowPolicy.class))
            .hasMessageContaining("not qualified");
    }
    @Test void startupValidationRejectsOverlapBeforeAnyDatabaseOrProviderCall() {
        var settings=new PipelineTranslationProperties();settings.setEnabled(true);settings.setStreamingTranslation(true);
        var jdbc=mock(org.springframework.jdbc.core.JdbcTemplate.class);
        var policies=new PipelinePolicyService(jdbc,settings,new SubtitleTranslationProperties());
        assertThatThrownBy(policies::validate).hasMessageContaining("not qualified");
        verifyNoInteractions(jdbc);
    }
    @Test void sourceOnlyRoundTripsWithExplicitDisabledOverlap() throws Exception {
        var original=new PreparationFlowPolicy(true,false,false);
        var json=new com.fasterxml.jackson.databind.ObjectMapper();
        assertThat(json.readValue(json.writeValueAsString(original),PreparationFlowPolicy.class)).isEqualTo(original);
    }
}
