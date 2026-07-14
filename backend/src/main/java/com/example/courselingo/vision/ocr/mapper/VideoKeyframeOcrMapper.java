package com.example.courselingo.vision.ocr.mapper;

import com.baomidou.mybatisplus.core.mapper.BaseMapper;
import com.baomidou.mybatisplus.core.toolkit.Wrappers;
import com.example.courselingo.vision.ocr.VideoKeyframeOcr;
import java.util.Collection;
import java.util.List;
import org.apache.ibatis.annotations.Mapper;

@Mapper
public interface VideoKeyframeOcrMapper extends BaseMapper<VideoKeyframeOcr> {

    default List<VideoKeyframeOcr> selectByTaskIdAndUserId(String taskId, Long userId) {
        return selectList(Wrappers.<VideoKeyframeOcr>lambdaQuery()
            .eq(VideoKeyframeOcr::getTaskId, taskId)
            .eq(VideoKeyframeOcr::getUserId, userId)
            .orderByAsc(VideoKeyframeOcr::getTimestampMillis)
            .orderByAsc(VideoKeyframeOcr::getId));
    }

    default List<VideoKeyframeOcr> selectByKeyframeIds(String taskId, Long userId, Collection<Long> keyframeIds) {
        if (keyframeIds == null || keyframeIds.isEmpty()) {
            return List.of();
        }
        return selectList(Wrappers.<VideoKeyframeOcr>lambdaQuery()
            .eq(VideoKeyframeOcr::getTaskId, taskId)
            .eq(VideoKeyframeOcr::getUserId, userId)
            .in(VideoKeyframeOcr::getKeyframeId, keyframeIds));
    }

    default int deleteByTaskIdAndUserId(String taskId, Long userId) {
        return delete(Wrappers.<VideoKeyframeOcr>lambdaQuery()
            .eq(VideoKeyframeOcr::getTaskId, taskId)
            .eq(VideoKeyframeOcr::getUserId, userId));
    }
}
