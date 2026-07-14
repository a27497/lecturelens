package com.example.courselingo.mq;

import com.example.courselingo.common.error.ErrorCode;
import com.example.courselingo.common.exception.BusinessException;
import com.example.courselingo.common.logging.SafeLogSanitizer;
import com.example.courselingo.common.metrics.BusinessMetrics;
import com.example.courselingo.common.tracing.TracingContext;
import com.example.courselingo.common.tracing.TracingContextHolder;
import com.example.courselingo.common.tracing.TracingScope;
import com.fasterxml.jackson.databind.ObjectMapper;
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import org.springframework.beans.factory.annotation.Autowired;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Service;

@Service
public class RocketMqAnalysisTaskMessageConsumer implements AnalysisTaskMessageConsumer {

    private static final Logger log = LoggerFactory.getLogger(RocketMqAnalysisTaskMessageConsumer.class);

    private static final String SAFE_INVALID_MESSAGE = "消息内容不合法";
    private static final String SAFE_CONSUME_FAILED = "消息消费失败";

    private final ObjectMapper objectMapper;
    private final AnalysisTaskMessageHandler handler;
    private final RocketMqProducerProperties properties;
    private final BusinessMetrics businessMetrics;

    @Autowired
    public RocketMqAnalysisTaskMessageConsumer(
        ObjectMapper objectMapper,
        AnalysisTaskMessageHandler handler,
        RocketMqProducerProperties properties,
        BusinessMetrics businessMetrics
    ) {
        this.objectMapper = objectMapper;
        this.handler = handler;
        this.properties = properties;
        this.businessMetrics = businessMetrics == null ? BusinessMetrics.noop() : businessMetrics;
    }

    public RocketMqAnalysisTaskMessageConsumer(
        ObjectMapper objectMapper,
        AnalysisTaskMessageHandler handler,
        RocketMqProducerProperties properties
    ) {
        this(objectMapper, handler, properties, BusinessMetrics.noop());
    }

    @Override
    public ConsumerProcessResult consume(RocketMqInboundMessage inboundMessage) {
        AnalysisTaskMessageTag tag;
        AnalysisTaskMessage message;
        try {
            tag = validateTag(inboundMessage.tag());
            validateTopic(inboundMessage.topic());
            validateKey(inboundMessage.key());
            message = parseMessage(inboundMessage.body());
            message.validate();
            validateKeyMatchesTaskId(inboundMessage.key(), message.taskId());
        } catch (BusinessException exception) {
            log.warn("event=mq_message_consume_rejected outcome=failure errorCode={}", ErrorCode.MQ_MESSAGE_INVALID.code());
            businessMetrics.incrementMqConsumed(safeTopic(inboundMessage), safeTag(inboundMessage), "rejected");
            return ConsumerProcessResult.fail(ErrorCode.MQ_MESSAGE_INVALID, SAFE_INVALID_MESSAGE);
        }
        try (TracingScope ignored = TracingContextHolder.open(new TracingContext(message.traceId(), message.requestId()))) {
            try {
                log.info(
                    "event=mq_message_consume_requested taskId={} tag={} outcome=start",
                    SafeLogSanitizer.sanitize(message.taskId()),
                    tag.name()
                );
                handler.handle(tag, message);
                log.info(
                    "event=mq_message_consume_completed taskId={} tag={} outcome=success",
                    SafeLogSanitizer.sanitize(message.taskId()),
                    tag.name()
                );
                businessMetrics.incrementMqConsumed(properties.analysisTopic(), tag.name(), "success");
                return ConsumerProcessResult.SUCCESS;
            } catch (Exception exception) {
                if (isDirtyBusinessMessage(exception)) {
                    log.warn(
                        "event=mq_message_consume_dropped taskId={} tag={} outcome=success reason=dirty_business_message errorCode={} errorMessage={}",
                        SafeLogSanitizer.sanitize(message.taskId()),
                        tag.name(),
                        ((BusinessException) exception).errorCode().code(),
                        SafeLogSanitizer.sanitizeAndLimit(exception.getMessage())
                    );
                    businessMetrics.incrementMqConsumed(properties.analysisTopic(), tag.name(), "dropped");
                    return ConsumerProcessResult.SUCCESS;
                }
                log.warn(
                    "event=mq_message_consume_failed taskId={} tag={} outcome=failure errorMessage={}",
                    SafeLogSanitizer.sanitize(message.taskId()),
                    tag.name(),
                    SafeLogSanitizer.sanitizeAndLimit(exception.getMessage())
                );
                businessMetrics.incrementMqConsumed(properties.analysisTopic(), tag.name(), "failure");
                return ConsumerProcessResult.retry(ErrorCode.MQ_CONSUME_FAILED, SAFE_CONSUME_FAILED);
            }
        }
    }

    private static boolean isDirtyBusinessMessage(Exception exception) {
        if (!(exception instanceof BusinessException businessException)) {
            return false;
        }
        ErrorCode errorCode = businessException.errorCode();
        return errorCode == ErrorCode.TASK_INVALID_STATUS || errorCode == ErrorCode.TASK_NOT_FOUND;
    }

    private static String safeTopic(RocketMqInboundMessage inboundMessage) {
        return inboundMessage == null ? null : inboundMessage.topic();
    }

    private static String safeTag(RocketMqInboundMessage inboundMessage) {
        return inboundMessage == null ? null : inboundMessage.tag();
    }

    private AnalysisTaskMessageTag validateTag(String tag) {
        if (isBlank(tag)) {
            throw new BusinessException(ErrorCode.MQ_MESSAGE_INVALID);
        }
        try {
            return AnalysisTaskMessageTag.valueOf(tag);
        } catch (IllegalArgumentException exception) {
            throw new BusinessException(ErrorCode.MQ_MESSAGE_INVALID);
        }
    }

    private void validateTopic(String topic) {
        if (!properties.analysisTopic().equals(topic)) {
            throw new BusinessException(ErrorCode.MQ_MESSAGE_INVALID);
        }
    }

    private void validateKey(String key) {
        if (isBlank(key)) {
            throw new BusinessException(ErrorCode.MQ_MESSAGE_INVALID);
        }
    }

    private AnalysisTaskMessage parseMessage(byte[] body) {
        if (body == null || body.length == 0) {
            throw new BusinessException(ErrorCode.MQ_MESSAGE_INVALID);
        }
        try {
            return objectMapper.readValue(new String(body, StandardCharsets.UTF_8), AnalysisTaskMessage.class);
        } catch (IOException exception) {
            throw new BusinessException(ErrorCode.MQ_MESSAGE_INVALID);
        }
    }

    private void validateKeyMatchesTaskId(String key, String taskId) {
        if (!key.equals(taskId)) {
            throw new BusinessException(ErrorCode.MQ_MESSAGE_INVALID);
        }
    }

    private static boolean isBlank(String value) {
        return value == null || value.isBlank();
    }
}
