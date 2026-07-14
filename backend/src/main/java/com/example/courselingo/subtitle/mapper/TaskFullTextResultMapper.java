package com.example.courselingo.subtitle.mapper;

import com.baomidou.mybatisplus.core.mapper.BaseMapper;
import com.baomidou.mybatisplus.core.toolkit.Wrappers;
import com.example.courselingo.subtitle.domain.TaskFullTextResult;
import org.apache.ibatis.annotations.Mapper;

@Mapper
public interface TaskFullTextResultMapper extends BaseMapper<TaskFullTextResult> {

    default TaskFullTextResult selectByTaskIdUserIdAndTargetLanguage(
        String taskId,
        Long userId,
        String targetLanguage
    ) {
        return selectOne(Wrappers.<TaskFullTextResult>lambdaQuery()
            .eq(TaskFullTextResult::getTaskId, taskId)
            .eq(TaskFullTextResult::getUserId, userId)
            .eq(TaskFullTextResult::getTargetLanguage, targetLanguage));
    }

    default int deleteByTaskIdUserIdAndTargetLanguage(String taskId, Long userId, String targetLanguage) {
        return delete(Wrappers.<TaskFullTextResult>lambdaQuery()
            .eq(TaskFullTextResult::getTaskId, taskId)
            .eq(TaskFullTextResult::getUserId, userId)
            .eq(TaskFullTextResult::getTargetLanguage, targetLanguage));
    }
}
