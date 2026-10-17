package com.example.courselingo.systemmodel;

import com.example.courselingo.auth.dto.CurrentUserResponse;
import com.example.courselingo.common.response.ApiResponse;

import jakarta.servlet.http.HttpServletRequest;

import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.web.bind.annotation.*;

@RestController
@RequestMapping("/api/admin/system-models")
@ConditionalOnProperty(
        prefix = "courselingo.ai.system-models",
        name = "enabled",
        havingValue = "true")
public class SystemModelOperationsController {
    private final SystemModelStatusService status;
    private final SystemModelProbeService probes;

    public SystemModelOperationsController(
            SystemModelStatusService status, SystemModelProbeService probes) {
        this.status = status;
        this.probes = probes;
    }

    @GetMapping("/status")
    public ApiResponse<SystemModelStatusService.Status> status(@RequestParam long version) {
        return ApiResponse.success(status.inspect(version));
    }

    @GetMapping("/probe-policy")
    public ApiResponse<SystemModelProbeService.Policy> policy() {
        return ApiResponse.success(probes.policy());
    }

    @PostMapping("/probes")
    public ApiResponse<SystemModelProbeService.Result> probe(
            @RequestBody SystemModelProbeService.Command command, HttpServletRequest request) {
        var admin =
                (CurrentUserResponse)
                        request.getAttribute(SystemModelAdminWebConfiguration.ADMIN_ATTRIBUTE);
        return ApiResponse.success(probes.probe(command, admin.userId()));
    }
}
