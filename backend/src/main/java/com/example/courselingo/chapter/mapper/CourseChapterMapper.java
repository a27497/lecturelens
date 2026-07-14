package com.example.courselingo.chapter.mapper;

import com.baomidou.mybatisplus.core.mapper.BaseMapper;
import com.baomidou.mybatisplus.core.toolkit.Wrappers;
import com.example.courselingo.chapter.domain.CourseChapter;
import java.util.List;
import org.apache.ibatis.annotations.Mapper;

@Mapper
public interface CourseChapterMapper extends BaseMapper<CourseChapter> {

    default List<CourseChapter> selectByTaskIdAndUserId(String taskId, Long userId) {
        return selectList(Wrappers.<CourseChapter>lambdaQuery()
            .eq(CourseChapter::getTaskId, taskId)
            .eq(CourseChapter::getUserId, userId)
            .orderByAsc(CourseChapter::getChapterIndex)
            .orderByAsc(CourseChapter::getId));
    }

    default int deleteByTaskIdAndUserId(String taskId, Long userId) {
        return delete(Wrappers.<CourseChapter>lambdaQuery()
            .eq(CourseChapter::getTaskId, taskId)
            .eq(CourseChapter::getUserId, userId));
    }
}
