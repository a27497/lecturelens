package com.example.courselingo.mq;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import com.example.courselingo.common.error.ErrorCode;
import com.example.courselingo.common.exception.BusinessException;
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import java.nio.charset.StandardCharsets;
import java.time.Instant;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;

class RocketMqAnalysisTaskMessageProducerTest {

    private static final ObjectMapper OBJECT_MAPPER = new ObjectMapper().findAndRegisterModules();

    private CapturingRocketMqMessageSender sender;
    private RocketMqAnalysisTaskMessageProducer producer;

    @BeforeEach
    void setUp() {
        sender = new CapturingRocketMqMessageSender();
        producer = new RocketMqAnalysisTaskMessageProducer(
            sender,
            OBJECT_MAPPER,
            new RocketMqProducerProperties(
                "127.0.0.1:9876",
                "127.0.0.1:8081",
                "courselingo-analysis-producer-group",
                "courselingo-analysis-task",
                3000,
                false,
                true
            )
        );
    }

    @Test
    void sendsAnalysisCreatedWithFixedTopicKeyTagAndJsonBody() throws Exception {
        producer.send(AnalysisTaskMessageTag.ANALYSIS_CREATED, validMessage());

        assertThat(sender.topic).isEqualTo("courselingo-analysis-task");
        assertThat(sender.tag).isEqualTo("ANALYSIS_CREATED");
        assertThat(sender.key).isEqualTo("task_1");

        JsonNode body = OBJECT_MAPPER.readTree(new String(sender.body, StandardCharsets.UTF_8));
        assertThat(body.get("taskId").asText()).isEqualTo("task_1");
        assertThat(body.get("uploadId").asText()).isEqualTo("up_1");
        assertThat(body.get("userId").asLong()).isEqualTo(1L);
        assertThat(body.get("targetLanguage").asText()).isEqualTo("zh-CN");
        assertThat(body.get("requestId").asText()).isEqualTo("req_1");
        assertThat(body.get("traceId").asText()).isEqualTo("trace_1");
        assertThat(body.get("createdAt").asText()).isEqualTo("2026-06-27T10:00:00Z");
        assertThat(body.has("protocolVersion")).isFalse();
        assertThat(body.has("executionEpoch")).isFalse();
        assertThat(body.toString())
            .doesNotContainIgnoringCase("authorization")
            .doesNotContainIgnoringCase("cookie")
            .doesNotContainIgnoringCase("secret")
            .doesNotContainIgnoringCase("api_key")
            .doesNotContainIgnoringCase("objectKey")
            .doesNotContainIgnoringCase("rawPrompt")
            .doesNotContain("C:\\");
    }

    @Test
    void supportsRetryAndCancelTags() {
        producer.send(AnalysisTaskMessageTag.ANALYSIS_RETRY, validMessage());
        assertThat(sender.tag).isEqualTo("ANALYSIS_RETRY");

        producer.send(AnalysisTaskMessageTag.ANALYSIS_CANCEL, validMessage());
        assertThat(sender.tag).isEqualTo("ANALYSIS_CANCEL");
    }

    @Test
    void preservesCheckpointProtocolAndEpochAcrossTheActualProducerConsumerWire() {
        var properties = new RocketMqProducerProperties("127.0.0.1:9876", "127.0.0.1:8081",
            "courselingo-analysis-producer-group", "courselingo-analysis-task", 3000, false, true);
        for (var tag : AnalysisTaskMessageTag.values()) {
            for (long epoch : new long[] {1, 7}) {
                var expected = validMessage().withExecution(epoch);
                var received = new java.util.concurrent.atomic.AtomicReference<AnalysisTaskMessage>();
                var receivedTag = new java.util.concurrent.atomic.AtomicReference<AnalysisTaskMessageTag>();
                var consumer = new RocketMqAnalysisTaskMessageConsumer(OBJECT_MAPPER, (actualTag, actual) -> {
                    receivedTag.set(actualTag);
                    received.set(actual);
                }, properties);
                producer.send(tag, expected);
                var result = consumer.consume(new RocketMqInboundMessage(sender.topic, sender.tag, sender.key, sender.body));

                assertThat(result.status()).isEqualTo(ConsumerProcessResult.Status.SUCCESS);
                assertThat(receivedTag.get()).isEqualTo(tag);
                assertThat(received.get()).isEqualTo(expected);
                assertThat(received.get().protocol()).isEqualTo(2);
                assertThat(received.get().epoch()).isEqualTo(epoch);
            }
        }
    }

    @Test
    void wrapsRocketMqSendFailureAndDoesNotLeakSecretsInMessage() {
        sender.failure = new RuntimeException("secretKey=abc api key=xyz access token=raw refresh token=raw");

        assertThatThrownBy(() -> producer.send(AnalysisTaskMessageTag.ANALYSIS_CREATED, validMessage()))
            .isInstanceOf(BusinessException.class)
            .satisfies(error -> {
                BusinessException exception = (BusinessException) error;
                assertThat(exception.errorCode()).isEqualTo(ErrorCode.MQ_SEND_FAILED);
                assertThat(exception.getMessage()).doesNotContainIgnoringCase("secret");
                assertThat(exception.getMessage()).doesNotContainIgnoringCase("api key");
                assertThat(exception.getMessage()).doesNotContainIgnoringCase("token");
            });
    }

    @Test
    void rejectsBlankTaskIdBeforeSending() {
        assertThatThrownBy(() -> producer.send(
            AnalysisTaskMessageTag.ANALYSIS_CREATED,
            new AnalysisTaskMessage(" ", "up_1", 1L, "zh-CN", "req_1", "trace_1", Instant.parse("2026-06-27T10:00:00Z"))
        ))
            .isInstanceOf(BusinessException.class)
            .extracting("errorCode")
            .isEqualTo(ErrorCode.COMMON_VALIDATION_FAILED);

        assertThat(sender.body).isNull();
    }

    private static AnalysisTaskMessage validMessage() {
        return new AnalysisTaskMessage(
            "task_1",
            "up_1",
            1L,
            "zh-CN",
            "req_1",
            "trace_1",
            Instant.parse("2026-06-27T10:00:00Z")
        );
    }

    private static class CapturingRocketMqMessageSender implements RocketMqMessageSender {

        private String topic;
        private String tag;
        private String key;
        private byte[] body;
        private RuntimeException failure;

        @Override
        public void send(String topic, String tag, String key, byte[] body) {
            if (failure != null) {
                throw failure;
            }
            this.topic = topic;
            this.tag = tag;
            this.key = key;
            this.body = body;
        }
    }
}
