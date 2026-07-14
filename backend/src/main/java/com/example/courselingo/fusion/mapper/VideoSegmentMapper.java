package com.example.courselingo.fusion.mapper;

import com.baomidou.mybatisplus.core.mapper.BaseMapper;
import com.baomidou.mybatisplus.core.toolkit.Wrappers;
import com.example.courselingo.fusion.VideoSegment;
import java.util.List;
import org.apache.ibatis.annotations.Mapper;

@Mapper
public interface VideoSegmentMapper extends BaseMapper<VideoSegment> {

    default List<VideoSegment> selectByTaskIdAndUserId(String taskId, Long userId) {
        return selectList(Wrappers.<VideoSegment>lambdaQuery()
            .eq(VideoSegment::getTaskId, taskId)
            .eq(VideoSegment::getUserId, userId)
            .orderByAsc(VideoSegment::getSegmentIndex)
            .orderByAsc(VideoSegment::getId));
    }

    default int deleteByTaskIdAndUserId(String taskId, Long userId) {
        return delete(Wrappers.<VideoSegment>lambdaQuery()
            .eq(VideoSegment::getTaskId, taskId)
            .eq(VideoSegment::getUserId, userId));
    }
}
