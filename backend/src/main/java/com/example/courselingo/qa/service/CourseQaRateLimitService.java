package com.example.courselingo.qa.service;

public interface CourseQaRateLimitService {

    CourseQaRateLimitResult checkAndConsume(Long userId);
}
