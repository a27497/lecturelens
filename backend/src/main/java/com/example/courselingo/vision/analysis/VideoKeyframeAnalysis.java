package com.example.courselingo.vision.analysis;

import com.baomidou.mybatisplus.annotation.IdType;
import com.baomidou.mybatisplus.annotation.TableId;
import com.baomidou.mybatisplus.annotation.TableName;
import java.time.LocalDateTime;

@TableName("video_keyframe_analysis")
public class VideoKeyframeAnalysis {

    @TableId(type = IdType.AUTO)
    private Long id;
    private String taskId;
    private Long userId;
    private Long keyframeId;
    private Long timestampMillis;
    private String provider;
    private String model;
    private String screenType;
    private String visualSummary;
    private String detectedElementsJson;
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

    public String getModel() {
        return model;
    }

    public void setModel(String model) {
        this.model = model;
    }

    public String getScreenType() {
        return screenType;
    }

    public void setScreenType(String screenType) {
        this.screenType = screenType;
    }

    public String getVisualSummary() {
        return visualSummary;
    }

    public void setVisualSummary(String visualSummary) {
        this.visualSummary = visualSummary;
    }

    public String getDetectedElementsJson() {
        return detectedElementsJson;
    }

    public void setDetectedElementsJson(String detectedElementsJson) {
        this.detectedElementsJson = detectedElementsJson;
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
        return "VideoKeyframeAnalysis{"
            + "id=" + id
            + ", taskId='" + taskId + '\''
            + ", userId=" + userId
            + ", keyframeId=" + keyframeId
            + ", timestampMillis=" + timestampMillis
            + ", provider='" + provider + '\''
            + ", model='" + model + '\''
            + ", screenType='" + screenType + '\''
            + ", status='" + status + '\''
            + ", errorCode='" + errorCode + '\''
            + '}';
    }
}
