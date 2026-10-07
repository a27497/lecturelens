package com.example.courselingo.study;

import com.example.courselingo.common.error.ErrorCode;
import com.example.courselingo.common.exception.BusinessException;
import com.example.courselingo.evidence.CourseEvidence;
import com.example.courselingo.evidence.EvidenceChunkMatch;
import com.example.courselingo.evidence.CourseEvidenceService;
import com.example.courselingo.evidence.EvidenceIndexSynchronizer;
import com.example.courselingo.qa.service.DenseEvidenceClient;
import java.util.*;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;

@Service
public class StudyEvidenceAuthority {
    private final JdbcTemplate jdbc;
    private final CourseEvidenceService evidence;
    private final EvidenceIndexSynchronizer indexes;
    private final DenseEvidenceClient retrieval;
    public StudyEvidenceAuthority(JdbcTemplate jdbc,CourseEvidenceService evidence,EvidenceIndexSynchronizer indexes,DenseEvidenceClient retrieval) {
        this.jdbc=jdbc; this.evidence=evidence; this.indexes=indexes; this.retrieval=retrieval;
    }

    public long current(String taskId,Long owner,boolean ready) {
        var rows=jdbc.queryForList("SELECT content_revision,status FROM analysis_task WHERE id=? AND user_id=? AND deleted_at IS NULL",taskId,owner);
        if (rows.isEmpty()) throw new BusinessException(ErrorCode.TASK_NOT_FOUND);
        if (!"SUCCEEDED".equals(rows.getFirst().get("status"))) throw new BusinessException(ErrorCode.TASK_INVALID_STATUS);
        long revision=((Number)rows.getFirst().get("content_revision")).longValue();
        if (ready && !"READY".equals(indexes.status(taskId,owner).status())) throw new BusinessException(ErrorCode.STUDY_INDEX_NOT_READY);
        return revision;
    }

