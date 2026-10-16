package com.example.courselingo.task.service;

/** Propagated explicitly to pipeline child workers; never inferred from the current DB lease. */
public final class PipelineExecutionScope implements AutoCloseable {
    private static final ThreadLocal<PipelineExecutionGuard.Identity> ACTIVE=new ThreadLocal<>();
    private final PipelineExecutionGuard.Identity previous;
    private PipelineExecutionScope(PipelineExecutionGuard.Identity identity){previous=ACTIVE.get();if(identity==null)ACTIVE.remove();else ACTIVE.set(identity);}
    public static PipelineExecutionScope open(String task,long user,String event,long epoch){return new PipelineExecutionScope(new PipelineExecutionGuard.Identity(task,user,event,epoch));}
    public static PipelineExecutionScope clear(){return new PipelineExecutionScope(null);}
    public static PipelineExecutionGuard.Identity current(){return ACTIVE.get();}
    public static PipelineExecutionScope restore(PipelineExecutionGuard.Identity identity){return new PipelineExecutionScope(identity);}
    @Override public void close(){if(previous==null)ACTIVE.remove();else ACTIVE.set(previous);}
}
