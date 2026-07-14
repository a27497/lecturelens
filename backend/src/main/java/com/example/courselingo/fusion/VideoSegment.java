package com.example.courselingo.fusion;

import com.baomidou.mybatisplus.annotation.IdType;
import com.baomidou.mybatisplus.annotation.TableField;
import com.baomidou.mybatisplus.annotation.TableId;
import com.baomidou.mybatisplus.annotation.TableName;
import java.time.LocalDateTime;

@TableName("video_segment")
public class VideoSegment {

    @TableId(value = "id", type = IdType.AUTO)
    private Long id;

    @TableField("task_id")
    private String taskId;

    @TableField("user_id")
    private Long userId;

    @TableField("segment_index")
    private Integer segmentIndex;

    @TableField("start_millis")
    private Long startMillis;

    @TableField("end_millis")
    private Long endMillis;

    @TableField("time_text")
    private String timeText;

    @TableField("asr_text")
    private String asrText;

    @TableField("ocr_text")
    private String ocrText;

    @TableField("visual_summary")
    private String visualSummary;

    @TableField("fused_summary")
    private String fusedSummary;

    @TableField("keywords_json")
    private String keywordsJson;

    @TableField("evidence_json")
    private String evidenceJson;

    @TableField("confidence")
    private Double confidence;

    @TableField("status")
    private String status;

    @TableField("created_at")
    private LocalDateTime createdAt;

    @TableField("updated_at")
    private LocalDateTime updatedAt;

    public Long getId() {
        return id;
    }

    public void setId(Long id) {
        this.id = id;
    }

    public String getTaskId() {
        return taskId;
    }

    public void setTaskId(String taskId) {
        this.taskId = taskId;
    }

    public Long getUserId() {
        return userId;
    }

    public void setUserId(Long userId) {
        this.userId = userId;
    }

    public Integer getSegmentIndex() {
        return segmentIndex;
    }

    public void setSegmentIndex(Integer segmentIndex) {
        this.segmentIndex = segmentIndex;
    }

    public Long getStartMillis() {
        return startMillis;
    }

    public void setStartMillis(Long startMillis) {
        this.startMillis = startMillis;
    }

    public Long getEndMillis() {
        return endMillis;
    }

    public void setEndMillis(Long endMillis) {
        this.endMillis = endMillis;
    }

    public String getTimeText() {
        return timeText;
    }

    public void setTimeText(String timeText) {
        this.timeText = timeText;
    }

    public String getAsrText() {
        return asrText;
    }

    public void setAsrText(String asrText) {
        this.asrText = asrText;
    }

    public String getOcrText() {
        return ocrText;
    }

    public void setOcrText(String ocrText) {
        this.ocrText = ocrText;
    }

    public String getVisualSummary() {
        return visualSummary;
    }

    public void setVisualSummary(String visualSummary) {
        this.visualSummary = visualSummary;
    }

    public String getFusedSummary() {
        return fusedSummary;
    }

    public void setFusedSummary(String fusedSummary) {
        this.fusedSummary = fusedSummary;
    }

    public String getKeywordsJson() {
        return keywordsJson;
    }

    public void setKeywordsJson(String keywordsJson) {
        this.keywordsJson = keywordsJson;
    }

    public String getEvidenceJson() {
        return evidenceJson;
    }

    public void setEvidenceJson(String evidenceJson) {
        this.evidenceJson = evidenceJson;
    }

    public Double getConfidence() {
        return confidence;
    }

    public void setConfidence(Double confidence) {
        this.confidence = confidence;
    }

    public String getStatus() {
        return status;
    }

    public void setStatus(String status) {
        this.status = status;
    }

    public LocalDateTime getCreatedAt() {
        return createdAt;
    }

    public void setCreatedAt(LocalDateTime createdAt) {
        this.createdAt = createdAt;
    }

    public LocalDateTime getUpdatedAt() {
        return updatedAt;
    }

    public void setUpdatedAt(LocalDateTime updatedAt) {
        this.updatedAt = updatedAt;
    }
}
