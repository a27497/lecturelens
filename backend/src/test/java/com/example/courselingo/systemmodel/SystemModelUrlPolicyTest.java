package com.example.courselingo.systemmodel;

import static org.assertj.core.api.Assertions.*;

import com.example.courselingo.common.exception.BusinessException;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.ValueSource;

import java.net.InetAddress;

class SystemModelUrlPolicyTest {
    private final SystemModelUrlPolicy policy =
            new SystemModelUrlPolicy(host -> new InetAddress[] {InetAddress.getByName("8.8.8.8")});

    @Test
    void preservesExactPrefixes() {
        assertThat(policy.checkedChatEndpoint("https://api.deepseek.com").toString())
                .isEqualTo("https://api.deepseek.com/chat/completions");
        assertThat(policy.checkedChatEndpoint("https://example.com/v1/").toString())
                .isEqualTo("https://example.com/v1/chat/completions");
        assertThat(policy.checkedChatEndpoint("https://example.com/compatible-mode/v1").toString())
                .isEqualTo("https://example.com/compatible-mode/v1/chat/completions");
    }

    @ParameterizedTest
    @ValueSource(
            strings = {
                "file:///etc/passwd",
                "https://user:secret@example.com",
                "http://example.com?q=key",
                "http://example.com/#key",
                "http://example.com/a/../b",
                "http://example.com/%2e%2e",
                "http://example.com//v1",
                "http://example.com:0",
                "http://example.com/chat/completions"
            })
    void rejectsUnsafeUrls(String url) {
        assertThatThrownBy(() -> policy.checkedChatEndpoint(url))
                .isInstanceOf(BusinessException.class)
                .hasNoCause();
    }

    @ParameterizedTest
    @ValueSource(
            strings = {
                "127.0.0.1",
                "0.0.0.0",
                "10.0.0.1",
                "172.16.0.1",
                "192.168.1.1",
                "169.254.169.254",
                "100.64.0.1",
                "::1",
                "fe80::1",
                "fc00::1",
                "::ffff:127.0.0.1",
                "2001:db8::1", "2002:7f00:1::1", "2001::1", "192.88.99.1"
            })
    void rejectsEveryNonPublicAddressEvenInMixedDnsAnswers(String ip) throws Exception {
        var mixed =
                new SystemModelUrlPolicy(
                        host ->
                                new InetAddress[] {
                                    InetAddress.getByName("8.8.8.8"), InetAddress.getByName(ip)
                                });
        assertThatThrownBy(() -> mixed.checkedChatEndpoint("https://example.com"))
                .isInstanceOf(BusinessException.class);
    }
}
