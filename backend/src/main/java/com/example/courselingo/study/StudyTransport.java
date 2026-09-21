package com.example.courselingo.study;

import com.example.courselingo.common.error.ErrorCode;
import com.example.courselingo.common.exception.BusinessException;
import com.example.courselingo.qa.service.DenseRetrievalProperties;
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import java.net.URI;
import java.net.http.*;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.time.Duration;
import java.time.Instant;
import java.util.HexFormat;
import java.util.Map;
import javax.crypto.Mac;
import javax.crypto.spec.SecretKeySpec;
import org.springframework.stereotype.Component;

@Component
public class StudyTransport implements AutoCloseable {
    private final DenseRetrievalProperties properties;
    private final ObjectMapper json;
    private final HttpClient http=HttpClient.newBuilder().version(HttpClient.Version.HTTP_1_1).connectTimeout(Duration.ofSeconds(3)).build();
    public StudyTransport(DenseRetrievalProperties properties,ObjectMapper json) { this.properties=properties; this.json=json; }

    public String signature(String path,String timestamp,byte[] body) throws Exception {
        byte[] key=properties.getServiceSecret().getBytes(StandardCharsets.UTF_8);
        if (key.length<32) throw new IllegalStateException("Study execution key missing");
        String digest=HexFormat.of().formatHex(MessageDigest.getInstance("SHA-256").digest(body));
        Mac mac=Mac.getInstance("HmacSHA256");
        mac.init(new SecretKeySpec(key,"HmacSHA256"));
        return HexFormat.of().formatHex(mac.doFinal(("lecturelens-study-v1\nPOST\n"+path+"\n"+timestamp+"\n"+digest).getBytes(StandardCharsets.UTF_8)));
    }

    public void verify(String path,String timestamp,String supplied,byte[] body) {
        try {
            if (timestamp==null || supplied==null || !supplied.matches("[0-9a-f]{64}")
                || Math.abs(Instant.now().getEpochSecond()-Long.parseLong(timestamp))>60
                || !MessageDigest.isEqual(signature(path,timestamp,body).getBytes(StandardCharsets.UTF_8),supplied.getBytes(StandardCharsets.UTF_8))) {
                throw new IllegalArgumentException("Invalid execution context");
            }
        } catch (Exception e) { throw new BusinessException(ErrorCode.COMMON_UNAUTHORIZED); }
    }

    public JsonNode command(Map<String,Object> payload) {
        return invoke("/internal/v1/study/command",payload,true);
    }

    public JsonNode models(Map<String,Object> payload) {
        return invoke("/internal/v1/models/command",payload,false);
    }

    private JsonNode invoke(String path,Map<String,Object> payload,boolean courseScope) {
        try {
            byte[] body=json.writeValueAsBytes(payload);
            String timestamp=Long.toString(Instant.now().getEpochSecond());
            var request=HttpRequest.newBuilder(URI.create(properties.getBaseUrl().replaceAll("/+$","")+path))
                .timeout(Duration.ofSeconds(15)).header("Content-Type","application/json")
                .header("X-LectureLens-Timestamp",timestamp).header("X-LectureLens-Signature",signature(path,timestamp,body))
                .POST(HttpRequest.BodyPublishers.ofByteArray(body)).build();
            var response=http.send(request,HttpResponse.BodyHandlers.ofString(StandardCharsets.UTF_8));
            if (response.statusCode()!=200) {
                String code="";
                try { var diagnostic=json.readTree(response.body()); if(diagnostic!=null) code=diagnostic.path("detail").asText(""); }
                catch(Exception ignored) { /* Never reflect an unstructured provider error body. */ }
                boolean studyDiagnostic=java.util.Set.of("ATTEMPT_VERSION_CONFLICT","REQUEST_KEY_CONFLICT",
                    "ARTIFACT_NOT_FOUND_OR_STALE","QUESTION_NOT_FOUND","FEEDBACK_DISABLED","ATTEMPT_NOT_FOUND",
                    "FEEDBACK_NOT_FOUND","FEEDBACK_VERSION_CONFLICT","SESSION_BUSY").contains(code);
                if (!courseScope || code.matches("MODEL_[A-Z_]{1,70}") || studyDiagnostic) {
                    if (!code.matches("MODEL_[A-Z_]{1,70}") && !studyDiagnostic) code="MODEL_MANAGEMENT_UNAVAILABLE";
                    throw new BusinessException(response.statusCode()==404 ? ErrorCode.STUDY_NOT_FOUND
                        : response.statusCode()==409 ? ErrorCode.STUDY_CONFLICT
                        : response.statusCode()==422 ? ErrorCode.COMMON_BAD_REQUEST : ErrorCode.STUDY_UNAVAILABLE,code);
                }
            }
            if (response.statusCode()==404) throw new BusinessException(ErrorCode.STUDY_NOT_FOUND);
            if (response.statusCode()==409) throw new BusinessException(ErrorCode.STUDY_CONFLICT);
            if (response.statusCode()!=200) throw new BusinessException(ErrorCode.STUDY_UNAVAILABLE);
            var result=json.readTree(response.body());
            if (!result.path("owner_id").isIntegralNumber() || result.path("owner_id").asLong()!=((Number)payload.get("owner_id")).longValue()
                    || (courseScope && (!result.path("course_id").asText().equals(payload.get("course_id"))
                    || !result.path("revision").isIntegralNumber() || result.path("revision").asLong()!=((Number)payload.get("revision")).longValue()))) {
                throw new BusinessException(ErrorCode.STUDY_UNAVAILABLE);
            }
            return result;
        } catch (BusinessException e) { throw e; }
        catch (InterruptedException e) { Thread.currentThread().interrupt(); throw new BusinessException(ErrorCode.STUDY_UNAVAILABLE); }
        catch (Exception e) { throw new BusinessException(ErrorCode.STUDY_UNAVAILABLE); }
    }

    @jakarta.annotation.PreDestroy public void close() { http.close(); }
}
