package com.example.courselingo.ai.record.service;

import com.example.courselingo.ai.record.dto.AiCallRecordView;
import com.example.courselingo.ai.record.dto.CompleteAiCallRecordCommand;
import com.example.courselingo.ai.record.dto.FailAiCallRecordCommand;
import com.example.courselingo.ai.record.dto.StartAiCallRecordCommand;
import java.util.List;

public interface AiCallRecordService {

    AiCallRecordView startCall(StartAiCallRecordCommand command);

    AiCallRecordView completeCall(CompleteAiCallRecordCommand command);

    AiCallRecordView failCall(FailAiCallRecordCommand command);

    List<AiCallRecordView> listByTask(String taskId, Long userId);
}
