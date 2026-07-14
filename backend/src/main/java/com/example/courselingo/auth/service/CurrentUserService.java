package com.example.courselingo.auth.service;

import com.example.courselingo.auth.dto.CurrentUserResponse;

public interface CurrentUserService {

    CurrentUserResponse currentUser(String authorizationHeader);
}
