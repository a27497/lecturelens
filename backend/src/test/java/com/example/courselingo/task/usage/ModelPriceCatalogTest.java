package com.example.courselingo.task.usage;

import com.example.courselingo.ai.llm.LlmUsage;
import java.time.Instant;
import org.junit.jupiter.api.Test;
import static org.assertj.core.api.Assertions.*;

class ModelPriceCatalogTest {
    static final Instant OFF=Instant.parse("2026-10-17T11:00:00Z"),PEAK=Instant.parse("2026-10-16T07:00:00Z");
    @Test void reasoningIsPartOfOutputAndCacheIsChargedOnlyOnce() {
        var c=ModelPriceCatalog.cost(ModelPriceCatalog.DEEPSEEK,new LlmUsage(1000000,1000000,2000000,500000,250000,750000),OFF,OFF.plusSeconds(1));
        assertThat(c.lower()).isEqualByComparingTo("0.71325");assertThat(c.upper()).isEqualByComparingTo(c.lower());assertThat(c.currency()).isEqualTo("USD");
    }
    @Test void missingCacheAndUnverifiedHolidayProduceHonestRanges() {
        var noCache=ModelPriceCatalog.cost(ModelPriceCatalog.DEEPSEEK,new LlmUsage(1000000,1000000,2000000),OFF,OFF.plusSeconds(1));
        assertThat(noCache.lower()).isEqualByComparingTo("0.603");assertThat(noCache.upper()).isEqualByComparingTo("0.75");
        var peak=ModelPriceCatalog.cost(ModelPriceCatalog.DEEPSEEK,new LlmUsage(1000000,1000000,2000000,0,0,1000000),PEAK,PEAK.plusSeconds(1));
        assertThat(peak.lower()).isEqualByComparingTo("0.75");assertThat(peak.upper()).isEqualByComparingTo("1.5");
        assertThat(peak.tier()).isEqualTo("PEAK_OR_HOLIDAY_OR_BOUNDARY");
    }
    @Test void invalidOrUnknownUsageIsNeverZeroAndAsrKeepsItsOwnCurrency() {
        assertThat(ModelPriceCatalog.cost(ModelPriceCatalog.DEEPSEEK,null,OFF,OFF).lower()).isNull();
        assertThat(ModelPriceCatalog.cost(ModelPriceCatalog.DEEPSEEK,new LlmUsage(10,20,30,0,30,0),OFF,OFF).lower()).isNull();
        var asr=ModelPriceCatalog.cost(ModelPriceCatalog.BAILIAN,new LlmUsage(1000000,1000000,2000000),OFF,OFF);
        assertThat(asr.currency()).isEqualTo("CNY");assertThat(asr.lower()).isEqualByComparingTo("3.5");
        assertThat(ModelPriceCatalog.select("https://proxy.invalid/chat","deepseek-flash")).isNull();
    }
}
