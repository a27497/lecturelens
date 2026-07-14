package com.example.courselingo.learning.domain;

import com.baomidou.mybatisplus.annotation.IdType;
import com.baomidou.mybatisplus.annotation.TableField;
import com.baomidou.mybatisplus.annotation.TableId;
import com.baomidou.mybatisplus.annotation.TableName;
import java.time.LocalDateTime;

@TableName("learning_package")
public class LearningPackage {

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

    @TableField("title")
    private String title;

    @TableField("summary")
    private String summary;

    @TableField("key_points_json")
    private String keyPointsJson;

    @TableField("glossary_json")
    private String glossaryJson;

    @TableField("qa_json")
    private String qaJson;

    @TableField("provider")
    private String provider;

    @TableField("schema_version")
    private String schemaVersion;

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

    public String getTitle() {
        return title;
    }

    public void setTitle(String title) {
        this.title = title;
    }

    public String getSummary() {
        return summary;
    }

    public void setSummary(String summary) {
        this.summary = summary;
    }

    public String getKeyPointsJson() {
        return keyPointsJson;
    }

    public void setKeyPointsJson(String keyPointsJson) {
        this.keyPointsJson = keyPointsJson;
    }

    public String getGlossaryJson() {
        return glossaryJson;
    }

    public void setGlossaryJson(String glossaryJson) {
        this.glossaryJson = glossaryJson;
    }

    public String getQaJson() {
        return qaJson;
    }

    public void setQaJson(String qaJson) {
        this.qaJson = qaJson;
    }

    public String getProvider() {
        return provider;
    }

    public void setProvider(String provider) {
        this.provider = provider;
    }

    public String getSchemaVersion() {
        return schemaVersion;
    }

    public void setSchemaVersion(String schemaVersion) {
        this.schemaVersion = schemaVersion;
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
