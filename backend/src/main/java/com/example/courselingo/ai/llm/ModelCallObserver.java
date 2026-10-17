package com.example.courselingo.ai.llm;

/** Receives only safe request summaries, typed usage and an optional redacted private error excerpt. */
public interface ModelCallObserver {
    record RequestSummary(String address,String bodyHash,long bodyBytes,String optionsJson) {}
    record Completion(Integer httpStatus,LlmUsage usage,String finishReason,String errorCategory,long durationMillis,
                      String privateErrorExcerpt,Integer responseChars,boolean truncated,String responseModelHash,String providerFingerprintHash) {
        public Completion(Integer httpStatus,LlmUsage usage,String finishReason,String errorCategory,long durationMillis,String privateErrorExcerpt,Integer responseChars,boolean truncated) {
            this(httpStatus,usage,finishReason,errorCategory,durationMillis,privateErrorExcerpt,responseChars,truncated,null,null);
        }
        @Override public String toString(){return "ModelCallCompletion[private]";}
    }
    ModelCallObserver NOOP=new ModelCallObserver(){public String begin(ModelCallScope.Context c,RequestSummary s){return null;}public void complete(String id,Completion c){}};
    String begin(ModelCallScope.Context context,RequestSummary summary);
    void complete(String id,Completion completion);
    default void validation(String id,String category,String check) {}
}
