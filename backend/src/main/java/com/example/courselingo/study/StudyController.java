package com.example.courselingo.study;

import com.example.courselingo.auth.service.CurrentUserService;
import com.example.courselingo.common.error.ErrorCode;
import com.example.courselingo.common.exception.BusinessException;
import com.example.courselingo.common.response.ApiResponse;
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import jakarta.servlet.http.HttpServletRequest;
import java.util.*;
import java.util.concurrent.atomic.AtomicBoolean;
import java.util.concurrent.atomic.AtomicInteger;
import org.springframework.web.bind.annotation.*;
import org.springframework.web.servlet.mvc.method.annotation.SseEmitter;

@RestController
public class StudyController {
    private final CurrentUserService users;
    private final StudyProperties properties;
    private final StudyEvidenceAuthority authority;
    private final StudyTransport transport;
    private final ObjectMapper json;
    private final AtomicInteger streams=new AtomicInteger();
    public StudyController(CurrentUserService users,StudyProperties properties,StudyEvidenceAuthority authority,StudyTransport transport,ObjectMapper json) {
        this.users=users; this.properties=properties; this.authority=authority; this.transport=transport; this.json=json;
    }
    private void enabled() { if(!properties.isEnabled()) throw new BusinessException(ErrorCode.STUDY_UNAVAILABLE); }

    @GetMapping("/api/tasks/{taskId}/study/status")
    public ApiResponse<Map<String,Object>> status(@PathVariable String taskId,@RequestHeader(value="Authorization",required=false) String auth) {
        long owner=users.currentUser(auth).userId();
        long revision=authority.current(taskId,owner,false);
        return ApiResponse.success(Map.of("enabled",properties.isEnabled(),"revision",revision));
    }

    @PostMapping("/api/tasks/{taskId}/study/command")
    public ApiResponse<JsonNode> command(@PathVariable String taskId,@RequestHeader(value="Authorization",required=false) String auth,@RequestBody Command command) {
        enabled();
        long owner=users.currentUser(auth).userId();
        return ApiResponse.success(invoke(taskId,owner,command));
    }

    private JsonNode invoke(String taskId,long owner,Command command) {
        if(command==null || command.operation()==null || !Set.of("CREATE_SESSION","LIST","RUNS","START","READ","CANCEL","EVENTS","ANSWERS","SAVE_ATTEMPT","ATTEMPT_HISTORY","START_FEEDBACK","SAVE_FEEDBACK_NOTE","FEEDBACK_NOTES").contains(command.operation())
                || (command.goal()!=null && (command.goal().isBlank() || command.goal().length()>1000))
                || command.after()<0) throw new BusinessException(ErrorCode.COMMON_BAD_REQUEST);
        for(String id:Arrays.asList(command.session_id(),command.run_id(),command.request_key(),command.artifact_id(),command.attempt_id(),command.feedback_id())) {
            if(id!=null && (id.isBlank() || id.length()>128)) throw new BusinessException(ErrorCode.COMMON_BAD_REQUEST);
        }
        if (Set.of("SAVE_ATTEMPT","ATTEMPT_HISTORY","START_FEEDBACK").contains(command.operation()) &&
                (command.session_id()==null || command.run_id()==null || command.artifact_id()==null ||
                 command.question_index()==null || command.question_index()<0 || command.question_index()>1))
            throw new BusinessException(ErrorCode.COMMON_BAD_REQUEST);
        if (command.operation().equals("SAVE_ATTEMPT") && (command.request_key()==null ||
                command.expected_version()==null || command.expected_version()<0 || command.answer_text()==null ||
                command.answer_text().isBlank() || command.answer_text().length()>4000))
            throw new BusinessException(ErrorCode.COMMON_BAD_REQUEST);
        if (command.before_version()!=null && command.before_version()<1) throw new BusinessException(ErrorCode.COMMON_BAD_REQUEST);
        if (command.operation().equals("START_FEEDBACK") && (command.request_key()==null || command.attempt_id()==null))
            throw new BusinessException(ErrorCode.COMMON_BAD_REQUEST);
        if (Set.of("SAVE_FEEDBACK_NOTE","FEEDBACK_NOTES").contains(command.operation()) &&
                (command.session_id()==null || command.run_id()==null || command.feedback_id()==null))
            throw new BusinessException(ErrorCode.COMMON_BAD_REQUEST);
        if (command.operation().equals("SAVE_FEEDBACK_NOTE") && (command.request_key()==null || command.expected_version()==null ||
                command.expected_version()<0 || command.note_text()==null || command.note_text().isBlank() || command.note_text().length()>2000 ||
                command.disposition()==null || !Set.of("disputed","acknowledged").contains(command.disposition())))
            throw new BusinessException(ErrorCode.COMMON_BAD_REQUEST);
        long revision=authority.current(taskId,owner,Set.of("CREATE_SESSION","START","ANSWERS","SAVE_ATTEMPT","START_FEEDBACK").contains(command.operation()));
        Map<String,Object> payload=new LinkedHashMap<>();
        payload.put("owner_id",owner); payload.put("course_id",taskId); payload.put("revision",revision); payload.put("operation",command.operation());
        if(command.session_id()!=null) payload.put("session_id",command.session_id());
        if(command.run_id()!=null) payload.put("run_id",command.run_id());
        if(command.request_key()!=null) payload.put("request_key",command.request_key());
        if(command.goal()!=null) payload.put("goal",command.goal());
        if(command.artifact_id()!=null) payload.put("artifact_id",command.artifact_id());
        if(command.question_index()!=null) payload.put("question_index",command.question_index());
        if(command.answer_text()!=null) payload.put("answer_text",command.answer_text());
        if(command.expected_version()!=null) payload.put("expected_version",command.expected_version());
        if(command.before_version()!=null) payload.put("before_version",command.before_version());
        if(command.attempt_id()!=null) payload.put("attempt_id",command.attempt_id());
        if(command.feedback_id()!=null) payload.put("feedback_id",command.feedback_id());
        if(command.note_text()!=null) payload.put("note_text",command.note_text());
        if(command.disposition()!=null) payload.put("disposition",command.disposition());
        payload.put("after",command.after());
        var result=transport.command(payload);
        if(authority.current(taskId,owner,false)!=revision) throw new BusinessException(ErrorCode.STUDY_CONFLICT);
        return result;
    }

