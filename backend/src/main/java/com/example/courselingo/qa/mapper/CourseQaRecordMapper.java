package com.example.courselingo.qa.mapper;

import com.baomidou.mybatisplus.core.mapper.BaseMapper;
import com.baomidou.mybatisplus.core.toolkit.Wrappers;
import com.example.courselingo.qa.domain.CourseQaRecord;
import java.util.List;
import org.apache.ibatis.annotations.Mapper;

@Mapper
public interface CourseQaRecordMapper extends BaseMapper<CourseQaRecord> {

    default List<CourseQaRecord> selectByTaskIdAndUserId(String taskId, Long userId, int limit) {
        int safeLimit = Math.max(1, Math.min(limit, 100));
        return selectList(Wrappers.<CourseQaRecord>lambdaQuery()
            .eq(CourseQaRecord::getTaskId, taskId)
            .eq(CourseQaRecord::getUserId, userId)
            .orderByDesc(CourseQaRecord::getCreatedAt)
            .orderByDesc(CourseQaRecord::getId)
            .last("LIMIT " + safeLimit));
    }
}
