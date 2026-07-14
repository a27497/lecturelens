package com.example.courselingo.auth.service;

import com.example.courselingo.auth.dto.CurrentUserResponse;
import com.example.courselingo.auth.entity.UserAccount;
import com.example.courselingo.auth.mapper.UserAccountMapper;
import com.example.courselingo.common.error.ErrorCode;
import com.example.courselingo.common.exception.BusinessException;
import org.springframework.stereotype.Service;

@Service
public class CurrentUserServiceImpl implements CurrentUserService {

    private static final String ACTIVE_STATUS = "ACTIVE";
    private static final String BEARER_PREFIX = "Bearer ";

    private final JwtAccessTokenService jwtAccessTokenService;
    private final UserAccountMapper userAccountMapper;

    public CurrentUserServiceImpl(JwtAccessTokenService jwtAccessTokenService, UserAccountMapper userAccountMapper) {
        this.jwtAccessTokenService = jwtAccessTokenService;
        this.userAccountMapper = userAccountMapper;
    }

    @Override
    public CurrentUserResponse currentUser(String authorizationHeader) {
        String accessToken = extractBearerToken(authorizationHeader);
        AccessTokenClaims claims = jwtAccessTokenService.parseAccessToken(accessToken);
        UserAccount userAccount = userAccountMapper.selectById(claims.userId());
        if (userAccount == null) {
            throw new BusinessException(ErrorCode.AUTH_INVALID_CREDENTIALS);
        }
        if (!ACTIVE_STATUS.equals(userAccount.getStatus())) {
            throw new BusinessException(ErrorCode.AUTH_USER_DISABLED);
        }
        return new CurrentUserResponse(userAccount.getId(), userAccount.getEmail(), userAccount.getStatus());
    }

    private String extractBearerToken(String authorizationHeader) {
        if (authorizationHeader == null || authorizationHeader.isBlank() || !authorizationHeader.startsWith(BEARER_PREFIX)) {
            throw new BusinessException(ErrorCode.COMMON_UNAUTHORIZED);
        }
        String token = authorizationHeader.substring(BEARER_PREFIX.length()).trim();
        if (token.isBlank()) {
            throw new BusinessException(ErrorCode.COMMON_UNAUTHORIZED);
        }
        return token;
    }
}
