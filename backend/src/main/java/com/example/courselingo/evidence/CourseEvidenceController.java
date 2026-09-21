package com.example.courselingo.evidence;

import com.example.courselingo.auth.service.CurrentUserService;
import com.example.courselingo.common.response.ApiResponse;
import org.springframework.web.bind.annotation.*;

@RestController
public class CourseEvidenceController {
    private final CourseEvidenceService evidence;
    private final CurrentUserService users;
    public CourseEvidenceController(CourseEvidenceService evidence, CurrentUserService users) {
        this.evidence = evidence;
        this.users = users;
    }

    @GetMapping("/api/tasks/{taskId}/evidence")
    public ApiResponse<CourseEvidenceService.Page> page(
        @PathVariable String taskId, @RequestHeader(value="Authorization", required=false) String auth,
        @RequestParam(required=false) Long revision, @RequestParam(defaultValue="") String after,
        @RequestParam(defaultValue="100") int limit) {
        return ApiResponse.success(evidence.page(taskId, users.currentUser(auth).userId(), revision, after, limit));
    }

    @GetMapping("/api/evidence/changes")
    public ApiResponse<java.util.List<java.util.Map<String,Object>>> changes(
        @RequestHeader(value="Authorization", required=false) String auth,
        @RequestParam(defaultValue="0") long after, @RequestParam(defaultValue="100") int limit) {
        return ApiResponse.success(evidence.changes(users.currentUser(auth).userId(), after, limit));
    }
}
