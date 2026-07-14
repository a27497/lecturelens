package com.example.courselingo.vision.analysis.mapper;

import com.baomidou.mybatisplus.core.mapper.BaseMapper;
import com.baomidou.mybatisplus.core.toolkit.Wrappers;
import com.example.courselingo.vision.analysis.VideoKeyframeAnalysis;
import java.util.Collection;
import java.util.List;
import org.apache.ibatis.annotations.Mapper;

@Mapper
public interface VideoKeyframeAnalysisMapper extends BaseMapper<VideoKeyframeAnalysis> {

    default List<VideoKeyframeAnalysis> selectByKeyframeIds(String taskId, Long userId, Collection<Long> keyframeIds) {
        if (keyframeIds == null || keyframeIds.isEmpty()) {
            return List.of();
        }
        return selectList(Wrappers.<VideoKeyframeAnalysis>lambdaQuery()
            .eq(VideoKeyframeAnalysis::getTaskId, taskId)
            .eq(VideoKeyframeAnalysis::getUserId, userId)
            .in(VideoKeyframeAnalysis::getKeyframeId, keyframeIds));
    }

    default int deleteByTaskIdAndUserId(String taskId, Long userId) {
        return delete(Wrappers.<VideoKeyframeAnalysis>lambdaQuery()
            .eq(VideoKeyframeAnalysis::getTaskId, taskId)
            .eq(VideoKeyframeAnalysis::getUserId, userId));
    }
}
