package com.example.courselingo.ai.record.mapper;

import com.baomidou.mybatisplus.core.mapper.BaseMapper;
import com.baomidou.mybatisplus.core.toolkit.Wrappers;
import com.example.courselingo.ai.record.domain.AiCallRecord;
import java.util.List;
import org.apache.ibatis.annotations.Mapper;

@Mapper
public interface AiCallRecordMapper extends BaseMapper<AiCallRecord> {

    default List<AiCallRecord> selectByTaskIdAndUserId(String taskId, Long userId) {
        return selectList(Wrappers.<AiCallRecord>lambdaQuery()
            .eq(AiCallRecord::getTaskId, taskId)
            .eq(AiCallRecord::getUserId, userId)
            .orderByAsc(AiCallRecord::getCreatedAt)
            .orderByAsc(AiCallRecord::getId));
    }

    default AiCallRecord selectByIdTaskIdAndUserId(Long id, String taskId, Long userId) {
        return selectOne(Wrappers.<AiCallRecord>lambdaQuery()
            .eq(AiCallRecord::getId, id)
            .eq(AiCallRecord::getTaskId, taskId)
            .eq(AiCallRecord::getUserId, userId));
    }

    default int updateByIdTaskIdAndUserId(AiCallRecord record, Long id, String taskId, Long userId) {
        return update(record, Wrappers.<AiCallRecord>lambdaQuery()
            .eq(AiCallRecord::getId, id)
            .eq(AiCallRecord::getTaskId, taskId)
            .eq(AiCallRecord::getUserId, userId));
    }
}
