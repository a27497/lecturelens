package com.example.courselingo.study;

import com.example.courselingo.auth.service.CurrentUserService;
import com.example.courselingo.common.error.ErrorCode;
import com.example.courselingo.common.exception.BusinessException;
import com.example.courselingo.common.response.ApiResponse;
import com.fasterxml.jackson.databind.JsonNode;
import java.util.LinkedHashMap;
import java.util.Map;
import java.util.Set;
import org.springframework.web.bind.annotation.*;

/** Browser authentication gateway. Model configuration and credentials belong to the Python Agent. */
@RestController
public class ModelManagementController {
    private final CurrentUserService users;
    private final StudyProperties properties;
    private final StudyTransport transport;

    public ModelManagementController(CurrentUserService users, StudyProperties properties, StudyTransport transport) {
        this.users=users; this.properties=properties; this.transport=transport;
    }

    @PostMapping("/api/agent/models/command")
    public ApiResponse<JsonNode> command(@RequestHeader(value="Authorization",required=false) String auth,
                                        @RequestBody JsonNode command) {
        long owner=users.currentUser(auth).userId();
        if (!properties.isEnabled()) throw new BusinessException(ErrorCode.STUDY_UNAVAILABLE,"MODEL_MANAGEMENT_DISABLED");
        Set<String> fields=Set.of("operation","connection_id","version","connection","model","bindings");
        if (command==null || !command.isObject() || command.toString().length()>65536
                || !Set.of("LIST","SAVE","DELETE","DISCOVER","PROBE","ROUTE","CLEAR_ROUTES").contains(command.path("operation").asText())) {
            throw new BusinessException(ErrorCode.COMMON_BAD_REQUEST);
        }
        Map<String,Object> payload=new LinkedHashMap<>();
        command.fields().forEachRemaining(entry->{
            if (!fields.contains(entry.getKey())) throw new BusinessException(ErrorCode.COMMON_BAD_REQUEST);
            payload.put(entry.getKey(),entry.getValue());
        });
        payload.put("owner_id",owner);
        return ApiResponse.success(transport.models(payload));
    }
}
