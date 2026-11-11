package com.example.courselingo.systemmodel;

import com.example.courselingo.auth.service.CurrentUserService;
import com.example.courselingo.common.response.ApiResponse;
import org.springframework.web.bind.annotation.*;

@RestController
@RequestMapping("/api/tasks/{taskId}/model-usage")
public class CourseModelUsageController {
    private final CurrentUserService users;
    private final CourseModelUsageService usage;
    public CourseModelUsageController(CurrentUserService users, CourseModelUsageService usage) {
        this.users = users;
        this.usage = usage;
    }
    @GetMapping
    public org.springframework.http.ResponseEntity<ApiResponse<CourseModelUsageService.Usage>> read(@PathVariable String taskId,
            @RequestHeader(value = "Authorization", required = false) String authorization) {
        return org.springframework.http.ResponseEntity.ok().cacheControl(org.springframework.http.CacheControl.noStore())
                .body(ApiResponse.success(usage.read(taskId, users.currentUser(authorization).userId())));
    }
}
