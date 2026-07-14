package com.example.courselingo.common.web;

import com.example.courselingo.common.error.ErrorCode;
import com.example.courselingo.common.exception.BusinessException;
import com.example.courselingo.common.logging.SafeLogSanitizer;
import com.example.courselingo.common.response.ApiResponse;
import jakarta.validation.ConstraintViolation;
import jakarta.validation.ConstraintViolationException;
import java.util.LinkedHashMap;
import java.util.Map;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.http.ResponseEntity;
import org.springframework.http.converter.HttpMessageNotReadableException;
import org.springframework.validation.FieldError;
import org.springframework.web.bind.MethodArgumentNotValidException;
import org.springframework.web.bind.MissingServletRequestParameterException;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;
import org.springframework.web.method.annotation.HandlerMethodValidationException;
import org.springframework.web.method.annotation.MethodArgumentTypeMismatchException;
import org.springframework.web.servlet.NoHandlerFoundException;
import org.springframework.web.servlet.resource.NoResourceFoundException;

@RestControllerAdvice
public class GlobalExceptionHandler {

    private static final Logger log = LoggerFactory.getLogger(GlobalExceptionHandler.class);

    @ExceptionHandler(BusinessException.class)
    public ResponseEntity<ApiResponse<Void>> handleBusinessException(BusinessException exception) {
        ErrorCode errorCode = exception.errorCode();
        logHandledException(errorCode, exception);
        return ResponseEntity
            .status(errorCode.httpStatus())
            .body(ApiResponse.failure(errorCode.code(), exception.getMessage()));
    }

    @ExceptionHandler(MethodArgumentNotValidException.class)
    public ResponseEntity<ApiResponse<Map<String, String>>> handleMethodArgumentNotValid(
        MethodArgumentNotValidException exception
    ) {
        Map<String, String> details = new LinkedHashMap<>();
        for (FieldError fieldError : exception.getBindingResult().getFieldErrors()) {
            details.putIfAbsent(fieldError.getField(), fieldError.getDefaultMessage());
        }
        ErrorCode errorCode = ErrorCode.COMMON_VALIDATION_FAILED;
        logHandledException(errorCode, exception, errorCode.defaultMessage());
        return ResponseEntity
            .status(errorCode.httpStatus())
            .body(ApiResponse.failure(errorCode.code(), errorCode.defaultMessage(), details));
    }

    @ExceptionHandler(ConstraintViolationException.class)
    public ResponseEntity<ApiResponse<Map<String, String>>> handleConstraintViolation(
        ConstraintViolationException exception
    ) {
        Map<String, String> details = new LinkedHashMap<>();
        for (ConstraintViolation<?> violation : exception.getConstraintViolations()) {
            details.putIfAbsent(lastPathSegment(violation.getPropertyPath().toString()), violation.getMessage());
        }
        ErrorCode errorCode = ErrorCode.COMMON_VALIDATION_FAILED;
        logHandledException(errorCode, exception, errorCode.defaultMessage());
        return ResponseEntity
            .status(errorCode.httpStatus())
            .body(ApiResponse.failure(errorCode.code(), errorCode.defaultMessage(), details));
    }

    @ExceptionHandler(HandlerMethodValidationException.class)
    public ResponseEntity<ApiResponse<Map<String, String>>> handleHandlerMethodValidation(
        HandlerMethodValidationException exception
    ) {
        Map<String, String> details = new LinkedHashMap<>();
        exception.getParameterValidationResults().forEach(result -> result.getResolvableErrors().forEach(error ->
            details.putIfAbsent(result.getMethodParameter().getParameterName(), error.getDefaultMessage())
        ));
        ErrorCode errorCode = ErrorCode.COMMON_VALIDATION_FAILED;
        logHandledException(errorCode, exception, errorCode.defaultMessage());
        return ResponseEntity
            .status(errorCode.httpStatus())
            .body(ApiResponse.failure(errorCode.code(), errorCode.defaultMessage(), details));
    }

