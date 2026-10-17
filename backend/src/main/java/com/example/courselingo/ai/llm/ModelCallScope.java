package com.example.courselingo.ai.llm;

import com.example.courselingo.systemmodel.SystemModelExecutionRef;

/** Safe identity propagated by each frozen adapter to its individual physical requests. */
public final class ModelCallScope implements AutoCloseable {
    public record Context(SystemModelExecutionRef execution,String feature,String model,String translationAttemptId,String executionEvent,
                          Long audioStartMillis,Long audioEndMillis,String timingSource,String audioPlanHash) {
        public Context(SystemModelExecutionRef execution,String feature,String model,String translationAttemptId,String executionEvent,
            Long audioStartMillis,Long audioEndMillis,String timingSource){this(execution,feature,model,translationAttemptId,executionEvent,audioStartMillis,audioEndMillis,timingSource,null);}
    }
    private static final ThreadLocal<ModelCallScope> ACTIVE=new ThreadLocal<>();
    private final ModelCallScope previous;
    private final Context context;
    private String callId;
    private ModelCallScope(Context context){previous=ACTIVE.get();this.context=context;if(context==null)ACTIVE.remove();else ACTIVE.set(this);}
    public static ModelCallScope open(Context context){return new ModelCallScope(context);}
    public static Context current(){return ACTIVE.get()==null?null:ACTIVE.get().context;}
    public static void recorded(String id){if(ACTIVE.get()!=null)ACTIVE.get().callId=id;}
    public String lastCallId(){return callId;}
    @Override public void close(){if(previous==null)ACTIVE.remove();else ACTIVE.set(previous);}
}
