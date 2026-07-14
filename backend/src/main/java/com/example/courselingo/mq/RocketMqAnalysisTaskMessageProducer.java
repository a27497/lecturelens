package com.example.courselingo.mq;

import com.example.courselingo.common.error.ErrorCode;
import com.example.courselingo.common.exception.BusinessException;
import com.example.courselingo.common.logging.SafeLogSanitizer;
import com.example.courselingo.common.metrics.BusinessMetrics;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.springframework.beans.factory.annotation.Autowired;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Service;

@Service
public class RocketMqAnalysisTaskMessageProducer implements AnalysisTaskMessageProducer {

    private static final Logger log = LoggerFactory.getLogger(RocketMqAnalysisTaskMessageProducer.class);

    private final RocketMqMessageSender sender;
    private final ObjectMapper objectMapper;
    private final RocketMqProducerProperties properties;
    private final BusinessMetrics businessMetrics;

    @Autowired
    public RocketMqAnalysisTaskMessageProducer(
        RocketMqMessageSender sender,
        ObjectMapper objectMapper,
        RocketMqProducerProperties properties,
        BusinessMetrics businessMetrics
    ) {
        this.sender = sender;
        this.objectMapper = objectMapper;
        this.properties = properties;
        this.businessMetrics = businessMetrics == null ? BusinessMetrics.noop() : businessMetrics;
    }

    public RocketMqAnalysisTaskMessageProducer(
        RocketMqMessageSender sender,
        ObjectMapper objectMapper,
        RocketMqProducerProperties properties
    ) {
        this(sender, objectMapper, properties, BusinessMetrics.noop());
    }

    @Override
    public void send(AnalysisTaskMessageTag tag, AnalysisTaskMessage message) {
        if (tag == null) {
            throw new BusinessException(ErrorCode.COMMON_VALIDATION_FAILED);
        }
        message.validate();
        log.info(
            "event=mq_message_send_requested taskId={} tag={} outcome=start",
            SafeLogSanitizer.sanitize(message.taskId()),
            tag.name()
        );
        try {
            sender.send(
                properties.analysisTopic(),
                tag.name(),
                message.taskId(),
                objectMapper.writeValueAsBytes(AnalysisTaskMessagePayload.from(message))
            );
            log.info(
                "event=mq_message_send_completed taskId={} tag={} outcome=success",
                SafeLogSanitizer.sanitize(message.taskId()),
                tag.name()
            );
            businessMetrics.incrementMqProduced(properties.analysisTopic(), tag.name(), "success");
        } catch (BusinessException exception) {
            businessMetrics.incrementMqProduced(properties.analysisTopic(), tag.name(), "failure");
            throw exception;
        } catch (Exception exception) {
            log.warn(
                "event=mq_message_send_failed taskId={} tag={} outcome=failure errorMessage={}",
                SafeLogSanitizer.sanitize(message.taskId()),
                tag.name(),
                SafeLogSanitizer.sanitizeAndLimit(exception.getMessage())
            );
            businessMetrics.incrementMqProduced(properties.analysisTopic(), tag.name(), "failure");
            throw new BusinessException(ErrorCode.MQ_SEND_FAILED, "消息发送失败", exception);
        }
    }

    private record AnalysisTaskMessagePayload(
        String taskId,
        String uploadId,
        Long userId,
        String targetLanguage,
        String requestId,
        String traceId,
        String createdAt
    ) {

        private static AnalysisTaskMessagePayload from(AnalysisTaskMessage message) {
            return new AnalysisTaskMessagePayload(
                message.taskId(),
                message.uploadId(),
                message.userId(),
                message.targetLanguage(),
                message.requestId(),
                message.traceId(),
                message.createdAt().toString()
            );
        }
    }
}
