package com.example.courselingo.task.mapper;

import com.baomidou.mybatisplus.core.mapper.BaseMapper;
import com.baomidou.mybatisplus.core.conditions.query.LambdaQueryWrapper;
import com.baomidou.mybatisplus.core.toolkit.Wrappers;
import com.example.courselingo.task.entity.AnalysisTask;
import java.time.LocalDateTime;
import java.util.Collection;
import java.util.List;
import java.util.Set;
import org.apache.ibatis.annotations.Mapper;

@Mapper
public interface AnalysisTaskMapper extends BaseMapper<AnalysisTask> {

    default AnalysisTask selectByIdAndUserId(String id, Long userId) {
        return selectOne(Wrappers.<AnalysisTask>lambdaQuery()
            .eq(AnalysisTask::getId, id)
            .eq(AnalysisTask::getUserId, userId)
            .isNull(AnalysisTask::getDeletedAt));
    }

    default List<AnalysisTask> selectByIdsAndUserIdIncludingDeleted(Collection<String> ids, Long userId) {
        return selectList(Wrappers.<AnalysisTask>lambdaQuery()
            .in(AnalysisTask::getId, ids)
            .eq(AnalysisTask::getUserId, userId));
    }

    default List<AnalysisTask> selectPageByUserId(Long userId, String status, long offset, int pageSize) {
        LambdaQueryWrapper<AnalysisTask> query = Wrappers.<AnalysisTask>lambdaQuery()
            .eq(AnalysisTask::getUserId, userId)
            .isNull(AnalysisTask::getDeletedAt);
        if (status != null) {
            query.eq(AnalysisTask::getStatus, status);
        }
        return selectList(query
            .orderByDesc(AnalysisTask::getCreatedAt)
            .last("LIMIT " + pageSize + " OFFSET " + offset));
    }

    default long countByUserId(Long userId, String status) {
        LambdaQueryWrapper<AnalysisTask> query = Wrappers.<AnalysisTask>lambdaQuery()
            .eq(AnalysisTask::getUserId, userId)
            .isNull(AnalysisTask::getDeletedAt);
        if (status != null) {
            query.eq(AnalysisTask::getStatus, status);
        }
        Long count = selectCount(query);
        return count == null ? 0L : count;
    }

    default int updateStateByIdAndUserId(AnalysisTask task) {
        return update(Wrappers.<AnalysisTask>lambdaUpdate()
            .eq(AnalysisTask::getId, task.getId())
            .eq(AnalysisTask::getUserId, task.getUserId())
            .isNull(AnalysisTask::getDeletedAt)
            .set(AnalysisTask::getStatus, task.getStatus())
            .set(AnalysisTask::getProgressPercent, task.getProgressPercent())
            .set(AnalysisTask::getCurrentStage, task.getCurrentStage())
            .set(AnalysisTask::getErrorCode, task.getErrorCode())
            .set(AnalysisTask::getErrorMessage, task.getErrorMessage())
            .set(AnalysisTask::getStartedAt, task.getStartedAt())
            .set(AnalysisTask::getFinishedAt, task.getFinishedAt()));
    }

    default int updateRetryingByIdAndUserId(AnalysisTask task) {
        return update(Wrappers.<AnalysisTask>lambdaUpdate()
            .eq(AnalysisTask::getId, task.getId())
            .eq(AnalysisTask::getUserId, task.getUserId())
            .isNull(AnalysisTask::getDeletedAt)
            .set(AnalysisTask::getStatus, task.getStatus())
            .set(AnalysisTask::getRetryCount, task.getRetryCount())
            .set(AnalysisTask::getErrorCode, task.getErrorCode())
            .set(AnalysisTask::getErrorMessage, task.getErrorMessage())
            .set(AnalysisTask::getFinishedAt, task.getFinishedAt()));
    }

    default int updateRunningProgressByIdAndUserId(String id, Long userId, int progressPercent, String currentStage) {
        return update(Wrappers.<AnalysisTask>lambdaUpdate()
            .eq(AnalysisTask::getId, id)
            .eq(AnalysisTask::getUserId, userId)
            .isNull(AnalysisTask::getDeletedAt)
            .eq(AnalysisTask::getStatus, "RUNNING")
            .set(AnalysisTask::getProgressPercent, progressPercent)
            .set(AnalysisTask::getCurrentStage, currentStage));
    }

    default int softDeleteByIdsAndUserId(
        Collection<String> ids,
        Long userId,
        Set<String> allowedStatuses,
        LocalDateTime deletedAt
    ) {
        return update(Wrappers.<AnalysisTask>lambdaUpdate()
            .in(AnalysisTask::getId, ids)
            .eq(AnalysisTask::getUserId, userId)
            .isNull(AnalysisTask::getDeletedAt)
            .in(AnalysisTask::getStatus, allowedStatuses)
            .set(AnalysisTask::getDeletedAt, deletedAt)
            .set(AnalysisTask::getUpdatedAt, deletedAt));
    }
}
