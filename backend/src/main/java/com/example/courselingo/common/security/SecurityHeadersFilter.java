package com.example.courselingo.common.security;

import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import java.io.IOException;
import org.springframework.core.Ordered;
import org.springframework.core.annotation.Order;
import org.springframework.stereotype.Component;
import org.springframework.web.filter.OncePerRequestFilter;

@Component
@Order(Ordered.HIGHEST_PRECEDENCE + 20)
public class SecurityHeadersFilter extends OncePerRequestFilter {

    static final String X_CONTENT_TYPE_OPTIONS = "X-Content-Type-Options";
    static final String X_FRAME_OPTIONS = "X-Frame-Options";
    static final String REFERRER_POLICY = "Referrer-Policy";
    static final String CACHE_CONTROL = "Cache-Control";
    static final String PRAGMA = "Pragma";

    @Override
    protected void doFilterInternal(
        HttpServletRequest request,
        HttpServletResponse response,
        FilterChain filterChain
    ) throws ServletException, IOException {
        setIfAbsent(response, X_CONTENT_TYPE_OPTIONS, "nosniff");
        setIfAbsent(response, X_FRAME_OPTIONS, "DENY");
        setIfAbsent(response, REFERRER_POLICY, "no-referrer");
        setIfAbsent(response, CACHE_CONTROL, "no-store");
        setIfAbsent(response, PRAGMA, "no-cache");
        filterChain.doFilter(request, response);
    }

    private void setIfAbsent(HttpServletResponse response, String name, String value) {
        if (!response.containsHeader(name)) {
            response.setHeader(name, value);
        }
    }
}
