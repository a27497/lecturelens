package com.example.courselingo.ai.llm;

public record LlmUsage(
    Integer promptTokens,
    Integer completionTokens,
    Integer totalTokens,
    @com.fasterxml.jackson.annotation.JsonInclude(com.fasterxml.jackson.annotation.JsonInclude.Include.NON_NULL) Integer reasoningTokens,
    @com.fasterxml.jackson.annotation.JsonInclude(com.fasterxml.jackson.annotation.JsonInclude.Include.NON_NULL) Integer cacheHitTokens,
    @com.fasterxml.jackson.annotation.JsonInclude(com.fasterxml.jackson.annotation.JsonInclude.Include.NON_NULL) Integer cacheMissTokens
) {
    public LlmUsage(Integer promptTokens,Integer completionTokens,Integer totalTokens){this(promptTokens,completionTokens,totalTokens,null,null,null);}
    public static LlmUsage parse(com.fasterxml.jackson.databind.JsonNode root) {
        var n=root==null?new com.fasterxml.jackson.databind.ObjectMapper().createObjectNode():root.path("usage");
        Integer prompt=number(n,"prompt_tokens");if(prompt==null)prompt=number(n,"input_tokens");
        Integer completion=number(n,"completion_tokens");if(completion==null)completion=number(n,"output_tokens");
        return new LlmUsage(prompt,completion,number(n,"total_tokens"),number(n.path("completion_tokens_details"),"reasoning_tokens"),
            number(n,"prompt_cache_hit_tokens"),number(n,"prompt_cache_miss_tokens"));
    }
    private static Integer number(com.fasterxml.jackson.databind.JsonNode node,String field){var n=node.path(field);return n.isIntegralNumber()&&n.canConvertToInt()&&n.intValue()>=0?n.intValue():null;}
}
