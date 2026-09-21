package com.example.courselingo.qa;

import static org.assertj.core.api.Assertions.*;
import static org.mockito.Mockito.*;

import com.example.courselingo.auth.dto.CurrentUserResponse;
import com.example.courselingo.auth.service.CurrentUserService;
import com.example.courselingo.common.error.ErrorCode;
import com.example.courselingo.common.exception.BusinessException;
import com.example.courselingo.qa.service.DenseRetrievalProperties;
import com.example.courselingo.study.*;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.sun.net.httpserver.HttpServer;
import java.net.InetSocketAddress;
import java.nio.charset.StandardCharsets;
import java.util.Map;
import java.util.concurrent.atomic.AtomicReference;
import org.junit.jupiter.api.Test;

class ModelManagementTest {
    @Test void ownerIsInjectedAndCannotBeSuppliedByBrowser() throws Exception {
        var users=mock(CurrentUserService.class);
        var user=mock(CurrentUserResponse.class);
        when(user.userId()).thenReturn(42L);
        when(users.currentUser("Bearer test")).thenReturn(user);
        var properties=new StudyProperties(); properties.setEnabled(true);
        var transport=mock(StudyTransport.class);
        var json=new ObjectMapper();
        when(transport.models(anyMap())).thenReturn(json.createObjectNode().put("owner_id",42));
        var controller=new ModelManagementController(users,properties,transport);
        controller.command("Bearer test",json.readTree("{\"operation\":\"LIST\"}"));
        var capture=org.mockito.ArgumentCaptor.forClass(Map.class);
        verify(transport).models(capture.capture());
        assertThat(capture.getValue().get("owner_id")).isEqualTo(42L);
        assertThatThrownBy(()->controller.command("Bearer test",json.readTree("{\"operation\":\"LIST\",\"owner_id\":99}"))).isInstanceOf(BusinessException.class);
        verifyNoMoreInteractions(transport);
    }

    @Test void transportBindsSignatureToModelPathAndRejectsWrongOwner() throws Exception {
        var json=new ObjectMapper();
        var properties=new DenseRetrievalProperties();
        properties.setServiceSecret("test-model-service-signing-secret-32-bytes");
        var server=HttpServer.create(new InetSocketAddress("127.0.0.1",0),0);
        properties.setBaseUrl("http://127.0.0.1:"+server.getAddress().getPort());
        var response=new AtomicReference<>("{\"owner_id\":42,\"connections\":[]}");
        var received=new AtomicReference<byte[]>();
        var signature=new AtomicReference<String>();
        var timestamp=new AtomicReference<String>();
        server.createContext("/internal/v1/models/command",exchange->{
            received.set(exchange.getRequestBody().readAllBytes());
            signature.set(exchange.getRequestHeaders().getFirst("X-LectureLens-Signature"));
            timestamp.set(exchange.getRequestHeaders().getFirst("X-LectureLens-Timestamp"));
            byte[] body=response.get().getBytes(StandardCharsets.UTF_8);
            exchange.sendResponseHeaders(200,body.length);exchange.getResponseBody().write(body);exchange.close();
        });
        server.start();
        try(var transport=new StudyTransport(properties,json)) {
            assertThat(transport.models(Map.of("owner_id",42L,"operation","LIST")).path("connections").isArray()).isTrue();
            assertThat(signature.get()).isEqualTo(transport.signature("/internal/v1/models/command",timestamp.get(),received.get()));
            assertThat(signature.get()).isNotEqualTo(transport.signature("/internal/v1/study/command",timestamp.get(),received.get()));
            response.set("{\"owner_id\":99}");
            assertThatThrownBy(()->transport.models(Map.of("owner_id",42L,"operation","LIST"))).isInstanceOf(BusinessException.class);
        } finally { server.stop(0); }
    }

    @Test void unstructuredCourseErrorsKeepExistingStatusMapping() throws Exception {
        var server=HttpServer.create(new InetSocketAddress("127.0.0.1",0),0);
        server.createContext("/internal/v1/study/command",exchange->{exchange.sendResponseHeaders(404,-1);exchange.close();});
        server.start();
        var properties=new DenseRetrievalProperties();properties.setBaseUrl("http://127.0.0.1:"+server.getAddress().getPort());properties.setServiceSecret("test-model-service-signing-secret-32-bytes");
        try(var transport=new StudyTransport(properties,new ObjectMapper())) {
            assertThatThrownBy(()->transport.command(Map.of("owner_id",42L,"course_id","course","revision",1)))
                .isInstanceOfSatisfying(BusinessException.class,error->assertThat(error.errorCode()).isEqualTo(ErrorCode.STUDY_NOT_FOUND));
        } finally { server.stop(0); }
    }
}
