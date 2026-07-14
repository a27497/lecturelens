package com.example.courselingo.mq;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import com.example.courselingo.common.error.ErrorCode;
import com.example.courselingo.common.exception.BusinessException;
import org.junit.jupiter.api.Test;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;

class RocketMqProducerConfigurationTest {

    private final ApplicationContextRunner contextRunner = new ApplicationContextRunner()
        .withUserConfiguration(RocketMqProducerConfiguration.class, RocketMqConsumerConfiguration.class)
        .withBean(RocketMqMessageListener.class, () -> new RocketMqMessageListener(message -> ConsumerProcessResult.SUCCESS));

    @Test
    void createsDisabledSenderAndConsumerByDefaultWithoutConnectingToRocketMq() {
        contextRunner
            .withPropertyValues(
                "courselingo.mq.rocketmq.name-server=127.0.0.1:9876",
                "courselingo.mq.rocketmq.endpoint=",
                "courselingo.mq.rocketmq.producer-group=courselingo-analysis-producer-group",
                "courselingo.mq.rocketmq.consumer-group=courselingo-analysis-consumer-group",
                "courselingo.mq.rocketmq.analysis-topic=courselingo-analysis-task",
                "courselingo.mq.rocketmq.send-timeout-ms=3000",
                "courselingo.mq.rocketmq.consume-timeout-ms=15000",
                "courselingo.mq.rocketmq.enabled=false"
            )
            .run(context -> {
                assertThat(context).hasSingleBean(RocketMqProducerProperties.class);
                assertThat(context).hasSingleBean(RocketMqConsumerProperties.class);
                assertThat(context).hasSingleBean(RocketMqMessageSender.class);
                assertThat(context).hasSingleBean(RocketMqConsumerStarter.class);
                assertThat(context.getBean(RocketMqMessageSender.class))
                    .isInstanceOf(DisabledRocketMqMessageSender.class);
                assertThat(context.getBean(RocketMqConsumerStarter.class))
                    .isInstanceOf(DisabledRocketMqConsumerStarter.class);
                assertThat(context.getBean(RocketMqProducerProperties.class).sslEnabled()).isFalse();
            });
    }

    @Test
    void rejectsInvalidConfigurationBeforeConnectingToRocketMq() {
        RocketMqProducerProperties properties = new RocketMqProducerProperties(
            "127.0.0.1:9876",
            " ",
            "courselingo-analysis-producer-group",
            "courselingo-analysis-task",
            3000,
            false,
            true
        );

        assertThatThrownBy(properties::validate)
            .isInstanceOf(BusinessException.class)
            .extracting("errorCode")
            .isEqualTo(ErrorCode.MQ_CONFIGURATION_INVALID);
    }

    @Test
    void disabledProducerAllowsBlankEndpoint() {
        RocketMqProducerProperties properties = new RocketMqProducerProperties(
            "127.0.0.1:9876",
            " ",
            "courselingo-analysis-producer-group",
            "courselingo-analysis-task",
            3000,
            false,
            false
        );

        properties.validate();
    }

    @Test
    void enabledProducerRequiresEndpointTopicAndGroup() {
        RocketMqProducerProperties missingEndpoint = new RocketMqProducerProperties(
            "127.0.0.1:9876",
            " ",
            "courselingo-analysis-producer-group",
            "courselingo-analysis-task",
            3000,
            false,
            true
        );
        RocketMqProducerProperties missingTopic = new RocketMqProducerProperties(
            "127.0.0.1:9876",
            "127.0.0.1:8081",
            "courselingo-analysis-producer-group",
            " ",
            3000,
            false,
            true
        );
        RocketMqProducerProperties missingGroup = new RocketMqProducerProperties(
            "127.0.0.1:9876",
            "127.0.0.1:8081",
            " ",
            "courselingo-analysis-task",
            3000,
            false,
            true
        );

        assertInvalid(missingEndpoint);
        assertInvalid(missingTopic);
        assertInvalid(missingGroup);
    }

    @Test
    void enabledProducerAcceptsProxyEndpointSeparateFromNameServer() {
        RocketMqProducerProperties properties = new RocketMqProducerProperties(
            "127.0.0.1:9876",
            "127.0.0.1:8081",
            "courselingo-analysis-producer-group",
            "courselingo-analysis-task",
            3000,
            false,
            true
        );

        properties.validate();
        assertThat(properties.endpoint()).isEqualTo("127.0.0.1:8081");
        assertThat(properties.nameServer()).isEqualTo("127.0.0.1:9876");
    }

    private static void assertInvalid(RocketMqProducerProperties properties) {
        assertThatThrownBy(properties::validate)
            .isInstanceOf(BusinessException.class)
            .extracting("errorCode")
            .isEqualTo(ErrorCode.MQ_CONFIGURATION_INVALID);
    }
}
