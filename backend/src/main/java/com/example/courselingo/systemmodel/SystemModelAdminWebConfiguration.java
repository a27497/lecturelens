package com.example.courselingo.systemmodel;

import com.example.courselingo.auth.service.AdminAuthorizationService;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import org.springframework.context.annotation.Configuration;
import org.springframework.beans.factory.ObjectProvider;
import org.springframework.web.servlet.HandlerInterceptor;
import org.springframework.web.servlet.config.annotation.InterceptorRegistry;
import org.springframework.web.servlet.config.annotation.WebMvcConfigurer;

@Configuration(proxyBeanMethods = false)
public class SystemModelAdminWebConfiguration implements WebMvcConfigurer {
    public static final String ADMIN_ATTRIBUTE = SystemModelAdminWebConfiguration.class.getName() + ".admin";
    private final ObjectProvider<AdminAuthorizationService> authorization;

    public SystemModelAdminWebConfiguration(ObjectProvider<AdminAuthorizationService> authorization) {
        this.authorization = authorization;
    }

    @Override
    public void addInterceptors(InterceptorRegistry registry) {
        registry.addInterceptor(new HandlerInterceptor() {
            @Override
            public boolean preHandle(HttpServletRequest request, HttpServletResponse response, Object handler) {
                request.setAttribute(ADMIN_ATTRIBUTE, authorization.getObject().requireAdmin(request.getHeader("Authorization")));
                return true;
            }
        }).addPathPatterns("/api/admin/system-models", "/api/admin/system-models/**");
    }
}
