package com.example.courselingo.subtitle.domain;

import com.baomidou.mybatisplus.annotation.IdType;
import com.baomidou.mybatisplus.annotation.TableField;
import com.baomidou.mybatisplus.annotation.TableId;
import com.baomidou.mybatisplus.annotation.TableName;
import java.time.LocalDateTime;

@TableName("task_full_text_result")
public class TaskFullTextResult {

    @TableId(value = "id", type = IdType.AUTO)
    private Long id;

    @TableField("task_id")
    private String taskId;

    @TableField("user_id")
    private Long userId;

    @TableField("source_language")
    private String sourceLanguage;

    @TableField("target_language")
    private String targetLanguage;

    @TableField("source_full_text")
    private String sourceFullText;

    @TableField("translated_full_text")
    private String translatedFullText;

    @TableField("provider")
    private String provider;

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

    public String getSourceLanguage() {
        return sourceLanguage;
    }

    public void setSourceLanguage(String sourceLanguage) {
        this.sourceLanguage = sourceLanguage;
    }

    public String getTargetLanguage() {
        return targetLanguage;
    }

    public void setTargetLanguage(String targetLanguage) {
        this.targetLanguage = targetLanguage;
    }

    public String getSourceFullText() {
        return sourceFullText;
    }

    public void setSourceFullText(String sourceFullText) {
        this.sourceFullText = sourceFullText;
    }

    public String getTranslatedFullText() {
        return translatedFullText;
    }

    public void setTranslatedFullText(String translatedFullText) {
        this.translatedFullText = translatedFullText;
    }

    public String getProvider() {
        return provider;
    }

    public void setProvider(String provider) {
        this.provider = provider;
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
