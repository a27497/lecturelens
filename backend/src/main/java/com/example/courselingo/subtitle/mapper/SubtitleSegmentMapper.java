package com.example.courselingo.subtitle.mapper;

import com.baomidou.mybatisplus.core.mapper.BaseMapper;
import com.baomidou.mybatisplus.core.toolkit.Wrappers;
import com.example.courselingo.subtitle.domain.SubtitleSegment;
import java.util.List;
import org.apache.ibatis.annotations.Mapper;

@Mapper
public interface SubtitleSegmentMapper extends BaseMapper<SubtitleSegment> {

    default List<SubtitleSegment> selectByTaskIdAndUserId(String taskId, Long userId) {
        return selectList(Wrappers.<SubtitleSegment>lambdaQuery()
            .eq(SubtitleSegment::getTaskId, taskId)
            .eq(SubtitleSegment::getUserId, userId)
            .orderByAsc(SubtitleSegment::getSegmentIndex));
    }

    default int deleteByTaskIdAndUserId(String taskId, Long userId) {
        return delete(Wrappers.<SubtitleSegment>lambdaQuery()
            .eq(SubtitleSegment::getTaskId, taskId)
            .eq(SubtitleSegment::getUserId, userId));
    }

    default long countByTaskIdAndUserId(String taskId, Long userId) {
        Long count = selectCount(Wrappers.<SubtitleSegment>lambdaQuery()
            .eq(SubtitleSegment::getTaskId, taskId)
            .eq(SubtitleSegment::getUserId, userId));
        return count == null ? 0L : count;
    }
}
