package com.example.courselingo.vision.keyframe.mapper;

import com.baomidou.mybatisplus.core.mapper.BaseMapper;
import com.baomidou.mybatisplus.core.toolkit.Wrappers;
import com.example.courselingo.vision.keyframe.VideoKeyframe;
import java.util.List;
import org.apache.ibatis.annotations.Mapper;

@Mapper
public interface VideoKeyframeMapper extends BaseMapper<VideoKeyframe> {

    default List<VideoKeyframe> selectByTaskIdAndUserId(String taskId, Long userId) {
        return selectList(Wrappers.<VideoKeyframe>lambdaQuery()
            .eq(VideoKeyframe::getTaskId, taskId)
            .eq(VideoKeyframe::getUserId, userId)
            .orderByAsc(VideoKeyframe::getTimestampMillis)
            .orderByAsc(VideoKeyframe::getId));
    }

    default VideoKeyframe selectByIdAndTaskIdAndUserId(Long id, String taskId, Long userId) {
        return selectOne(Wrappers.<VideoKeyframe>lambdaQuery()
            .eq(VideoKeyframe::getId, id)
            .eq(VideoKeyframe::getTaskId, taskId)
            .eq(VideoKeyframe::getUserId, userId));
    }

    default List<VideoKeyframe> selectExistingForTask(String taskId, Long userId) {
        return selectList(Wrappers.<VideoKeyframe>lambdaQuery()
            .eq(VideoKeyframe::getTaskId, taskId)
            .eq(VideoKeyframe::getUserId, userId));
    }

    default int deleteByTaskIdAndUserId(String taskId, Long userId) {
        return delete(Wrappers.<VideoKeyframe>lambdaQuery()
            .eq(VideoKeyframe::getTaskId, taskId)
            .eq(VideoKeyframe::getUserId, userId));
    }
}
