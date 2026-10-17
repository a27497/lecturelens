package com.example.courselingo.subtitle.pipeline;

import com.example.courselingo.ai.asr.TranscribedSegment;
import com.example.courselingo.ai.asr.TranscriptTimingSource;
import com.example.courselingo.ai.llm.TranslationFailure;
import com.example.courselingo.media.SilenceSegmentationPolicy;
import com.example.courselingo.subtitle.dto.AlignedParagraphView;
import com.example.courselingo.subtitle.service.SaveTranscriptionSegmentsCommand;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import java.util.*;

@Service
public class TranscriptParagraphService {
    public record Paragraph(List<TranscribedSegment> members,String shortReason) {
        public Paragraph {members=List.copyOf(members);}
    }
    private final JdbcTemplate jdbc;
    private final PipelinePolicyService policies;
    private static final ObjectMapper JSON=new ObjectMapper();
    public TranscriptParagraphService(JdbcTemplate jdbc,PipelinePolicyService policies) {this.jdbc=jdbc;this.policies=policies;}

    @Transactional
    public void replace(SaveTranscriptionSegmentsCommand command) {
        var frozen=policies.find(command.taskId(),command.userId());
        if(frozen.isEmpty() || frozen.get().policy().silence()==null) return;
        var segments=command.result().segments();
        if(segments.isEmpty() || segments.stream().anyMatch(s->s.timingSource()==TranscriptTimingSource.ESTIMATED
            || s.endMillis()>command.result().audioDurationMillis())) throw changed();
        var paragraphs=group(segments,frozen.get().policy().silence());
        var owner=jdbc.queryForList("SELECT id FROM analysis_task WHERE id=? AND user_id=? AND deleted_at IS NULL AND status NOT IN ('FAILED','CANCELED') FOR UPDATE",command.taskId(),command.userId());
        if(owner.size()!=1) throw changed();
        clear(command.taskId(),command.userId());
        String fingerprint=fingerprint(segments);
        var metadata=command.result().metadata();
        var summary=new LinkedHashMap<String,Object>();
        for(String key:List.of("segmentationMode","silencePlanHash","asrPhysicalAttempts","silenceClipCount","detectedSilenceMillis","clipIntervals"))
            if(metadata.containsKey(key)) summary.put(key,metadata.get(key));
        Object hash=summary.get("silencePlanHash");
        if(!(hash instanceof String planHash) || !planHash.matches("[a-f0-9]{64}")) throw changed();
        jdbc.update("""
            INSERT INTO transcript_timing_plan(task_id,user_id,source_fingerprint,plan_hash,plan_json,asr_attempt_count,clip_count,detected_silence_millis)
            VALUES(?,?,?,?,?,?,?,?)
            """,command.taskId(),command.userId(),fingerprint,planHash,encode(summary),number(summary,"asrPhysicalAttempts"),
            number(summary,"silenceClipCount"),number(summary,"detectedSilenceMillis"));
        for(int index=0;index<paragraphs.size();index++) {
            var paragraph=paragraphs.get(index);var members=paragraph.members();String id=UUID.randomUUID().toString();
            jdbc.update("""
                INSERT INTO transcript_paragraph(id,task_id,user_id,source_fingerprint,paragraph_no,start_millis,end_millis,member_count,short_reason)
                VALUES(?,?,?,?,?,?,?,?,?)
                """,id,command.taskId(),command.userId(),fingerprint,index,members.getFirst().startMillis(),
                members.stream().mapToLong(TranscribedSegment::endMillis).max().orElseThrow(),members.size(),paragraph.shortReason());
            for(int order=0;order<members.size();order++) {
                var member=members.get(order);
                jdbc.update("""
                    INSERT INTO transcript_paragraph_member(paragraph_id,ordinal,task_id,user_id,source_segment_index,source_hash)
                    VALUES(?,?,?,?,?,?)
                    """,id,order,command.taskId(),command.userId(),member.index(),fingerprint(List.of(member)));
            }
        }
    }

    @Transactional
    public void clear(String task,long user) {
        jdbc.update("DELETE FROM transcript_paragraph WHERE task_id=? AND user_id=?",task,user);
        jdbc.update("DELETE FROM transcript_timing_plan WHERE task_id=? AND user_id=?",task,user);
        jdbc.update("DELETE FROM transcript_alignment_publication WHERE task_id=? AND user_id=?",task,user);
    }

    public List<AlignedParagraphView> aligned(String task,long user,String language) {
        if(jdbc.queryForObject("""
            SELECT COUNT(*) FROM transcript_alignment_publication a JOIN transcript_timing_plan p
            ON a.task_id=p.task_id AND a.user_id=p.user_id AND a.source_fingerprint=p.source_fingerprint
            WHERE a.task_id=? AND a.user_id=? AND a.target_language=?
            """,Integer.class,task,user,language)==0) return List.of();
        return alignedRows(task,user,language);
    }

    /** Called in the same transaction as final subtitle/full-text publication. */
    public void publish(String task,long user,String language,String expectedSource) {
        var plans=jdbc.queryForList("SELECT source_fingerprint FROM transcript_timing_plan WHERE task_id=? AND user_id=?",task,user);
        if(plans.isEmpty()) return;
        if(!Objects.equals(plans.getFirst().get("source_fingerprint"),expectedSource)) throw changed();
        if(alignedRows(task,user,language).isEmpty()) throw changed();
        long version=policies.find(task,user).orElseThrow(TranscriptParagraphService::changed).execution().configVersion();
        jdbc.update("""
            INSERT INTO transcript_alignment_publication(task_id,user_id,target_language,source_fingerprint,config_version)
            VALUES(?,?,?,?,?) ON DUPLICATE KEY UPDATE source_fingerprint=VALUES(source_fingerprint),config_version=VALUES(config_version)
            """,task,user,language,expectedSource,version);
    }

