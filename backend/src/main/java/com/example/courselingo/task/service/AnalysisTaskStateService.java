package com.example.courselingo.task.service;

import com.example.courselingo.task.dto.AnalysisTaskStateChangeCommand;

public interface AnalysisTaskStateService {

    void changeState(AnalysisTaskStateChangeCommand command);
}
