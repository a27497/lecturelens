package com.example.courselingo.task.entity;

import com.baomidou.mybatisplus.annotation.IdType;
import com.baomidou.mybatisplus.annotation.TableField;
import com.baomidou.mybatisplus.annotation.TableId;
import com.baomidou.mybatisplus.annotation.TableName;
import java.time.LocalDateTime;

@TableName("analysis_task")
public class AnalysisTask {

    @TableId(value = "id", type = IdType.INPUT)
    private String id;

    @TableField("user_id")
    private Long userId;

    @TableField("upload_id")
    private String uploadId;

    @TableField("target_language")
    private String targetLanguage;

    @TableField("status")
    private String status;

    @TableField("progress_percent")
    private Integer progressPercent;

    @TableField("current_stage")
    private String currentStage;

    @TableField("error_code")
    private String errorCode;

    @TableField("error_message")
    private String errorMessage;

    @TableField("retry_count")
    private Integer retryCount;

    @TableField("max_retry_count")
    private Integer maxRetryCount;

    @TableField("started_at")
    private LocalDateTime startedAt;

    @TableField("finished_at")
    private LocalDateTime finishedAt;

    @TableField("deleted_at")
    private LocalDateTime deletedAt;

    @TableField("created_at")
    private LocalDateTime createdAt;

    @TableField("updated_at")
    private LocalDateTime updatedAt;

    public String getId() {
        return id;
    }

    public void setId(String id) {
        this.id = id;
    }

    public Long getUserId() {
        return userId;
    }

    public void setUserId(Long userId) {
        this.userId = userId;
    }

    public String getUploadId() {
        return uploadId;
    }

    public void setUploadId(String uploadId) {
        this.uploadId = uploadId;
    }

    public String getTargetLanguage() {
        return targetLanguage;
    }

    public void setTargetLanguage(String targetLanguage) {
        this.targetLanguage = targetLanguage;
    }

    public String getStatus() {
        return status;
    }

    public void setStatus(String status) {
        this.status = status;
    }

    public Integer getProgressPercent() {
        return progressPercent;
    }

    public void setProgressPercent(Integer progressPercent) {
        this.progressPercent = progressPercent;
    }

    public String getCurrentStage() {
        return currentStage;
    }

    public void setCurrentStage(String currentStage) {
        this.currentStage = currentStage;
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

    public Integer getRetryCount() {
        return retryCount;
    }

    public void setRetryCount(Integer retryCount) {
        this.retryCount = retryCount;
    }

    public Integer getMaxRetryCount() {
        return maxRetryCount;
    }

    public void setMaxRetryCount(Integer maxRetryCount) {
        this.maxRetryCount = maxRetryCount;
    }

    public LocalDateTime getStartedAt() {
        return startedAt;
    }

    public void setStartedAt(LocalDateTime startedAt) {
        this.startedAt = startedAt;
    }

    public LocalDateTime getFinishedAt() {
        return finishedAt;
    }

    public void setFinishedAt(LocalDateTime finishedAt) {
        this.finishedAt = finishedAt;
    }

    public LocalDateTime getCreatedAt() {
        return createdAt;
    }

    public LocalDateTime getDeletedAt() {
        return deletedAt;
    }

    public void setDeletedAt(LocalDateTime deletedAt) {
        this.deletedAt = deletedAt;
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
