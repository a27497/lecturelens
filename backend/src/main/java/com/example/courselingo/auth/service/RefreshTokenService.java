package com.example.courselingo.auth.service;

import com.example.courselingo.auth.dto.LoginResponse;
import com.example.courselingo.auth.dto.RefreshRequest;
import com.example.courselingo.auth.entity.UserAccount;

public interface RefreshTokenService {

    String issue(UserAccount userAccount);

    LoginResponse refresh(RefreshRequest request);
}
