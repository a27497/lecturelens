package com.example.courselingo.artifact.mapper;

import com.baomidou.mybatisplus.core.mapper.BaseMapper;
import com.baomidou.mybatisplus.core.toolkit.Wrappers;
import com.example.courselingo.artifact.domain.ArtifactFile;
import java.util.List;
import org.apache.ibatis.annotations.Mapper;

@Mapper
public interface ArtifactFileMapper extends BaseMapper<ArtifactFile> {

    default List<ArtifactFile> selectByTaskIdAndUserId(String taskId, Long userId) {
        return selectList(Wrappers.<ArtifactFile>lambdaQuery()
            .eq(ArtifactFile::getTaskId, taskId)
            .eq(ArtifactFile::getUserId, userId)
            .orderByAsc(ArtifactFile::getArtifactType)
            .orderByAsc(ArtifactFile::getLanguage)
            .orderByAsc(ArtifactFile::getCreatedAt));
    }

    default ArtifactFile selectByScope(String taskId, Long userId, String artifactType, String language) {
        return selectOne(Wrappers.<ArtifactFile>lambdaQuery()
            .eq(ArtifactFile::getTaskId, taskId)
            .eq(ArtifactFile::getUserId, userId)
            .eq(ArtifactFile::getArtifactType, artifactType)
            .eq(ArtifactFile::getLanguage, language));
    }

    default int deleteByScope(String taskId, Long userId, String artifactType, String language) {
        return delete(Wrappers.<ArtifactFile>lambdaQuery()
            .eq(ArtifactFile::getTaskId, taskId)
            .eq(ArtifactFile::getUserId, userId)
            .eq(ArtifactFile::getArtifactType, artifactType)
            .eq(ArtifactFile::getLanguage, language));
    }

    default long countByScope(String taskId, Long userId, String artifactType, String language) {
        Long count = selectCount(Wrappers.<ArtifactFile>lambdaQuery()
            .eq(ArtifactFile::getTaskId, taskId)
            .eq(ArtifactFile::getUserId, userId)
            .eq(ArtifactFile::getArtifactType, artifactType)
            .eq(ArtifactFile::getLanguage, language));
        return count == null ? 0L : count;
    }
}
