package com.example.courselingo.systemmodel;

import com.example.courselingo.auth.dto.CurrentUserResponse;
import com.example.courselingo.common.response.ApiResponse;

import jakarta.servlet.http.HttpServletRequest;

import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.web.bind.annotation.*;

import java.util.List;

@RestController
@RequestMapping("/api/admin/system-models")
@ConditionalOnProperty(
        prefix = "courselingo.ai.system-models",
        name = "enabled",
        havingValue = "true")
public class SystemModelAdminController {
    private final SystemModelRegistry registry;
    private final SystemModelExecutionService executions;

    @GetMapping("/executions")
    public ApiResponse<List<SystemModelViews.Execution>> executions(@RequestParam String taskId) {
        return ApiResponse.success(executions.list(taskId));
    }

    public SystemModelAdminController(
            SystemModelRegistry registry, SystemModelExecutionService executions) {
        this.registry = registry;
        this.executions = executions;
    }

    private long actor(HttpServletRequest request) {
        return ((CurrentUserResponse)
                        request.getAttribute(SystemModelAdminWebConfiguration.ADMIN_ATTRIBUTE))
                .userId();
    }

    @GetMapping("/catalog")
    public ApiResponse<SystemModelViews.Catalog> catalog() {
        return ApiResponse.success(registry.catalog());
    }

    @PostMapping("/providers")
    public ApiResponse<SystemModelViews.Catalog> createProvider(
            @RequestBody SystemModelCommands.Provider command, HttpServletRequest request) {
        return ApiResponse.success(registry.saveProvider(null, command, actor(request)));
    }

    @PatchMapping("/providers/{id}")
    public ApiResponse<SystemModelViews.Catalog> saveProvider(
            @PathVariable long id,
            @RequestBody SystemModelCommands.Provider command,
            HttpServletRequest request) {
        return ApiResponse.success(registry.saveProvider(id, command, actor(request)));
    }

    @DeleteMapping("/providers/{id}")
    public ApiResponse<SystemModelViews.Catalog> deleteProvider(
            @PathVariable long id, @RequestParam long expectedVersion, HttpServletRequest request) {
        return ApiResponse.success(
                registry.delete("PROVIDER", id, expectedVersion, actor(request)));
    }

    @PostMapping("/providers/{id}/models")
    public ApiResponse<SystemModelViews.Catalog> createModel(
            @PathVariable long id,
            @RequestBody SystemModelCommands.Model command,
            HttpServletRequest request) {
        return ApiResponse.success(registry.saveModel(null, id, command, actor(request)));
    }

    @PatchMapping("/providers/{providerId}/models/{id}")
    public ApiResponse<SystemModelViews.Catalog> saveModel(
            @PathVariable long providerId,
            @PathVariable long id,
            @RequestBody SystemModelCommands.Model command,
            HttpServletRequest request) {
        return ApiResponse.success(registry.saveModel(id, providerId, command, actor(request)));
    }

    @DeleteMapping("/models/{id}")
    public ApiResponse<SystemModelViews.Catalog> deleteModel(
            @PathVariable long id, @RequestParam long expectedVersion, HttpServletRequest request) {
        return ApiResponse.success(registry.delete("MODEL", id, expectedVersion, actor(request)));
    }

    @PutMapping("/bindings")
    public ApiResponse<SystemModelViews.Catalog> bindings(
            @RequestBody SystemModelCommands.Bindings command, HttpServletRequest request) {
        return ApiResponse.success(registry.bindings(command, actor(request)));
    }

    @PostMapping("/rollbacks")
    public ApiResponse<SystemModelViews.Catalog> rollback(
            @RequestBody SystemModelCommands.Rollback command, HttpServletRequest request) {
        return ApiResponse.success(registry.rollback(command, actor(request)));
    }

    @GetMapping("/versions")
    public ApiResponse<List<SystemModelViews.VersionSummary>> versions(
            @RequestParam(defaultValue = "9223372036854775807") long before) {
        return ApiResponse.success(registry.versions(before));
    }

    @GetMapping("/versions/{version}")
    public ApiResponse<SystemModelViews.Version> version(@PathVariable long version) {
        return ApiResponse.success(registry.version(version));
    }

    @GetMapping("/audit")
    public ApiResponse<List<SystemModelViews.Audit>> audit(
            @RequestParam(defaultValue = "9223372036854775807") long before) {
        return ApiResponse.success(registry.audit(before));
    }

    @GetMapping("/executions/{id}")
    public ApiResponse<SystemModelViews.Execution> execution(@PathVariable String id) {
        return ApiResponse.success(executions.query(id));
    }
}
