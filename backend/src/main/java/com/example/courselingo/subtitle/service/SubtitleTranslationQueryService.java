package com.example.courselingo.subtitle.service;

import com.example.courselingo.subtitle.dto.SubtitleTranslationSegmentView;
import java.util.List;

public interface SubtitleTranslationQueryService {

    List<SubtitleTranslationSegmentView> listTranslations(String taskId, Long userId, String targetLanguage);

    long countByTaskIdAndLanguage(String taskId, Long userId, String targetLanguage);
}
