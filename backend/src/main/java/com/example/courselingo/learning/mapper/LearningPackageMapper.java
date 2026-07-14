package com.example.courselingo.learning.mapper;

import com.baomidou.mybatisplus.core.mapper.BaseMapper;
import com.baomidou.mybatisplus.core.toolkit.Wrappers;
import com.example.courselingo.learning.domain.LearningPackage;
import org.apache.ibatis.annotations.Mapper;

@Mapper
public interface LearningPackageMapper extends BaseMapper<LearningPackage> {

    default LearningPackage selectByTaskIdUserIdAndTargetLanguage(String taskId, Long userId, String targetLanguage) {
        return selectOne(Wrappers.<LearningPackage>lambdaQuery()
            .eq(LearningPackage::getTaskId, taskId)
            .eq(LearningPackage::getUserId, userId)
            .eq(LearningPackage::getTargetLanguage, targetLanguage));
    }

    default int deleteByTaskIdUserIdAndTargetLanguage(String taskId, Long userId, String targetLanguage) {
        return delete(Wrappers.<LearningPackage>lambdaQuery()
            .eq(LearningPackage::getTaskId, taskId)
            .eq(LearningPackage::getUserId, userId)
            .eq(LearningPackage::getTargetLanguage, targetLanguage));
    }

    default long countByTaskIdAndLanguage(String taskId, Long userId, String targetLanguage) {
        Long count = selectCount(Wrappers.<LearningPackage>lambdaQuery()
            .eq(LearningPackage::getTaskId, taskId)
            .eq(LearningPackage::getUserId, userId)
            .eq(LearningPackage::getTargetLanguage, targetLanguage));
        return count == null ? 0L : count;
    }
}
