package com.example.courselingo.subtitle.service;

import com.example.courselingo.subtitle.dto.SubtitleSegmentView;
import java.util.List;

public interface SubtitleSegmentQueryService {

    List<SubtitleSegmentView> listByTaskId(String taskId, Long userId);

    long countByTaskId(String taskId, Long userId);
}
