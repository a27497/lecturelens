package com.example.courselingo.vision.keyframe;

import com.baomidou.mybatisplus.annotation.IdType;
import com.baomidou.mybatisplus.annotation.TableField;
import com.baomidou.mybatisplus.annotation.TableId;
import com.baomidou.mybatisplus.annotation.TableName;
import java.time.LocalDateTime;

@TableName("video_keyframe")
public class VideoKeyframe {

    @TableId(value = "id", type = IdType.AUTO)
    private Long id;

    @TableField("task_id")
    private String taskId;

    @TableField("user_id")
    private Long userId;

    @TableField("frame_index")
    private Integer frameIndex;

    @TableField("timestamp_millis")
    private Long timestampMillis;

    @TableField("time_text")
    private String timeText;

    @TableField("change_score")
    private Double changeScore;

    @TableField("select_reason")
    private String selectReason;

    @TableField("content_type")
    private String contentType;

    @TableField("storage_backend")
    private String storageBackend;

    @TableField("object_key")
    private String objectKey;

    @TableField("size_bytes")
    private Long sizeBytes;

    @TableField("quality_score")
    private Double qualityScore;

    @TableField("sharpness_score")
    private Double sharpnessScore;

    @TableField("brightness_mean")
    private Double brightnessMean;

    @TableField("brightness_variance")
    private Double brightnessVariance;

    @TableField("edge_density")
    private Double edgeDensity;

    @TableField("perceptual_hash")
    private String perceptualHash;

    @TableField("degraded")
    private Boolean degraded;

    @TableField("source_type")
    private String sourceType;

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

    public Integer getFrameIndex() {
        return frameIndex;
    }

    public void setFrameIndex(Integer frameIndex) {
        this.frameIndex = frameIndex;
    }

    public Long getTimestampMillis() {
        return timestampMillis;
    }

    public void setTimestampMillis(Long timestampMillis) {
        this.timestampMillis = timestampMillis;
    }

    public String getTimeText() {
        return timeText;
    }

    public void setTimeText(String timeText) {
        this.timeText = timeText;
    }

    public Double getChangeScore() {
        return changeScore;
    }

    public void setChangeScore(Double changeScore) {
        this.changeScore = changeScore;
    }

    public String getSelectReason() {
        return selectReason;
    }

    public void setSelectReason(String selectReason) {
        this.selectReason = selectReason;
    }

    public String getContentType() {
        return contentType;
    }

    public void setContentType(String contentType) {
        this.contentType = contentType;
    }

    public String getStorageBackend() {
        return storageBackend;
    }

    public void setStorageBackend(String storageBackend) {
        this.storageBackend = storageBackend;
    }

    public String getObjectKey() {
        return objectKey;
    }

    public void setObjectKey(String objectKey) {
        this.objectKey = objectKey;
    }

    public Long getSizeBytes() {
        return sizeBytes;
    }

    public void setSizeBytes(Long sizeBytes) {
        this.sizeBytes = sizeBytes;
    }

    public Double getQualityScore() {
        return qualityScore;
    }

    public void setQualityScore(Double qualityScore) {
        this.qualityScore = qualityScore;
    }

    public Double getSharpnessScore() {
        return sharpnessScore;
    }

    public void setSharpnessScore(Double sharpnessScore) {
        this.sharpnessScore = sharpnessScore;
    }

    public Double getBrightnessMean() {
        return brightnessMean;
    }

    public void setBrightnessMean(Double brightnessMean) {
        this.brightnessMean = brightnessMean;
    }

    public Double getBrightnessVariance() {
        return brightnessVariance;
    }

    public void setBrightnessVariance(Double brightnessVariance) {
        this.brightnessVariance = brightnessVariance;
    }

    public Double getEdgeDensity() {
        return edgeDensity;
    }

    public void setEdgeDensity(Double edgeDensity) {
        this.edgeDensity = edgeDensity;
    }

    public String getPerceptualHash() {
        return perceptualHash;
    }

    public void setPerceptualHash(String perceptualHash) {
        this.perceptualHash = perceptualHash;
    }

    public Boolean getDegraded() {
        return degraded;
    }

    public void setDegraded(Boolean degraded) {
        this.degraded = degraded;
    }

    public String getSourceType() {
        return sourceType;
    }

    public void setSourceType(String sourceType) {
        this.sourceType = sourceType;
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