    @ExceptionHandler(HttpMessageNotReadableException.class)
    public ResponseEntity<ApiResponse<Void>> handleHttpMessageNotReadable(HttpMessageNotReadableException exception) {
        ErrorCode errorCode = ErrorCode.COMMON_BAD_REQUEST;
        logHandledException(errorCode, exception);
        return ResponseEntity
            .status(errorCode.httpStatus())
            .body(ApiResponse.failure(errorCode.code(), errorCode.defaultMessage()));
    }

    @ExceptionHandler(MissingServletRequestParameterException.class)
    public ResponseEntity<ApiResponse<Map<String, String>>> handleMissingServletRequestParameter(
        MissingServletRequestParameterException exception
    ) {
        ErrorCode errorCode = ErrorCode.COMMON_VALIDATION_FAILED;
        Map<String, String> details = Map.of(exception.getParameterName(), "缺少必填请求参数");
        logHandledException(errorCode, exception, errorCode.defaultMessage());
        return ResponseEntity
            .status(errorCode.httpStatus())
            .body(ApiResponse.failure(errorCode.code(), errorCode.defaultMessage(), details));
    }

    @ExceptionHandler(MethodArgumentTypeMismatchException.class)
    public ResponseEntity<ApiResponse<Map<String, String>>> handleMethodArgumentTypeMismatch(
        MethodArgumentTypeMismatchException exception
    ) {
        ErrorCode errorCode = ErrorCode.COMMON_VALIDATION_FAILED;
        Map<String, String> details = Map.of(exception.getName(), "请求参数类型不正确");
        logHandledException(errorCode, exception, errorCode.defaultMessage());
        return ResponseEntity
            .status(errorCode.httpStatus())
            .body(ApiResponse.failure(errorCode.code(), errorCode.defaultMessage(), details));
    }

    @ExceptionHandler(NoHandlerFoundException.class)
    public ResponseEntity<ApiResponse<Void>> handleNoHandlerFound(NoHandlerFoundException exception) {
        ErrorCode errorCode = ErrorCode.COMMON_NOT_FOUND;
        logHandledException(errorCode, exception);
        return ResponseEntity
            .status(errorCode.httpStatus())
            .body(ApiResponse.failure(errorCode.code(), errorCode.defaultMessage()));
    }

    @ExceptionHandler(NoResourceFoundException.class)
    public ResponseEntity<ApiResponse<Void>> handleNoResourceFound(NoResourceFoundException exception) {
        ErrorCode errorCode = ErrorCode.COMMON_NOT_FOUND;
        logHandledException(errorCode, exception);
        return ResponseEntity
            .status(errorCode.httpStatus())
            .body(ApiResponse.failure(errorCode.code(), errorCode.defaultMessage()));
    }

    @ExceptionHandler(Exception.class)
    public ResponseEntity<ApiResponse<Void>> handleException(Exception exception) {
        ErrorCode errorCode = ErrorCode.COMMON_INTERNAL_ERROR;
        logHandledException(errorCode, exception);
        return ResponseEntity
            .status(errorCode.httpStatus())
            .body(ApiResponse.failure(errorCode.code(), errorCode.defaultMessage()));
    }

    private static void logHandledException(ErrorCode errorCode, Exception exception) {
        logHandledException(errorCode, exception, exception.getMessage());
    }

    private static void logHandledException(ErrorCode errorCode, Exception exception, String message) {
        log.warn(
            "event=exception_handled outcome=failure errorCode={} exceptionType={} errorMessage={}",
            errorCode.code(),
            exception.getClass().getSimpleName(),
            SafeLogSanitizer.sanitizeAndLimit(message)
        );
    }

    private static String lastPathSegment(String path) {
        int lastDotIndex = path.lastIndexOf('.');
        if (lastDotIndex < 0 || lastDotIndex == path.length() - 1) {
            return path;
        }
        return path.substring(lastDotIndex + 1);
    }
}
