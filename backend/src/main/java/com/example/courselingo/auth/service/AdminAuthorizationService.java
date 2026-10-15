package com.example.courselingo.auth.service;

import com.example.courselingo.auth.dto.CurrentUserResponse;
import com.example.courselingo.auth.entity.UserRole;
import com.example.courselingo.common.error.ErrorCode;
import com.example.courselingo.common.exception.BusinessException;
import org.springframework.stereotype.Service;

@Service
public class AdminAuthorizationService {
    private final CurrentUserService users;

    public AdminAuthorizationService(CurrentUserService users) {
        this.users = users;
    }

    public CurrentUserResponse requireAdmin(String authorizationHeader) {
        // CurrentUserService reads the account on every request; JWT role claims cannot preserve revoked privileges.
        CurrentUserResponse user = users.currentUser(authorizationHeader);
        if (user == null || user.role() != UserRole.ADMIN) {
            throw new BusinessException(ErrorCode.COMMON_FORBIDDEN);
        }
        return user;
    }
}
