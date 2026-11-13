package com.example.courselingo.task.usage;

import com.example.courselingo.ai.llm.LlmUsage;
import com.fasterxml.jackson.databind.ObjectMapper;
import java.math.*;
import java.net.URI;
import java.time.*;
import java.util.*;

/** Frozen catalog estimates, not account bills. Reasoning tokens are already part of completion. */
public final class ModelPriceCatalog {
    public record Card(String id,String model,String currency,String source,String checkedAt,String rates) {}
    public record Cost(String tier,String currency,BigDecimal lower,BigDecimal upper) {}
    public static final Card DEEPSEEK=new Card("catalog-20261016-deepseek-flash","deepseek-flash","USD",
        "https://api-docs.deepseek.com/quick_start/pricing/","2026-10-16",
        "{\"offPeakHit\":0.003,\"offPeakMiss\":0.15,\"offPeakOutput\":0.6,\"peakHit\":0.006,\"peakMiss\":0.3,\"peakOutput\":1.2}");
    public static final Card BAILIAN=new Card("catalog-20261016-qwen-audio-3.1-asr-flash","qwen-audio-3.1-asr-flash","CNY",
        "https://help.aliyun.com/zh/model-studio/model-pricing","2026-10-16","{\"input\":0.8,\"output\":2.7}");
    private ModelPriceCatalog(){}
    public static Card select(String address,String model) {
        String host=URI.create(address).getHost();
        var uri=URI.create(address);if(!"https".equalsIgnoreCase(uri.getScheme()) || uri.getPort()!=-1 && uri.getPort()!=443)return null;
        if("api.deepseek.com".equalsIgnoreCase(host) && DEEPSEEK.model().equals(model))return DEEPSEEK;
        if("dashscope.aliyuncs.com".equalsIgnoreCase(host) && BAILIAN.model().equals(model))return BAILIAN;
        return null;
    }
    public static Cost cost(Card card,LlmUsage usage,Instant start,Instant end) {
        if(card==null)return new Cost("UNPRICED",null,null,null);
        if(usage==null || usage.promptTokens()==null || usage.completionTokens()==null)return new Cost("UNKNOWN_USAGE",card.currency(),null,null);
        long prompt=usage.promptTokens(),output=usage.completionTokens();
        if(card==BAILIAN) {var amount=amount(prompt,"0.8").add(amount(output,"2.7"));return new Cost("CATALOG",card.currency(),amount,amount);}
        long minHit=0,maxHit=prompt;
        if(usage.cacheHitTokens()!=null)minHit=maxHit=usage.cacheHitTokens();
        if(usage.cacheMissTokens()!=null){long inferred=prompt-usage.cacheMissTokens();if(usage.cacheHitTokens()!=null && inferred!=minHit)return new Cost("INCONSISTENT_USAGE",card.currency(),null,null);minHit=maxHit=inferred;}
        if(minHit<0 || maxHit>prompt || usage.reasoningTokens()!=null && usage.reasoningTokens()>output)return new Cost("INCONSISTENT_USAGE",card.currency(),null,null);
        // Without a verified holiday calendar, weekday peak hours remain a range. Cross-boundary calls also remain ranges.
        boolean offPeak=certainlyOffPeak(start,end);
        var lower=amount(maxHit,"0.003").add(amount(prompt-maxHit,"0.15")).add(amount(output,"0.6"));
        var upper=amount(minHit,offPeak?"0.003":"0.006").add(amount(prompt-minHit,offPeak?"0.15":"0.3")).add(amount(output,offPeak?"0.6":"1.2"));
        return new Cost(offPeak?"OFF_PEAK":"PEAK_OR_HOLIDAY_OR_BOUNDARY",card.currency(),lower,upper);
    }
    private static boolean certainlyOffPeak(Instant start,Instant end) {
        if(start==null || end==null || end.isBefore(start) || Duration.between(start,end).toHours()>1)return false;
        var a=start.atZone(ZoneOffset.UTC);var b=end.atZone(ZoneOffset.UTC);
        if(!a.toLocalDate().equals(b.toLocalDate()))return false;
        if(a.getDayOfWeek()==DayOfWeek.SATURDAY || a.getDayOfWeek()==DayOfWeek.SUNDAY)return true;
        int first=a.getHour()*60+a.getMinute(),last=b.getHour()*60+b.getMinute();
        return !(first<240 && last>=60 || first<600 && last>=360);
    }
    private static BigDecimal amount(long tokens,String rate){return BigDecimal.valueOf(tokens).multiply(new BigDecimal(rate)).divide(BigDecimal.valueOf(1000000),12,RoundingMode.HALF_UP);}
}
