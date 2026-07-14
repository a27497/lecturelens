package com.example.courselingo.qa.service;

public class NoopCourseQaRateLimitService implements CourseQaRateLimitService {

    @Override
    public CourseQaRateLimitResult checkAndConsume(Long userId) {
        return CourseQaRateLimitResult.allowed(Integer.MAX_VALUE, Integer.MAX_VALUE);
    }
}
