package com.example.courselingo.mq;

import com.example.courselingo.common.error.ErrorCode;
import com.example.courselingo.common.exception.BusinessException;

class DisabledRocketMqMessageSender implements RocketMqMessageSender {

    @Override
    public void send(String topic, String tag, String key, byte[] body) {
        throw new BusinessException(ErrorCode.MQ_CONFIGURATION_INVALID);
    }
}