    private List<AlignedParagraphView> alignedRows(String task,long user,String language) {
        var paragraphs=jdbc.queryForList("""
            SELECT p.* FROM transcript_paragraph p JOIN analysis_task t ON t.id=p.task_id AND t.user_id=p.user_id
            WHERE p.task_id=? AND p.user_id=? AND t.deleted_at IS NULL ORDER BY p.paragraph_no
            """,task,user);
        var output=new ArrayList<AlignedParagraphView>();
        for(var paragraph:paragraphs) {
            var rows=jdbc.queryForList("""
                SELECT s.*,m.source_hash,x.translated_text FROM transcript_paragraph_member m
                JOIN subtitle_segment s ON s.task_id=m.task_id AND s.user_id=m.user_id AND s.segment_index=m.source_segment_index
                LEFT JOIN subtitle_translation_segment x ON x.task_id=s.task_id AND x.user_id=s.user_id AND x.segment_index=s.segment_index AND x.target_language=?
                WHERE m.paragraph_id=? AND m.task_id=? AND m.user_id=? ORDER BY m.ordinal
                """,language,paragraph.get("id"),task,user);
            if(rows.isEmpty() || rows.size()!=((Number)paragraph.get("member_count")).intValue()) throw changed();
            var originals=new ArrayList<String>();var translations=new ArrayList<String>();
            var indexes=new ArrayList<Integer>();var provenance=new LinkedHashSet<String>();
            for(var row:rows) {
                var atom=new TranscribedSegment(((Number)row.get("segment_index")).intValue(),((Number)row.get("start_millis")).longValue(),
                    ((Number)row.get("end_millis")).longValue(),(String)row.get("text"),
                    TranscriptTimingSource.valueOf((String)row.get("timing_source")),(String)row.get("timing_reason"));
                if(!fingerprint(List.of(atom)).equals(row.get("source_hash"))) throw changed();
                if(!(row.get("translated_text") instanceof String text) || text.isBlank()) return List.of();
                originals.add(atom.text());translations.add(text);indexes.add(atom.index());provenance.add(atom.timingSource().name());
            }
            long start=((Number)paragraph.get("start_millis")).longValue(),end=((Number)paragraph.get("end_millis")).longValue();
            output.add(new AlignedParagraphView((String)paragraph.get("id"),((Number)paragraph.get("paragraph_no")).intValue(),start,end,
                Math.floorDiv(start,1000),Math.floorDiv(end+999,1000),String.join("\n",originals),String.join("\n",translations),
                indexes,List.copyOf(provenance),(String)paragraph.get("short_reason")));
        }
        return List.copyOf(output);
    }

    public static List<Paragraph> group(List<TranscribedSegment> source,SilenceSegmentationPolicy policy) {
        var output=new ArrayList<Paragraph>();var current=new ArrayList<TranscribedSegment>();
        long end=0;int previous=-1;
        for(var atom:source) {
            if(atom.index()<=previous || atom.startMillis()<0 || atom.endMillis()<=atom.startMillis()
                || atom.endMillis()-atom.startMillis()>policy.maxMillis() || !current.isEmpty() && atom.startMillis()<current.getLast().startMillis()) throw changed();
            if(!current.isEmpty()) {
                long span=end-current.getFirst().startMillis(),gap=atom.startMillis()-end;
                if(atom.endMillis()-current.getFirst().startMillis()>policy.maxMillis()
                    || gap>=policy.pauseMillis() && span>=policy.minMillis() || gap>=policy.minMillis()) {
                    output.add(paragraph(current,policy,false));current=new ArrayList<>();
                }
            }
            current.add(atom);end=Math.max(end,atom.endMillis());previous=atom.index();
        }
        if(!current.isEmpty()) output.add(paragraph(current,policy,true));
        return List.copyOf(output);
    }
    private static Paragraph paragraph(List<TranscribedSegment> atoms,SilenceSegmentationPolicy policy,boolean last) {
        long length=atoms.stream().mapToLong(TranscribedSegment::endMillis).max().orElseThrow()-atoms.getFirst().startMillis();
        String reason=atoms.stream().map(TranscribedSegment::timingReason).filter(Objects::nonNull).findFirst().orElse(null);
        if(length>=policy.minMillis()) reason=null;
        else if(reason==null || "MAX_DURATION".equals(reason)) reason=last?"TRAILING_FRAGMENT":"SHORT_SPEECH_ISLAND";
        return new Paragraph(atoms,reason);
    }
    public static String fingerprint(List<TranscribedSegment> segments) {return PipelinePolicyService.hash(encode(segments));}
    public static String fingerprintSource(List<com.example.courselingo.subtitle.domain.SubtitleSegment> source) {
        return fingerprint(source.stream().map(s->new TranscribedSegment(s.getSegmentIndex(),s.getStartMillis(),s.getEndMillis(),s.getText(),
            TranscriptTimingSource.valueOf(s.getTimingSource()),s.getTimingReason())).toList());
    }
    private static long number(Map<String,Object> data,String key) {
        if(!(data.get(key) instanceof Number value) || value.longValue()<0) throw changed();
        return value.longValue();
    }
    private static String encode(Object value) {
        try{return JSON.writeValueAsString(value);}catch(Exception ignored){throw changed();}
    }
    private static TranslationFailure changed(){return TranslationFailure.of(TranslationFailure.Reason.SOURCE_CHANGED);}
}
