package com.example.courselingo.auth.service;

import com.example.courselingo.auth.dto.LoginRequest;
import com.example.courselingo.auth.dto.LoginResponse;

public interface AuthLoginService {

    LoginResponse login(LoginRequest request);
}
