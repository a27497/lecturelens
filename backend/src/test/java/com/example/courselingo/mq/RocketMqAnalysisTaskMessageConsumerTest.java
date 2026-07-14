package com.example.courselingo.mq;

import static org.assertj.core.api.Assertions.assertThat;

import com.example.courselingo.common.error.ErrorCode;
import com.example.courselingo.common.exception.BusinessException;
import com.fasterxml.jackson.databind.ObjectMapper;
import java.nio.ByteBuffer;
import java.nio.charset.StandardCharsets;
import java.util.Collection;
import java.util.Map;
import java.util.Optional;
import org.apache.rocketmq.client.apis.consumer.ConsumeResult;
import org.apache.rocketmq.client.apis.message.MessageId;
import org.apache.rocketmq.client.apis.message.MessageView;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;

class RocketMqAnalysisTaskMessageConsumerTest {

    private static final ObjectMapper OBJECT_MAPPER = new ObjectMapper().findAndRegisterModules();

    private CapturingAnalysisTaskMessageHandler handler;
    private RocketMqAnalysisTaskMessageConsumer consumer;

    @BeforeEach
    void setUp() {
        handler = new CapturingAnalysisTaskMessageHandler();
        consumer = new RocketMqAnalysisTaskMessageConsumer(
            OBJECT_MAPPER,
            handler,
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
    void parsesValidJsonAndDispatchesAnalysisCreated() {
        ConsumerProcessResult result = consumer.consume(envelope("ANALYSIS_CREATED", "task_1", validJson()));

        assertThat(result.status()).isEqualTo(ConsumerProcessResult.Status.SUCCESS);
        assertThat(handler.tag).isEqualTo(AnalysisTaskMessageTag.ANALYSIS_CREATED);
        assertThat(handler.message.taskId()).isEqualTo("task_1");
        assertThat(handler.message.uploadId()).isEqualTo("up_1");
        assertThat(handler.message.userId()).isEqualTo(1L);
        assertThat(handler.message.targetLanguage()).isEqualTo("zh-CN");
        assertThat(handler.message.requestId()).isEqualTo("req_1");
        assertThat(handler.message.traceId()).isEqualTo("trace_1");
        assertThat(handler.message.createdAt().toString()).isEqualTo("2026-06-27T10:00:00Z");
    }

    @Test
    void supportsRetryAndCancelTags() {
        assertThat(consumer.consume(envelope("ANALYSIS_RETRY", "task_1", validJson())))
            .extracting(ConsumerProcessResult::status)
            .isEqualTo(ConsumerProcessResult.Status.SUCCESS);
        assertThat(handler.tag).isEqualTo(AnalysisTaskMessageTag.ANALYSIS_RETRY);

        assertThat(consumer.consume(envelope("ANALYSIS_CANCEL", "task_1", validJson())))
            .extracting(ConsumerProcessResult::status)
            .isEqualTo(ConsumerProcessResult.Status.SUCCESS);
        assertThat(handler.tag).isEqualTo(AnalysisTaskMessageTag.ANALYSIS_CANCEL);
    }

    @Test
    void rejectsUnknownTag() {
        ConsumerProcessResult result = consumer.consume(envelope("UNKNOWN", "task_1", validJson()));

        assertFailure(result, ErrorCode.MQ_MESSAGE_INVALID);
        assertThat(handler.message).isNull();
    }

    @Test
    void rejectsMismatchedTopic() {
        ConsumerProcessResult result = consumer.consume(new RocketMqInboundMessage(
            "other-topic",
            "ANALYSIS_CREATED",
            "task_1",
            validJson().getBytes(StandardCharsets.UTF_8)
        ));

        assertFailure(result, ErrorCode.MQ_MESSAGE_INVALID);
        assertThat(handler.message).isNull();
    }

    @Test
    void rejectsBlankMessageKey() {
        ConsumerProcessResult result = consumer.consume(envelope("ANALYSIS_CREATED", " ", validJson()));

        assertFailure(result, ErrorCode.MQ_MESSAGE_INVALID);
        assertThat(handler.message).isNull();
    }

    @Test
    void rejectsMessageKeyThatDoesNotMatchBodyTaskId() {
        ConsumerProcessResult result = consumer.consume(envelope("ANALYSIS_CREATED", "other_task", validJson()));

        assertFailure(result, ErrorCode.MQ_MESSAGE_INVALID);
        assertThat(handler.message).isNull();
    }

    @Test
    void rejectsInvalidJson() {
        ConsumerProcessResult result = consumer.consume(envelope("ANALYSIS_CREATED", "task_1", "{"));

        assertFailure(result, ErrorCode.MQ_MESSAGE_INVALID);
        assertThat(result.errorMessage()).doesNotContainIgnoringCase("secret");
        assertThat(result.errorMessage()).doesNotContainIgnoringCase("token");
        assertThat(result.errorMessage()).doesNotContainIgnoringCase("api key");
    }

    @Test
    void rejectsMissingRequiredFields() {
        assertFailure(consumer.consume(envelope("ANALYSIS_CREATED", "task_1", jsonWithout("taskId"))),
            ErrorCode.MQ_MESSAGE_INVALID);
        assertFailure(consumer.consume(envelope("ANALYSIS_CREATED", "task_1", jsonWithout("uploadId"))),
            ErrorCode.MQ_MESSAGE_INVALID);
        assertFailure(consumer.consume(envelope("ANALYSIS_CREATED", "task_1", jsonWithout("userId"))),
            ErrorCode.MQ_MESSAGE_INVALID);
        assertFailure(consumer.consume(envelope("ANALYSIS_CREATED", "task_1", jsonWithout("targetLanguage"))),
            ErrorCode.MQ_MESSAGE_INVALID);
        assertFailure(consumer.consume(envelope("ANALYSIS_CREATED", "task_1", jsonWithout("requestId"))),
            ErrorCode.MQ_MESSAGE_INVALID);
        assertFailure(consumer.consume(envelope("ANALYSIS_CREATED", "task_1", jsonWithout("traceId"))),
            ErrorCode.MQ_MESSAGE_INVALID);
        assertFailure(consumer.consume(envelope("ANALYSIS_CREATED", "task_1", jsonWithout("createdAt"))),
            ErrorCode.MQ_MESSAGE_INVALID);
    }

    @Test
    void returnsRetryableFailureWhenHandlerThrows() {
        handler.failure = new IllegalStateException("secretKey=abc access token=raw api key=xyz");

        ConsumerProcessResult result = consumer.consume(envelope("ANALYSIS_CREATED", "task_1", validJson()));

        assertThat(result.status()).isEqualTo(ConsumerProcessResult.Status.RETRY);
        assertThat(result.errorCode()).isEqualTo(ErrorCode.MQ_CONSUME_FAILED);
        assertThat(result.errorMessage()).doesNotContainIgnoringCase("secret");
        assertThat(result.errorMessage()).doesNotContainIgnoringCase("token");
        assertThat(result.errorMessage()).doesNotContainIgnoringCase("api key");
    }

    @Test
    void acknowledgesDirtyBusinessMessageWithoutRocketMqRetry() {
        handler.failure = new BusinessException(ErrorCode.TASK_INVALID_STATUS, "task is already FAILED");

        ConsumerProcessResult result = consumer.consume(envelope("ANALYSIS_CREATED", "task_1", validJson()));

        assertThat(result.status()).isEqualTo(ConsumerProcessResult.Status.SUCCESS);
    }

    @Test
    void listenerReturnsRocketMqFailureForRetryableResult() {
        RocketMqMessageListener listener = new RocketMqMessageListener(message -> ConsumerProcessResult.retry(
            ErrorCode.MQ_CONSUME_FAILED,
            "消息消费失败"
        ));

        ConsumeResult result = listener.consume(new TestMessageView(
            "courselingo-analysis-task",
            "ANALYSIS_CREATED",
            "task_1",
            validJson().getBytes(StandardCharsets.UTF_8)
        ));

        assertThat(result).isEqualTo(ConsumeResult.FAILURE);
    }

    private static void assertFailure(ConsumerProcessResult result, ErrorCode errorCode) {
        assertThat(result.status()).isEqualTo(ConsumerProcessResult.Status.FAIL);
        assertThat(result.errorCode()).isEqualTo(errorCode);
    }

    private static RocketMqInboundMessage envelope(String tag, String key, String body) {
        return new RocketMqInboundMessage(
            "courselingo-analysis-task",
            tag,
            key,
            body.getBytes(StandardCharsets.UTF_8)
        );
    }

    private static String jsonWithout(String fieldName) {
        return switch (fieldName) {
            case "taskId" -> """
                {"uploadId":"up_1","userId":1,"targetLanguage":"zh-CN","requestId":"req_1","traceId":"trace_1","createdAt":"2026-06-27T10:00:00Z"}
                """;
            case "uploadId" -> """
                {"taskId":"task_1","userId":1,"targetLanguage":"zh-CN","requestId":"req_1","traceId":"trace_1","createdAt":"2026-06-27T10:00:00Z"}
                """;
            case "userId" -> """
                {"taskId":"task_1","uploadId":"up_1","targetLanguage":"zh-CN","requestId":"req_1","traceId":"trace_1","createdAt":"2026-06-27T10:00:00Z"}
                """;
            case "targetLanguage" -> """
                {"taskId":"task_1","uploadId":"up_1","userId":1,"requestId":"req_1","traceId":"trace_1","createdAt":"2026-06-27T10:00:00Z"}
                """;
            case "requestId" -> """
                {"taskId":"task_1","uploadId":"up_1","userId":1,"targetLanguage":"zh-CN","traceId":"trace_1","createdAt":"2026-06-27T10:00:00Z"}
                """;
            case "traceId" -> """
                {"taskId":"task_1","uploadId":"up_1","userId":1,"targetLanguage":"zh-CN","requestId":"req_1","createdAt":"2026-06-27T10:00:00Z"}
                """;
            case "createdAt" -> """
                {"taskId":"task_1","uploadId":"up_1","userId":1,"targetLanguage":"zh-CN","requestId":"req_1","traceId":"trace_1"}
                """;
            default -> throw new IllegalArgumentException(fieldName);
        };
    }

    private static String validJson() {
        return """
            {
              "taskId": "task_1",
              "uploadId": "up_1",
              "userId": 1,
              "targetLanguage": "zh-CN",
              "requestId": "req_1",
              "traceId": "trace_1",
              "createdAt": "2026-06-27T10:00:00Z"
            }
            """;
    }

    private static class CapturingAnalysisTaskMessageHandler implements AnalysisTaskMessageHandler {

        private AnalysisTaskMessageTag tag;
        private AnalysisTaskMessage message;
        private RuntimeException failure;

        @Override
        public void handle(AnalysisTaskMessageTag tag, AnalysisTaskMessage message) {
            if (failure != null) {
                throw failure;
            }
            this.tag = tag;
            this.message = message;
        }
    }

    private record TestMessageView(
        String topic,
        String tag,
        String key,
        byte[] body
    ) implements MessageView {

        @Override
        public MessageId getMessageId() {
            return null;
        }

        @Override
        public String getTopic() {
            return topic;
        }

        @Override
        public ByteBuffer getBody() {
            return ByteBuffer.wrap(body);
        }

        @Override
        public Map<String, String> getProperties() {
            return Map.of();
        }

        @Override
        public Optional<String> getTag() {
            return Optional.ofNullable(tag);
        }

        @Override
        public Collection<String> getKeys() {
            return key == null ? java.util.List.of() : java.util.List.of(key);
        }

        @Override
        public Optional<String> getMessageGroup() {
            return Optional.empty();
        }

        @Override
        public Optional<Long> getDeliveryTimestamp() {
            return Optional.empty();
        }

        @Override
        public String getBornHost() {
            return "127.0.0.1";
        }

        @Override
        public long getBornTimestamp() {
            return 0;
        }

        @Override
        public int getDeliveryAttempt() {
            return 1;
        }
    }
}
