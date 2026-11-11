package com.example.courselingo.study;

import com.example.courselingo.auth.service.CurrentUserService;
import com.example.courselingo.common.error.ErrorCode;
import com.example.courselingo.common.exception.BusinessException;
import com.example.courselingo.common.response.ApiResponse;
import com.fasterxml.jackson.databind.JsonNode;
import java.util.LinkedHashMap;
import java.util.Map;
import org.springframework.web.bind.annotation.*;

/** Authenticated gateway only. Session, execution and artifact state belong to Python/PG. */
@RestController
@RequestMapping("/api/tasks/{taskId}/tutor/sessions")
public class TutorController {
    private final CurrentUserService users;
    private final StudyProperties properties;
    private final StudyEvidenceAuthority authority;
    private final StudyTransport transport;

    public TutorController(CurrentUserService users, StudyProperties properties,
                           StudyEvidenceAuthority authority, StudyTransport transport) {
        this.users = users; this.properties = properties; this.authority = authority; this.transport = transport;
    }

    public record Create(String request_key) {}
    public record Turn(String client_turn_id, String text, boolean socratic) {}

    @PostMapping
    public ApiResponse<JsonNode> create(@PathVariable String taskId,
            @RequestHeader(value="Authorization", required=false) String auth, @RequestBody Create body) {
        id(body.request_key());
        return invoke(taskId, auth, "CREATE", null, Map.of("request_key", body.request_key()));
    }

    @GetMapping
    public ApiResponse<JsonNode> list(@PathVariable String taskId,
            @RequestHeader(value="Authorization", required=false) String auth) {
        return invoke(taskId, auth, "LIST", null, Map.of());
    }

    @GetMapping("/{sessionId}")
    public ApiResponse<JsonNode> get(@PathVariable String taskId, @PathVariable String sessionId,
            @RequestHeader(value="Authorization", required=false) String auth) {
        return invoke(taskId, auth, "GET", sessionId, Map.of());
    }

    @PostMapping("/{sessionId}/turns")
    public ApiResponse<JsonNode> turn(@PathVariable String taskId, @PathVariable String sessionId,
            @RequestHeader(value="Authorization", required=false) String auth, @RequestBody Turn body) {
        id(body.client_turn_id());
        if (body.text() == null || body.text().isBlank() || body.text().length() > 2000)
            throw new BusinessException(ErrorCode.COMMON_BAD_REQUEST);
        return invoke(taskId, auth, "TURN", sessionId,
                Map.of("client_turn_id", body.client_turn_id(), "text", body.text(), "socratic", body.socratic()));
    }

    @PostMapping("/{sessionId}/turns/{clientTurnId}/cancel")
    public ApiResponse<JsonNode> cancel(@PathVariable String taskId, @PathVariable String sessionId,
            @PathVariable String clientTurnId, @RequestHeader(value="Authorization", required=false) String auth) {
        id(clientTurnId);
        return invoke(taskId, auth, "CANCEL", sessionId, Map.of("client_turn_id", clientTurnId));
    }

    private void id(String value) {
        if (value == null || !value.matches("[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}"))
            throw new BusinessException(ErrorCode.COMMON_BAD_REQUEST);
    }

    private ApiResponse<JsonNode> invoke(String taskId, String auth, String operation,
                                         String sessionId, Map<String,Object> arguments) {
        if (!properties.isEnabled()) throw new BusinessException(ErrorCode.STUDY_UNAVAILABLE);
        long owner = users.currentUser(auth).userId();
        if (sessionId != null) id(sessionId);
        long revision = authority.current(taskId, owner, operation.equals("TURN") || operation.equals("CREATE"));
        Map<String,Object> payload = new LinkedHashMap<>(arguments);
        payload.put("owner_id", owner); payload.put("course_id", taskId);
        payload.put("revision", revision); payload.put("operation", operation);
        if (sessionId != null) payload.put("session_id", sessionId);
        var result = transport.tutor(payload);
        if (authority.current(taskId, owner, false) != revision)
            throw new BusinessException(ErrorCode.STUDY_CONFLICT);
        return ApiResponse.success(result);
    }
}
