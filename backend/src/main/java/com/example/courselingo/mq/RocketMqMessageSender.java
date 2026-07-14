package com.example.courselingo.mq;

interface RocketMqMessageSender {

    void send(String topic, String tag, String key, byte[] body) throws Exception;
}
