package com.example.courselingo.qa.service;

import com.example.courselingo.common.error.ErrorCode;
import com.example.courselingo.common.exception.BusinessException;
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import java.util.ArrayList;
import java.util.LinkedHashSet;
import java.util.List;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.stereotype.Component;

@Component
public class CourseQaResponseParser {

    private final ObjectMapper objectMapper;

    public CourseQaResponseParser() {
        this(new ObjectMapper());
    }

    @Autowired
    public CourseQaResponseParser(ObjectMapper objectMapper) {
        this.objectMapper = objectMapper == null ? new ObjectMapper() : objectMapper;
    }

    public ParsedCourseQaResponse parse(String content, int evidenceCount) {
        try {
            JsonNode root = objectMapper.readTree(content == null ? "" : content);
            String answer = root.path("answer").asText("").strip();
            if (answer.isBlank()) {
                throw invalid("QA answer is empty");
            }
            LinkedHashSet<Integer> indexes = new LinkedHashSet<>();
            JsonNode cited = root.path("citedEvidenceIndexes");
            if (cited.isArray()) {
                for (JsonNode node : cited) {
                    if (node.canConvertToInt()) {
                        int index = node.asInt();
                        if (index >= 0 && index < evidenceCount) {
                            indexes.add(index);
                        }
                    }
                }
            }
            return new ParsedCourseQaResponse(answer, new ArrayList<>(indexes));
        } catch (BusinessException exception) {
            throw exception;
        } catch (Exception exception) {
            throw invalid("QA provider returned invalid JSON");
        }
    }

    private static BusinessException invalid(String message) {
        return new BusinessException(ErrorCode.AI_PROVIDER_FAILED, message);
    }

    public record ParsedCourseQaResponse(
        String answer,
        List<Integer> citedEvidenceIndexes
    ) {
        public ParsedCourseQaResponse {
            citedEvidenceIndexes = citedEvidenceIndexes == null ? List.of() : List.copyOf(citedEvidenceIndexes);
        }
    }
}
