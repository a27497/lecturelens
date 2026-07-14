package com.example.courselingo.vision.ocr;

import com.baomidou.mybatisplus.annotation.IdType;
import com.baomidou.mybatisplus.annotation.TableId;
import com.baomidou.mybatisplus.annotation.TableName;
import java.time.LocalDateTime;

@TableName("video_keyframe_ocr")
public class VideoKeyframeOcr {

    @TableId(type = IdType.AUTO)
    private Long id;
    private String taskId;
    private Long userId;
    private Long keyframeId;
    private Long timestampMillis;
    private String provider;
    private String languageHint;
    private String ocrText;
    private Integer textLength;
    private Boolean textTruncated;
    private Double confidence;
    private String status;
    private String errorCode;
    private String errorMessage;
    private Long durationMillis;
    private LocalDateTime createdAt;
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

    public Long getKeyframeId() {
        return keyframeId;
    }

    public void setKeyframeId(Long keyframeId) {
        this.keyframeId = keyframeId;
    }

    public Long getTimestampMillis() {
        return timestampMillis;
    }

    public void setTimestampMillis(Long timestampMillis) {
        this.timestampMillis = timestampMillis;
    }

    public String getProvider() {
        return provider;
    }

    public void setProvider(String provider) {
        this.provider = provider;
    }

    public String getLanguageHint() {
        return languageHint;
    }

    public void setLanguageHint(String languageHint) {
        this.languageHint = languageHint;
    }

    public String getOcrText() {
        return ocrText;
    }

    public void setOcrText(String ocrText) {
        this.ocrText = ocrText;
    }

    public Integer getTextLength() {
        return textLength;
    }

    public void setTextLength(Integer textLength) {
        this.textLength = textLength;
    }

    public Boolean getTextTruncated() {
        return textTruncated;
    }

    public void setTextTruncated(Boolean textTruncated) {
        this.textTruncated = textTruncated;
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

    public String getErrorCode() {
        return errorCode;
    }

    public void setErrorCode(String errorCode) {
        this.errorCode = errorCode;
    }

    public String getErrorMessage() {
        return errorMessage;
    }

    public void setErrorMessage(String errorMessage) {
        this.errorMessage = errorMessage;
    }

    public Long getDurationMillis() {
        return durationMillis;
    }

    public void setDurationMillis(Long durationMillis) {
        this.durationMillis = durationMillis;
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

    @Override
    public String toString() {
        return "VideoKeyframeOcr{"
            + "id=" + id
            + ", taskId='" + taskId + '\''
            + ", userId=" + userId
            + ", keyframeId=" + keyframeId
            + ", timestampMillis=" + timestampMillis
            + ", provider='" + provider + '\''
            + ", languageHint='" + languageHint + '\''
            + ", textLength=" + textLength
            + ", textTruncated=" + textTruncated
            + ", confidence=" + confidence
            + ", status='" + status + '\''
            + ", errorCode='" + errorCode + '\''
            + '}';
    }
}
