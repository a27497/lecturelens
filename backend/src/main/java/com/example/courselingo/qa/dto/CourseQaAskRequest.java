package com.example.courselingo.qa.dto;

import com.example.courselingo.evidence.LearningScope;

public record CourseQaAskRequest(String question, LearningScope learning_scope) {
    public CourseQaAskRequest(String question) { this(question, null); }
}
