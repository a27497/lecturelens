package com.example.courselingo.study;

import com.example.courselingo.common.error.ErrorCode;
import com.example.courselingo.common.exception.BusinessException;
import com.example.courselingo.evidence.CourseEvidence;
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
        if (!"CHECK".equals(request.action())) {
            var all=evidence.current(request.course_id(),request.owner_id()).stream().filter(CourseEvidence::retrievable).toList();
            switch (request.action()) {
                case "SEARCH" -> {
                    if (request.query()==null || request.query().isBlank() || request.query().length()>500
                            || (request.start_ms()==null)!=(request.end_ms()==null)
                            || (request.start_ms()!=null && (request.start_ms()<0 || request.end_ms()<request.start_ms()))) {
                        throw new BusinessException(ErrorCode.COMMON_BAD_REQUEST);
                    }
                    var hits=retrieval.retrieve(request.course_id(),request.owner_id(),all,request.query(),request.start_ms(),request.end_ms(),4);
                    selected=searchContext(all,hits,request.start_ms(),request.end_ms());
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
            "evidence",selected.stream().map(e->Map.of("evidence_id",e.evidenceId(),"text",bounded(e.normalizedText()),
                "start_ms",e.startMs(),"end_ms",e.endMs(),"source_type",e.sourceType())).toList());
    }
    private static List<CourseEvidence> timeline(List<CourseEvidence> all,CourseEvidence anchor) {
        return all.stream().filter(e->e.sourceType().equals(anchor.sourceType()))
            .sorted(Comparator.comparingLong(CourseEvidence::startMs).thenComparingLong(CourseEvidence::endMs)).toList();
    }
    private static List<CourseEvidence> searchContext(List<CourseEvidence> all,List<CourseEvidence> hits,Long start,Long end) {
        var selected=new LinkedHashMap<String,CourseEvidence>();
        for(var hit:hits) {
            // Prefer the original speech when both it and its translation match. Translation
            // can omit a clause; the original also leaves room for the adjacent explanation.
            var canonical="SUBTITLE_TRANSLATION".equals(hit.sourceType()) ? all.stream()
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
    private static String bounded(String text) { return text.length()>1200 ? text.substring(0,1200) : text; }
    public record Request(Long owner_id,String course_id,long revision,String action,String query,Long start_ms,Long end_ms,
                          List<String> evidence_ids,String evidence_id) { }
}
