package com.example.courselingo.video.context.mapper;

import com.baomidou.mybatisplus.core.mapper.BaseMapper;
import com.baomidou.mybatisplus.core.toolkit.Wrappers;
import com.example.courselingo.video.context.domain.CourseVideoChunk;
import java.util.List;
import org.apache.ibatis.annotations.Mapper;

@Mapper
public interface CourseVideoChunkMapper extends BaseMapper<CourseVideoChunk> {

    default List<CourseVideoChunk> selectByTaskIdUserIdAndTargetLanguage(String taskId, Long userId, String targetLanguage) {
        return selectList(Wrappers.<CourseVideoChunk>lambdaQuery()
            .eq(CourseVideoChunk::getTaskId, taskId)
            .eq(CourseVideoChunk::getUserId, userId)
            .eq(CourseVideoChunk::getTargetLanguage, targetLanguage)
            .orderByAsc(CourseVideoChunk::getChunkIndex)
            .orderByAsc(CourseVideoChunk::getId));
    }

    default int deleteByTaskIdUserIdAndTargetLanguage(String taskId, Long userId, String targetLanguage) {
        return delete(Wrappers.<CourseVideoChunk>lambdaQuery()
            .eq(CourseVideoChunk::getTaskId, taskId)
            .eq(CourseVideoChunk::getUserId, userId)
            .eq(CourseVideoChunk::getTargetLanguage, targetLanguage));
    }
}
