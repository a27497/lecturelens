package com.example.courselingo.auth.service;

import com.baomidou.mybatisplus.core.conditions.query.LambdaQueryWrapper;
import com.example.courselingo.auth.dto.LoginResponse;
import com.example.courselingo.auth.dto.RefreshRequest;
import com.example.courselingo.auth.entity.RefreshToken;
import com.example.courselingo.auth.entity.UserAccount;
import com.example.courselingo.auth.mapper.RefreshTokenMapper;
import com.example.courselingo.auth.mapper.UserAccountMapper;
import com.example.courselingo.common.error.ErrorCode;
import com.example.courselingo.common.exception.BusinessException;
import com.example.courselingo.infrastructure.RefreshTokenProperties;
import java.time.LocalDateTime;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class RefreshTokenServiceImpl implements RefreshTokenService {

    private static final String ACTIVE_STATUS = "ACTIVE";
    private static final String TOKEN_TYPE = "Bearer";

    private final RefreshTokenMapper refreshTokenMapper;
    private final UserAccountMapper userAccountMapper;
    private final JwtAccessTokenService jwtAccessTokenService;
    private final RefreshTokenGenerator tokenGenerator;
    private final RefreshTokenHashService hashService;
    private final RefreshTokenProperties properties;

    public RefreshTokenServiceImpl(
        RefreshTokenMapper refreshTokenMapper,
        UserAccountMapper userAccountMapper,
        JwtAccessTokenService jwtAccessTokenService,
        RefreshTokenGenerator tokenGenerator,
        RefreshTokenHashService hashService,
        RefreshTokenProperties properties
    ) {
        this.refreshTokenMapper = refreshTokenMapper;
        this.userAccountMapper = userAccountMapper;
        this.jwtAccessTokenService = jwtAccessTokenService;
        this.tokenGenerator = tokenGenerator;
        this.hashService = hashService;
        this.properties = properties;
    }

    @Override
    @Transactional
    public String issue(UserAccount userAccount) {
        String rawToken = tokenGenerator.generate();
        RefreshToken refreshToken = buildRefreshToken(userAccount.getId(), rawToken, LocalDateTime.now());
        refreshTokenMapper.insert(refreshToken);
        return rawToken;
    }

    @Override
    @Transactional
    public LoginResponse refresh(RefreshRequest request) {
        LocalDateTime now = LocalDateTime.now();
        RefreshToken existingToken = findByRawToken(request.refreshToken());
        if (existingToken == null) {
            throw new BusinessException(ErrorCode.AUTH_REFRESH_TOKEN_INVALID);
        }
        if (existingToken.getRevokedAt() != null) {
            throw new BusinessException(ErrorCode.AUTH_REFRESH_TOKEN_REVOKED);
        }
        if (!existingToken.getExpiresAt().isAfter(now)) {
            throw new BusinessException(ErrorCode.AUTH_TOKEN_EXPIRED);
        }

        UserAccount userAccount = userAccountMapper.selectById(existingToken.getUserId());
        if (userAccount == null) {
            throw new BusinessException(ErrorCode.AUTH_INVALID_CREDENTIALS);
        }
        if (!ACTIVE_STATUS.equals(userAccount.getStatus())) {
            throw new BusinessException(ErrorCode.AUTH_USER_DISABLED);
        }

        existingToken.setRevokedAt(now);
        refreshTokenMapper.updateById(existingToken);

        String newRefreshToken = tokenGenerator.generate();
        refreshTokenMapper.insert(buildRefreshToken(userAccount.getId(), newRefreshToken, now));

        return new LoginResponse(
            jwtAccessTokenService.generate(userAccount),
            newRefreshToken,
            TOKEN_TYPE,
            jwtAccessTokenService.expiresIn(),
            new LoginResponse.User(userAccount.getId(), userAccount.getEmail(), userAccount.getStatus())
        );
    }

    private RefreshToken findByRawToken(String rawToken) {
        LambdaQueryWrapper<RefreshToken> queryWrapper = new LambdaQueryWrapper<RefreshToken>()
            .eq(RefreshToken::getTokenHash, hashService.sha256Hex(rawToken))
            .last("LIMIT 1");
        return refreshTokenMapper.selectOne(queryWrapper);
    }

    private RefreshToken buildRefreshToken(Long userId, String rawToken, LocalDateTime now) {
        RefreshToken refreshToken = new RefreshToken();
        refreshToken.setUserId(userId);
        refreshToken.setTokenHash(hashService.sha256Hex(rawToken));
        refreshToken.setExpiresAt(now.plusSeconds(properties.refreshExpireSeconds()));
        refreshToken.setRevokedAt(null);
        return refreshToken;
    }
}
