package com.example.courselingo.systemmodel;

import com.example.courselingo.common.response.ApiResponse;
import java.util.Arrays;
import java.util.List;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/admin/system-models")
public class SystemModelCapabilitiesController {
    @GetMapping("/capabilities")
    public ApiResponse<Capabilities> capabilities() {
        return ApiResponse.success(new Capabilities(
            List.of(SystemModelProtocol.values()),
            Arrays.stream(SystemModelFeature.values()).map(feature -> new Feature(feature.name(), feature.connected())).toList()
        ));
    }

    public record Capabilities(List<SystemModelProtocol> protocols, List<Feature> features) { }
    public record Feature(String key, boolean connected) { }
}
