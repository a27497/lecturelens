package com.example.courselingo.qa;

import static org.assertj.core.api.Assertions.*;
import static org.mockito.Mockito.*;

import com.example.courselingo.auth.dto.CurrentUserResponse;
import com.example.courselingo.auth.service.CurrentUserService;
import com.example.courselingo.common.web.GlobalExceptionHandler;
import com.example.courselingo.qa.service.DenseRetrievalProperties;
import com.example.courselingo.study.*;
import com.fasterxml.jackson.databind.*;
import com.sun.net.httpserver.HttpServer;
import java.net.*;
import java.net.http.*;
import java.nio.charset.StandardCharsets;
import java.nio.file.*;
import java.time.Duration;
import java.util.*;
import java.util.concurrent.TimeUnit;
import org.junit.jupiter.api.Test;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.request.MockMvcRequestBuilders;
import org.springframework.test.web.servlet.setup.MockMvcBuilders;

/** Real gateway/authority/HTTP/ASGI/PG; only identity facts, retrieval and model are Mock. */
class TutorUsableCrossServiceIT {
    private final ObjectMapper json=new ObjectMapper();
    private JsonNode invoke(MockMvc mvc,String method,String path,String body) throws Exception {
        var request=MockMvcRequestBuilders.request(org.springframework.http.HttpMethod.valueOf(method),path)
            .header("Authorization","Bearer synthetic-owner").contentType("application/json");
        if(body!=null) request.content(body);
        var result=mvc.perform(request).andReturn().getResponse();
        assertThat(result.getStatus()).as(path).isEqualTo(200);
        return json.readTree(result.getContentAsString()).path("data");
    }
    @Test void gatewayToNewFactoryCompleteEvidencePersistenceReplayAndAuthority() throws Exception {
        Path root=Path.of(System.getProperty("tutor.phase.root"));
        Path phase=root.resolve(".data/tutor-usability-v18").resolve(System.getProperty("tutor.phase.label","cross-service-check"));
        Files.createDirectories(phase);
        var lab=new StudyAuthorityTest();lab.setup();
        String raw="values = ['alpha', 'beta']\nprint(values[0])\nThe first value is alpha.";
        var item=TutorCompleteEvidenceTest.source("e1",raw,false);
        when(lab.evidence.current("task",42L)).thenReturn(List.of(item));
        when(lab.dense.retrieve(eq("task"),eq(42L),anyList(),anyString(),isNull(),isNull(),eq(4))).thenReturn(List.of(item));
        var users=mock(CurrentUserService.class);
        when(users.currentUser("Bearer synthetic-owner")).thenReturn(new CurrentUserResponse(42L,"synthetic@test.invalid","ACTIVE"));
        var properties=new StudyProperties();properties.setEnabled(true);
        int pythonPort;
        try(var available=new java.net.ServerSocket(0,0,InetAddress.getLoopbackAddress())) { pythonPort=available.getLocalPort(); }
        var config=new DenseRetrievalProperties();config.setBaseUrl("http://127.0.0.1:"+pythonPort);
        config.setServiceSecret("phase-synthetic-service-secret-32-minimum");
        try(var transport=new StudyTransport(config,json)) {
            var mvc=MockMvcBuilders.standaloneSetup(new TutorController(users,properties,lab.authority,transport),
                new StudyController(users,properties,lab.authority,transport,json)).setControllerAdvice(new GlobalExceptionHandler()).build();
            var javaServer=HttpServer.create(new InetSocketAddress("127.0.0.1",0),0);
            javaServer.createContext("/internal/v1/study/evidence", exchange->{
                try {
                    byte[] body=exchange.getRequestBody().readAllBytes();
                    var request=MockMvcRequestBuilders.post("/internal/v1/study/evidence").contentType("application/json").content(body);
                    exchange.getRequestHeaders().forEach((name,values)->values.forEach(v->request.header(name,v)));
                    var response=mvc.perform(request).andReturn().getResponse();
                    byte[] output=response.getContentAsByteArray();
                    exchange.getResponseHeaders().set("Content-Type","application/json");
                    exchange.sendResponseHeaders(response.getStatus(),output.length);exchange.getResponseBody().write(output);
                } catch(Exception error) { throw new RuntimeException(error); }
                finally { exchange.close(); }
            });
            javaServer.start();
            var command=List.of(root.resolve("agent-service/.venv/bin/python").toString(),root.resolve("eval/tutor-scale/safe_exec.py").toString(),
                phase.resolve("network-cross-service").toString(),root.resolve("scripts/dev/serve_tutor_usable_mock.py").toString(),
                "--port",Integer.toString(pythonPort),"--java-url","http://127.0.0.1:"+javaServer.getAddress().getPort(),
                "--output",phase.resolve("cross-service").toString());
            var builder=new ProcessBuilder(command).directory(root.toFile()).redirectErrorStream(true).redirectOutput(phase.resolve("cross-service-python.log").toFile());
            builder.environment().clear();builder.environment().put("PATH","/opt/node/bin:/usr/bin:/bin");builder.environment().put("HOME",root.resolve(".data").toString());
            var python=builder.start();
            try {
                boolean ready=false;
                try(var client=HttpClient.newBuilder().version(HttpClient.Version.HTTP_1_1).connectTimeout(Duration.ofSeconds(1)).build()) {
                    for(int n=0;n<100 && python.isAlive();n++) {
                        try {
                            var response=client.send(HttpRequest.newBuilder(URI.create("http://127.0.0.1:"+pythonPort+"/healthz")).timeout(Duration.ofSeconds(1)).build(),HttpResponse.BodyHandlers.discarding());
                            if(response.statusCode()==200) { ready=true;break; }
                        } catch(Exception ignored) { /* Startup only; never retry model I/O. */ }
                        Thread.sleep(100);
                    }
                }
                assertThat(ready).as("isolated Python ready").isTrue();
                String base="/api/tasks/task/tutor/sessions";
                String sid=invoke(mvc,"POST",base,"{\"request_key\":\"phase-session\"}").path("session").path("session_id").asText();
                String body="{\"client_turn_id\":\"phase-turn\",\"text\":\"Explain values indexing\",\"socratic\":false}";
                invoke(mvc,"POST",base+"/"+sid+"/turns",body);
                JsonNode saved=null;
                for(int n=0;n<100;n++) {
                    saved=invoke(mvc,"GET",base+"/"+sid,null);
                    if(saved.path("turns").path(0).path("status").asText().equals("completed")) break;
                    Thread.sleep(100);
                }
                assertThat(saved.path("turns").path(0).path("status").asText()).isEqualTo("completed");
                assertThat(saved.path("turns").path(0).path("answer").asText()).contains("values[0]").doesNotContain("values(0)");
                assertThat(saved.path("turns").path(0).path("citations").path(0).path("text").asText()).isEqualTo(raw);
                int calls=saved.path("session").path("model_calls").asInt();
                var replay=invoke(mvc,"POST",base+"/"+sid+"/turns",body);
                assertThat(replay.path("replayed").asBoolean()).isTrue();
                assertThat(replay.path("session").path("model_calls").asInt()).isEqualTo(calls);
                assertThat(replay.path("turns")).hasSize(1);
                invoke(mvc,"POST",base+"/"+sid+"/turns/phase-turn/cancel","{}");
                var completed=invoke(mvc,"GET",base+"/"+sid,null);
                assertThat(completed.path("turns").path(0).path("status").asText()).isEqualTo("completed");
                String second=invoke(mvc,"POST",base,"{\"request_key\":\"isolated-session\"}").path("session").path("session_id").asText();
                assertThat(second).isNotEqualTo(sid);
                assertThat(invoke(mvc,"GET",base+"/"+second,null).path("turns")).isEmpty();
                invoke(mvc,"POST",base+"/"+second+"/turns",body);
                JsonNode separate=null;
                for(int n=0;n<100;n++) {
                    separate=invoke(mvc,"GET",base+"/"+second,null);
                    if(separate.path("turns").path(0).path("status").asText().equals("completed")) break;
                    Thread.sleep(100);
                }
                assertThat(separate.path("turns").path(0).path("status").asText()).isEqualTo("completed");
                assertThat(separate.path("turns").path(0).path("turn_id").asText()).isNotEqualTo(completed.path("turns").path(0).path("turn_id").asText());
                assertThat(invoke(mvc,"GET",base+"/"+sid,null).path("session").path("model_calls").asInt()).isEqualTo(calls);
                Files.writeString(phase.resolve("cross-service-view.json"),json.writerWithDefaultPrettyPrinter().writeValueAsString(completed));
                lab.jdbc.update("UPDATE analysis_task SET content_revision=2");
                var stale=mvc.perform(MockMvcRequestBuilders.get(base+"/"+sid).header("Authorization","Bearer synthetic-owner")).andReturn().getResponse();
                assertThat(stale.getStatus()).isEqualTo(409);
                when(users.currentUser("Bearer synthetic-other")).thenReturn(new CurrentUserResponse(99L,"other@test.invalid","ACTIVE"));
                assertThat(mvc.perform(MockMvcRequestBuilders.get(base+"/"+sid).header("Authorization","Bearer synthetic-other")).andReturn().getResponse().getStatus()).isEqualTo(404);
            } finally {
                python.destroy();
                if(!python.waitFor(20,TimeUnit.SECONDS)) { python.destroyForcibly();python.waitFor(); }
                javaServer.stop(0);
            }
            // A signal exit is acceptable only when the required export below
            // proves the scoped child's final cleanup actually completed.
            assertThat(python.exitValue()).isIn(0,143);
            var record=json.readTree(phase.resolve("cross-service/runtime.json").toFile());
            assertThat(record.path("real_model_calls").asInt()).isZero();
            assertThat(record.path("embedding_calls").asInt()).isZero();
            assertThat(record.path("turns")).hasSize(2);
            assertThat(record.path("provider").asText()).isEqualTo("UsableMock");
            assertThat(record.path("turns").path(0).path(5).asText()).isEqualTo("p8-tutor-usable-v18-development");
        }
    }
}