    public Map<String,Object> execute(Request request) {
        if (request.owner_id()==null || request.owner_id()<1 || request.course_id()==null || request.course_id().length()>128
                || request.revision()<0 || request.action()==null) throw new BusinessException(ErrorCode.COMMON_BAD_REQUEST);
        requireVersion(request);
        List<CourseEvidence> selected=List.of();
        var spans=new HashMap<String,Span>();
        var hashes=new HashMap<String,String>();
        var verified=new HashMap<String,EvidenceChunkMatch.Position>();
        if(request.hit_hashes()!=null) {
            if(request.hit_hashes().size()>8) throw new BusinessException(ErrorCode.COMMON_BAD_REQUEST);
            hashes.putAll(request.hit_hashes());
        }
        if(request.hit_spans()!=null) {
            if(request.hit_spans().size()>8) throw new BusinessException(ErrorCode.COMMON_BAD_REQUEST);
            spans.putAll(request.hit_spans());
        }
        if (!"CHECK".equals(request.action())) {
            var all=evidence.current(request.course_id(),request.owner_id()).stream().filter(CourseEvidence::retrievable).toList();
            for(var entry:spans.entrySet()) {
                var source=all.stream().filter(e->e.evidenceId().equals(entry.getKey())).findFirst()
                    .orElseThrow(()->new BusinessException(ErrorCode.STUDY_NOT_FOUND));
                validateSpan(source,entry.getValue());
            }
            for(var entry:hashes.entrySet()) {
                var source=all.stream().filter(e->e.evidenceId().equals(entry.getKey())).findFirst()
                    .orElseThrow(()->new BusinessException(ErrorCode.STUDY_NOT_FOUND));
                EvidenceChunkMatch.Position position;
                try { position=EvidenceChunkMatch.resolve(source.normalizedText(),entry.getValue()); }
                catch(IllegalArgumentException invalid) { throw new BusinessException(ErrorCode.COMMON_BAD_REQUEST); }
                var span=spans.get(entry.getKey());
                if(span!=null && (!Objects.equals(position.start(),span.start()) || !Objects.equals(position.end(),span.end())))
                    throw new BusinessException(ErrorCode.COMMON_BAD_REQUEST);
                verified.put(entry.getKey(),position);
                if(position.start()!=null) spans.put(entry.getKey(),new Span(position.start(),position.end()));
            }
            switch (request.action()) {
                case "SEARCH" -> {
                    if (request.query()==null || request.query().isBlank() || request.query().length()>500
                            || (request.start_ms()==null)!=(request.end_ms()==null)
                            || (request.start_ms()!=null && (request.start_ms()<0 || request.end_ms()<request.start_ms()))) {
                        throw new BusinessException(ErrorCode.COMMON_BAD_REQUEST);
                    }
                    var matches=retrieval.retrieveMatches(request.course_id(),request.owner_id(),all,request.query(),request.start_ms(),request.end_ms(),4);
                    for(var hit:matches) {
                        String id=hit.evidence().evidenceId();
                        if(hit.start()!=null) spans.put(id,new Span(hit.start(),hit.end()));
                        if(hit.hash()!=null) {
                            hashes.put(id,hit.hash());
                            verified.put(id,new EvidenceChunkMatch.Position(hit.start(),hit.end(),hit.text()));
                        }
                    }
                    var hits=matches.stream().map(DenseEvidenceClient.Match::evidence).toList();
                    selected=searchContext(all,hits,request.start_ms(),request.end_ms(),spans,hashes);
                }
                case "READ" -> {
                    var ids=request.evidence_ids();
                    if (ids==null || ids.size()>8 || ids.stream().anyMatch(Objects::isNull)) throw new BusinessException(ErrorCode.COMMON_BAD_REQUEST);
                    var wanted=new HashSet<>(ids);
                    selected=all.stream().filter(e->wanted.contains(e.evidenceId())).toList();
                    if (selected.size()!=wanted.size()) throw new BusinessException(ErrorCode.STUDY_NOT_FOUND);
                }
                case "WINDOW" -> {
                    if (request.evidence_id()==null) throw new BusinessException(ErrorCode.COMMON_BAD_REQUEST);
                    var anchor=all.stream().filter(e->e.evidenceId().equals(request.evidence_id())).findFirst()
                        .orElseThrow(()->new BusinessException(ErrorCode.STUDY_NOT_FOUND));
                    var timeline=timeline(all,anchor);
                    int position=timeline.indexOf(anchor);
                    selected=timeline.subList(Math.max(0,position-1),Math.min(timeline.size(),position+2));
                }
                default -> throw new BusinessException(ErrorCode.COMMON_BAD_REQUEST);
            }
        }
        requireVersion(request); // Source may change during retrieval; never return stale context.
        return Map.of("owner_id",request.owner_id(),"course_id",request.course_id(),"revision",request.revision(),
            "evidence",selected.stream().map(e->context(e,spans.get(e.evidenceId()),hashes.get(e.evidenceId()),verified.get(e.evidenceId()))).toList());
    }
    private static List<CourseEvidence> timeline(List<CourseEvidence> all,CourseEvidence anchor) {
        return all.stream().filter(e->e.sourceType().equals(anchor.sourceType()))
            .sorted(Comparator.comparingLong(CourseEvidence::startMs).thenComparingLong(CourseEvidence::endMs)).toList();
    }
    private static List<CourseEvidence> searchContext(List<CourseEvidence> all,List<CourseEvidence> hits,Long start,Long end,Map<String,Span> spans,Map<String,String> hashes) {
        var selected=new LinkedHashMap<String,CourseEvidence>();
        for(var hit:hits) {
            // Prefer the original speech when both it and its translation match. Translation
            // can omit a clause; the original also leaves room for the adjacent explanation.
            // Translation offsets address translated characters, never the source speech.
            var canonical="SUBTITLE_TRANSLATION".equals(hit.sourceType()) && !spans.containsKey(hit.evidenceId()) && !hashes.containsKey(hit.evidenceId()) ? all.stream()
                .filter(e->"SUBTITLE".equals(e.sourceType()) && e.startMs()==hit.startMs() && e.endMs()==hit.endMs())
                .findFirst().orElse(hit) : hit;
            selected.putIfAbsent(canonical.evidenceId(),canonical);
        }
        var anchors=List.copyOf(selected.values());
        // Keep ranked hits, then complete their immediate context without another model call.
        // Respect an explicitly requested time window and do not cross modality boundaries.
        for(int direction:new int[]{1,-1}) for(var anchor:anchors) {
            var timeline=timeline(all,anchor);
            int neighbor=timeline.indexOf(anchor)+direction;
            if(neighbor>=0 && neighbor<timeline.size() && selected.size()<8) {
                var item=timeline.get(neighbor);
                if(start==null || (item.endMs()>=start && item.startMs()<=end)) selected.putIfAbsent(item.evidenceId(),item);
            }
        }
        return List.copyOf(selected.values());
    }
    private void requireVersion(Request request) {
        if (current(request.course_id(),request.owner_id(),!"CHECK".equals(request.action()))!=request.revision()) throw new BusinessException(ErrorCode.STUDY_CONFLICT);
    }
    private static void validateSpan(CourseEvidence evidence,Span span) {
        int length=evidence.normalizedText().codePointCount(0,evidence.normalizedText().length());
        if(span==null || span.start()<0 || span.end()<=span.start() || span.end()>length || span.end()-span.start()>240)
            throw new BusinessException(ErrorCode.COMMON_BAD_REQUEST);
    }
    static Map<String,Object> context(CourseEvidence evidence,Span span) {
        return context(evidence,span,null,null);
    }
    private static Map<String,Object> context(CourseEvidence evidence,Span span,String hash,EvidenceChunkMatch.Position verified) {
        String text=evidence.normalizedText();int size=text.codePointCount(0,text.length());
        int start=0,end=Math.min(size,1200);
        if(span!=null) {
            validateSpan(evidence,span);
            start=Math.max(0,Math.min(span.start()-(1200-(span.end()-span.start()))/2,size-1200));
            end=Math.min(size,start+1200);
        }
        var result=new LinkedHashMap<String,Object>();
        result.put("evidence_id",evidence.evidenceId());result.put("text",text.substring(text.offsetByCodePoints(0,start),text.offsetByCodePoints(0,end)));
        result.put("start_ms",evidence.startMs());result.put("end_ms",evidence.endMs());result.put("source_type",evidence.sourceType());
        result.put("text_start",start);result.put("text_end",end);
        if(span!=null) {result.put("match_start",span.start());result.put("match_end",span.end());}
        if(hash!=null) {
            result.put("match_hash",hash);result.put("canonical_length",size);
            result.put("match_resolution",verified.start()==null?"AMBIGUOUS_TEXT":"UNIQUE_HASH");
            if(verified.start()==null) {
                result.put("text",verified.text());
                result.remove("text_start");result.remove("text_end");
            }
        }
        return result;
    }
    public record Span(int start,int end) { }
    public record Request(Long owner_id,String course_id,long revision,String action,String query,Long start_ms,Long end_ms,
                          List<String> evidence_ids,String evidence_id,Map<String,Span> hit_spans,Map<String,String> hit_hashes) {
        public Request(Long owner_id,String course_id,long revision,String action,String query,Long start_ms,Long end_ms,
                       List<String> evidence_ids,String evidence_id,Map<String,Span> hit_spans) {
            this(owner_id,course_id,revision,action,query,start_ms,end_ms,evidence_ids,evidence_id,hit_spans,null);
        }
        public Request(Long owner_id,String course_id,long revision,String action,String query,Long start_ms,Long end_ms,
                       List<String> evidence_ids,String evidence_id) {
            this(owner_id,course_id,revision,action,query,start_ms,end_ms,evidence_ids,evidence_id,null);
        }
    }
}
