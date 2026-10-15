package com.example.courselingo.systemmodel;

import org.springframework.data.redis.connection.RedisConnectionFactory;
import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.data.redis.listener.ChannelTopic;
import org.springframework.data.redis.listener.RedisMessageListenerContainer;

import java.nio.charset.StandardCharsets;

final class SystemModelVersionNotifications implements AutoCloseable {
    static final String CHANNEL = "lecturelens:system-models:version";
    private final RedisMessageListenerContainer listener;

    SystemModelVersionNotifications(
            SystemModelRegistry registry,
            StringRedisTemplate template,
            RedisConnectionFactory factory) {
        if (template != null)
            registry.notifier(version -> template.convertAndSend(CHANNEL, Long.toString(version)));
        if (factory == null) {
            listener = null;
            return;
        }
        listener = new RedisMessageListenerContainer();
        listener.setConnectionFactory(factory);
        listener.addMessageListener(
                (message, pattern) -> {
                    try {
                        registry.invalidate(
                                Long.parseLong(
                                        new String(message.getBody(), StandardCharsets.US_ASCII)));
                    } catch (RuntimeException ignored) {
                    }
                },
                new ChannelTopic(CHANNEL));
        try {
            listener.afterPropertiesSet();
            listener.start();
        } catch (Exception ignored) {
            org.slf4j.LoggerFactory.getLogger(getClass())
                    .warn(
                            "event=system_model_version_notifications_unavailable"
                                + " source=database_version_check");
        }
    }

    @Override
    public void close() {
        if (listener != null)
            try {
                listener.destroy();
            } catch (Exception ignored) {
            }
    }
}
