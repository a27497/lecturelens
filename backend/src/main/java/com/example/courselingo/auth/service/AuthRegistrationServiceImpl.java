package com.example.courselingo.auth.service;

import com.baomidou.mybatisplus.core.conditions.query.LambdaQueryWrapper;
import com.example.courselingo.auth.dto.RegisterRequest;
import com.example.courselingo.auth.dto.RegisterResponse;
import com.example.courselingo.auth.entity.UserAccount;
import com.example.courselingo.auth.mapper.UserAccountMapper;
import com.example.courselingo.common.error.ErrorCode;
import com.example.courselingo.common.exception.BusinessException;
import java.util.Locale;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.dao.DuplicateKeyException;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class AuthRegistrationServiceImpl implements AuthRegistrationService {

    private static final String ACTIVE_STATUS = "ACTIVE";
    private static final int BCRYPT_MAX_PASSWORD_LENGTH = 72;

    private final UserAccountMapper userAccountMapper;
    private final PasswordEncoder passwordEncoder;

    public AuthRegistrationServiceImpl(UserAccountMapper userAccountMapper, PasswordEncoder passwordEncoder) {
        this.userAccountMapper = userAccountMapper;
        this.passwordEncoder = passwordEncoder;
    }

    @Override
    @Transactional
    public RegisterResponse register(RegisterRequest request) {
        String email = normalizeEmail(request.email());
        validatePassword(request.password());
        rejectDuplicateEmail(email);

        UserAccount userAccount = new UserAccount();
        userAccount.setEmail(email);
        userAccount.setPasswordHash(passwordEncoder.encode(request.password()));
        userAccount.setStatus(ACTIVE_STATUS);

        try {
            userAccountMapper.insert(userAccount);
        } catch (DuplicateKeyException exception) {
            throw new BusinessException(ErrorCode.AUTH_EMAIL_ALREADY_EXISTS);
        }

        return new RegisterResponse(userAccount.getId(), userAccount.getEmail(), userAccount.getStatus());
    }

    private String normalizeEmail(String email) {
        return email.trim().toLowerCase(Locale.ROOT);
    }

    private void validatePassword(String password) {
        if (password == null || password.isBlank() || password.length() < 8 || password.length() > BCRYPT_MAX_PASSWORD_LENGTH) {
            throw new BusinessException(ErrorCode.AUTH_PASSWORD_WEAK);
        }
        boolean hasLetter = password.chars().anyMatch(Character::isLetter);
        boolean hasDigit = password.chars().anyMatch(Character::isDigit);
        if (!hasLetter || !hasDigit) {
            throw new BusinessException(ErrorCode.AUTH_PASSWORD_WEAK);
        }
    }

    private void rejectDuplicateEmail(String email) {
        LambdaQueryWrapper<UserAccount> queryWrapper = new LambdaQueryWrapper<UserAccount>()
            .eq(UserAccount::getEmail, email)
            .last("LIMIT 1");
        UserAccount existing = userAccountMapper.selectOne(queryWrapper);
        if (existing != null) {
            throw new BusinessException(ErrorCode.AUTH_EMAIL_ALREADY_EXISTS);
        }
    }
}