    @GetMapping(value="/api/tasks/{taskId}/study/runs/{runId}/events",produces="text/event-stream")
    public SseEmitter events(@PathVariable String taskId,@PathVariable String runId,@RequestParam String sessionId,
                            @RequestParam(defaultValue="0") long after,@RequestHeader(value="Last-Event-ID",required=false) Long lastEventId,
                            @RequestHeader(value="Authorization",required=false) String auth) {
        enabled();
        long owner=users.currentUser(auth).userId();
        long cursor=Math.max(after,lastEventId==null?0:lastEventId);
        var initial=invoke(taskId,owner,new Command("EVENTS",sessionId,runId,null,null,cursor));
        if(streams.incrementAndGet()>64) { streams.decrementAndGet(); throw new BusinessException(ErrorCode.STUDY_UNAVAILABLE); }
        var emitter=new SseEmitter(30_000L);
        var closed=new AtomicBoolean();
        Runnable release=()->{if(closed.compareAndSet(false,true)) streams.decrementAndGet();};
        emitter.onCompletion(release); emitter.onTimeout(release); emitter.onError(e->release.run());
        Thread.ofVirtual().name("study-events").start(()->{
            long next=cursor;
            long deadline=System.nanoTime()+25_000_000_000L;
            JsonNode batch=initial;
            try {
                while(!closed.get() && System.nanoTime()<deadline) {
                    for(var event:batch.path("events")) {
                        next=event.path("sequence").asLong();
                        emitter.send(SseEmitter.event().id(Long.toString(next)).name(event.path("event_type").asText()).data(event));
                    }
                    if(Set.of("succeeded","failed","cancelled","budget_exceeded").contains(batch.path("status").asText())) break;
                    emitter.send(SseEmitter.event().comment("heartbeat"));
                    Thread.sleep(1000);
                    long checkedOwner=users.currentUser(auth).userId();
                    batch=invoke(taskId,checkedOwner,new Command("EVENTS",sessionId,runId,null,null,next));
                }
                emitter.complete();
            } catch(Exception error) { emitter.completeWithError(error); }
            finally { release.run(); }
        });
        return emitter;
    }

    @PostMapping("/internal/v1/study/evidence")
    public ApiResponse<Map<String,Object>> evidence(HttpServletRequest request) throws Exception {
        enabled();
        byte[] body=request.getInputStream().readNBytes(65537);
        if(body.length>65536) throw new BusinessException(ErrorCode.COMMON_BAD_REQUEST);
        transport.verify("/internal/v1/study/evidence",request.getHeader("X-LectureLens-Timestamp"),request.getHeader("X-LectureLens-Signature"),body);
        StudyEvidenceAuthority.Request payload;
        try { payload=json.readValue(body,StudyEvidenceAuthority.Request.class); }
        catch(Exception e) { throw new BusinessException(ErrorCode.COMMON_BAD_REQUEST); }
        return ApiResponse.success(authority.execute(payload));
    }
    public record Command(String operation,String session_id,String run_id,String request_key,String goal,long after,
                          String artifact_id,Integer question_index,String answer_text,Integer expected_version,Integer before_version,
                          String attempt_id,String feedback_id,String note_text,String disposition) {
        public Command(String operation,String session_id,String run_id,String request_key,String goal,long after) {
            this(operation,session_id,run_id,request_key,goal,after,null,null,null,null,null);
        }
        public Command(String operation,String session_id,String run_id,String request_key,String goal,long after,
                       String artifact_id,Integer question_index,String answer_text,Integer expected_version,Integer before_version) {
            this(operation,session_id,run_id,request_key,goal,after,artifact_id,question_index,answer_text,expected_version,before_version,null,null,null,null);
        }
    }
}
