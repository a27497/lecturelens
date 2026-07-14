package com.example.courselingo.auth.service;

import com.example.courselingo.auth.dto.RegisterRequest;
import com.example.courselingo.auth.dto.RegisterResponse;

public interface AuthRegistrationService {

    RegisterResponse register(RegisterRequest request);
}
