package com.example.courselingo.subtitle.mapper;

import com.baomidou.mybatisplus.core.mapper.BaseMapper;
import com.baomidou.mybatisplus.core.toolkit.Wrappers;
import com.example.courselingo.subtitle.domain.SubtitleTranslationSegment;
import java.util.List;
import org.apache.ibatis.annotations.Mapper;

@Mapper
public interface SubtitleTranslationSegmentMapper extends BaseMapper<SubtitleTranslationSegment> {

    default List<SubtitleTranslationSegment> selectByTaskIdUserIdAndTargetLanguage(
        String taskId,
        Long userId,
        String targetLanguage
    ) {
        return selectList(Wrappers.<SubtitleTranslationSegment>lambdaQuery()
            .eq(SubtitleTranslationSegment::getTaskId, taskId)
            .eq(SubtitleTranslationSegment::getUserId, userId)
            .eq(SubtitleTranslationSegment::getTargetLanguage, targetLanguage)
            .orderByAsc(SubtitleTranslationSegment::getSegmentIndex));
    }

    default int deleteByTaskIdUserIdAndTargetLanguage(String taskId, Long userId, String targetLanguage) {
        return delete(Wrappers.<SubtitleTranslationSegment>lambdaQuery()
            .eq(SubtitleTranslationSegment::getTaskId, taskId)
            .eq(SubtitleTranslationSegment::getUserId, userId)
            .eq(SubtitleTranslationSegment::getTargetLanguage, targetLanguage));
    }

    default long countByTaskIdAndLanguage(String taskId, Long userId, String targetLanguage) {
        Long count = selectCount(Wrappers.<SubtitleTranslationSegment>lambdaQuery()
            .eq(SubtitleTranslationSegment::getTaskId, taskId)
            .eq(SubtitleTranslationSegment::getUserId, userId)
            .eq(SubtitleTranslationSegment::getTargetLanguage, targetLanguage));
        return count == null ? 0L : count;
    }
}
