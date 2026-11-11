package com.example.courselingo.systemmodel;

import com.example.courselingo.common.error.ErrorCode;
import com.example.courselingo.common.exception.BusinessException;

import java.net.InetAddress;
import java.net.URI;

public class SystemModelUrlPolicy {
    @FunctionalInterface
    interface Resolver {
        InetAddress[] resolve(String host) throws Exception;
    }

    private final Resolver resolver;
    private static final java.util.concurrent.ThreadPoolExecutor DNS =
            new java.util.concurrent.ThreadPoolExecutor(
                    2,
                    2,
                    30,
                    java.util.concurrent.TimeUnit.SECONDS,
                    new java.util.concurrent.ArrayBlockingQueue<>(16),
                    task -> {
                        var thread = new Thread(task, "system-model-dns");
                        thread.setDaemon(true);
                        return thread;
                    });

    public SystemModelUrlPolicy() {
        this(SystemModelUrlPolicy::resolveBounded);
    }

    SystemModelUrlPolicy(Resolver resolver) {
        this.resolver = resolver;
    }

    public String normalize(String value) {
        try {
            if (value == null
                    || value.length() > 1900
                    || value.chars().anyMatch(c -> c <= 32 || c >= 127)) throw forbidden();
            URI uri = URI.create(value);
            if (!uri.isAbsolute()
                    || !("http".equals(uri.getScheme()) || "https".equals(uri.getScheme()))
                    || uri.getHost() == null
                    || uri.getRawUserInfo() != null
                    || uri.getRawQuery() != null
                    || uri.getRawFragment() != null
                    || uri.getRawPath().contains("%")
                    || uri.getRawPath().contains("\\")
                    || !uri.normalize().equals(uri)
                    || uri.getPort() == 0
                    || uri.getPort() > 65535) throw forbidden();
            String path = uri.getPath();
            if (path.endsWith("/chat/completions") || path.contains("//")) throw forbidden();
            return value.replaceAll("/+$", "");
        } catch (RuntimeException ignored) {
            throw forbidden();
        }
    }

    public URI checkedChatEndpoint(String baseUrl) {
        URI uri = URI.create(normalize(baseUrl) + "/chat/completions");
        checkDestination(uri);
        return uri;
    }

    public void checkDestination(URI uri) {
        if (uri == null || uri.getHost() == null
                || !("http".equals(uri.getScheme()) || "https".equals(uri.getScheme()))
                || uri.getRawUserInfo() != null || uri.getRawQuery() != null
                || uri.getRawFragment() != null || uri.getPort() == 0 || uri.getPort() > 65535)
            throw forbidden();
        publicAddresses(uri.getHost());
    }

    // The HTTP transport must connect to these checked addresses, not resolve the host again.
    InetAddress[] publicAddresses(String host) {
        try {
            InetAddress[] addresses = resolver.resolve(host);
            if (addresses.length == 0) throw forbidden();
            for (InetAddress address : addresses) if (!publicAddress(address)) throw forbidden();
            return addresses;
        } catch (Exception ignored) {
            throw forbidden();
        }
    }

    static boolean publicAddress(InetAddress address) {
        if (address.isAnyLocalAddress()
                || address.isLoopbackAddress()
                || address.isLinkLocalAddress()
                || address.isSiteLocalAddress()
                || address.isMulticastAddress()) return false;
        byte[] b = address.getAddress();
        if (b.length == 4) {
            int a = b[0] & 255, c = b[1] & 255, d = b[2] & 255;
            return a != 0
                    && a != 10
                    && a != 127
                    && a < 224
                    && !(a == 100 && c >= 64 && c <= 127)
                    && !(a == 169 && c == 254)
                    && !(a == 172 && c >= 16 && c <= 31)
                    && !(a == 192 && (c == 168 || c == 0))
                    && !(a == 192 && c == 88 && d == 99)
                    && !(a == 198 && (c == 18 || c == 19 || (c == 51 && d == 100)))
                    && !(a == 203 && c == 0 && d == 113);
        }
        // IPv6 global unicast only; reject ULA, mapped/translation, documentation and local ranges.
        return b.length == 16
                && (b[0] & 0xe0) == 0x20
                && !((b[0] & 255) == 0x20 && (b[1] & 255) == 2)
                && !((b[0] & 255) == 0x20 && (b[1] & 255) == 1 && (b[2] & 255) <= 1)
                && !((b[0] & 255) == 0x20
                        && (b[1] & 255) == 1
                        && (b[2] & 255) == 0x0d
                        && (b[3] & 255) == 0xb8);
    }

    private static BusinessException forbidden() {
        return new BusinessException(ErrorCode.SYSTEM_MODEL_ADDRESS_FORBIDDEN);
    }

    private static InetAddress[] resolveBounded(String host) throws Exception {
        var pending = DNS.submit(() -> InetAddress.getAllByName(host));
        try {
            return pending.get(3, java.util.concurrent.TimeUnit.SECONDS);
        } finally {
            if (!pending.isDone()) pending.cancel(true);
        }
    }
}
