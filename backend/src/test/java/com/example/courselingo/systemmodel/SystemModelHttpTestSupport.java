package com.example.courselingo.systemmodel;

import java.net.InetAddress;
import java.net.URI;

/** Explicit test-only exception for disposable loopback HTTP servers. */
final class SystemModelHttpTestSupport {
    static SystemModelHttpClient loopbackClient(int limit) {
        return new SystemModelHttpClient(limit, new SystemModelUrlPolicy() {
            @Override public void checkDestination(URI uri) {}
            @Override InetAddress[] publicAddresses(String host) {
                return new InetAddress[] {InetAddress.getLoopbackAddress()};
            }
        });
    }
}
