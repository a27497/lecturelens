package com.example.courselingo.auth.service;

import com.baomidou.mybatisplus.core.conditions.query.LambdaQueryWrapper;
import com.example.courselingo.auth.dto.LoginRequest;
import com.example.courselingo.auth.dto.LoginResponse;
import com.example.courselingo.auth.entity.UserAccount;
import com.example.courselingo.auth.mapper.UserAccountMapper;
import com.example.courselingo.common.error.ErrorCode;
import com.example.courselingo.common.exception.BusinessException;
import java.util.Locale;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.stereotype.Service;

@Service
public class AuthLoginServiceImpl implements AuthLoginService {

    private static final String ACTIVE_STATUS = "ACTIVE";
    private static final String TOKEN_TYPE = "Bearer";

    private final UserAccountMapper userAccountMapper;
    private final PasswordEncoder passwordEncoder;
    private final JwtAccessTokenService jwtAccessTokenService;
    private final RefreshTokenService refreshTokenService;

    public AuthLoginServiceImpl(
        UserAccountMapper userAccountMapper,
        PasswordEncoder passwordEncoder,
        JwtAccessTokenService jwtAccessTokenService,
        RefreshTokenService refreshTokenService
    ) {
        this.userAccountMapper = userAccountMapper;
        this.passwordEncoder = passwordEncoder;
        this.jwtAccessTokenService = jwtAccessTokenService;
        this.refreshTokenService = refreshTokenService;
    }

    @Override
    public LoginResponse login(LoginRequest request) {
        String email = normalizeEmail(request.email());
        UserAccount userAccount = findByEmail(email);
        if (userAccount == null) {
            throw new BusinessException(ErrorCode.AUTH_INVALID_CREDENTIALS);
        }
        if (!passwordEncoder.matches(request.password(), userAccount.getPasswordHash())) {
            throw new BusinessException(ErrorCode.AUTH_INVALID_CREDENTIALS);
        }
        if (!ACTIVE_STATUS.equals(userAccount.getStatus())) {
            throw new BusinessException(ErrorCode.AUTH_USER_DISABLED);
        }

        String accessToken = jwtAccessTokenService.generate(userAccount);
        String refreshToken = refreshTokenService.issue(userAccount);
        return new LoginResponse(
            accessToken,
            refreshToken,
            TOKEN_TYPE,
            jwtAccessTokenService.expiresIn(),
            new LoginResponse.User(userAccount.getId(), userAccount.getEmail(), userAccount.getStatus())
        );
    }

    private UserAccount findByEmail(String email) {
        LambdaQueryWrapper<UserAccount> queryWrapper = new LambdaQueryWrapper<UserAccount>()
            .eq(UserAccount::getEmail, email)
            .last("LIMIT 1");
        return userAccountMapper.selectOne(queryWrapper);
    }

    private String normalizeEmail(String email) {
        return email.trim().toLowerCase(Locale.ROOT);
    }
}
