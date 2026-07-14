package com.example.courselingo.upload.entity;

import com.baomidou.mybatisplus.annotation.IdType;
import com.baomidou.mybatisplus.annotation.TableField;
import com.baomidou.mybatisplus.annotation.TableId;
import com.baomidou.mybatisplus.annotation.TableName;
import java.time.LocalDateTime;

@TableName("upload_session")
public class UploadSession {

    @TableId(value = "id", type = IdType.INPUT)
    private String id;

    @TableField("user_id")
    private Long userId;

    @TableField("filename")
    private String filename;

    @TableField("ext")
    private String ext;

    @TableField("total_chunks")
    private Integer totalChunks;

    @TableField("chunk_size_bytes")
    private Long chunkSizeBytes;

    @TableField("size_bytes")
    private Long sizeBytes;

    @TableField("file_md5")
    private String fileMd5;

    @TableField("status")
    private String status;

    @TableField("storage_type")
    private String storageType;

    @TableField("object_key")
    private String objectKey;

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

    public String getFilename() {
        return filename;
    }

    public void setFilename(String filename) {
        this.filename = filename;
    }

    public String getExt() {
        return ext;
    }

    public void setExt(String ext) {
        this.ext = ext;
    }

    public Integer getTotalChunks() {
        return totalChunks;
    }

    public void setTotalChunks(Integer totalChunks) {
        this.totalChunks = totalChunks;
    }

    public Long getChunkSizeBytes() {
        return chunkSizeBytes;
    }

    public void setChunkSizeBytes(Long chunkSizeBytes) {
        this.chunkSizeBytes = chunkSizeBytes;
    }

    public Long getSizeBytes() {
        return sizeBytes;
    }

    public void setSizeBytes(Long sizeBytes) {
        this.sizeBytes = sizeBytes;
    }

    public String getFileMd5() {
        return fileMd5;
    }

    public void setFileMd5(String fileMd5) {
        this.fileMd5 = fileMd5;
    }

    public String getStatus() {
        return status;
    }

    public void setStatus(String status) {
        this.status = status;
    }

    public String getStorageType() {
        return storageType;
    }

    public void setStorageType(String storageType) {
        this.storageType = storageType;
    }

    public String getObjectKey() {
        return objectKey;
    }

    public void setObjectKey(String objectKey) {
        this.objectKey = objectKey;
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
