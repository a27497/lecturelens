package com.example.courselingo.ai.llm;

import com.example.courselingo.common.error.ErrorCode;
import com.example.courselingo.common.exception.BusinessException;

public class LlmStageException extends BusinessException {

    private final String stage;
    private final LlmProviderFailureDetails details;
    private final String safeErrorCode;
    private final String userMessage;

    public LlmStageException(String stage, Throwable cause) {
        this(stage, LlmProviderFailureClassifier.from(cause), cause);
    }

    public LlmStageException(String stage, LlmProviderFailureDetails details, Throwable cause) {
        super(errorCode(details), userMessage(stage, details), cause);
        this.stage = safeStage(stage);
        this.details = details == null
            ? new LlmProviderFailureDetails(LlmProviderFailureCategory.UNKNOWN, null, null, false)
            : details;
        this.safeErrorCode = safeErrorCode(this.stage, this.details.category());
        this.userMessage = userMessage(this.stage, this.details);
    }

    public String stage() {
        return stage;
    }

    public LlmProviderFailureDetails details() {
        return details;
    }

    public AiServiceErrorDetails apiDetails() {
        return new AiServiceErrorDetails(safeErrorCode, details.category(), details.retryable(), stage, userMessage);
    }

    public String safeDiagnosticSummary() {
        return details.safeSummary() + ";stage=" + stage;
    }

    private static ErrorCode errorCode(LlmProviderFailureDetails details) {
        return details != null && details.category() == LlmProviderFailureCategory.TIMEOUT
            ? ErrorCode.AI_PROVIDER_TIMEOUT
            : ErrorCode.AI_PROVIDER_FAILED;
    }

    private static String safeStage(String stage) {
        if (stage == null || stage.isBlank()) {
            return "AI";
        }
        String sanitized = stage.strip().replaceAll("[^A-Za-z0-9_-]", "");
        return sanitized.isBlank() ? "AI" : sanitized.substring(0, Math.min(64, sanitized.length()));
    }

    private static String safeErrorCode(String stage, LlmProviderFailureCategory category) {
        if (category == LlmProviderFailureCategory.MODEL_NOT_FOUND) {
            return "MODEL_NOT_FOUND";
        }
        if (category == LlmProviderFailureCategory.UNSUPPORTED_RESPONSE_FORMAT) {
            return "STRUCTURED_OUTPUT_UNSUPPORTED";
        }
        return stage + "_PROVIDER_" + category;
    }

    private static String userMessage(String stage, LlmProviderFailureDetails details) {
        LlmProviderFailureCategory category = details == null
            ? LlmProviderFailureCategory.UNKNOWN
            : details.category();
        String subject = switch (safeStage(stage)) {
            case "TRANSLATION", "TRANSLATION_FULL_TEXT", "SUBTITLE_TRANSLATION" -> "翻译服务";
            case "COURSE_QA" -> "课程问答";
            case "COURSE_CHAPTER" -> "课程章节生成";
            default -> "AI 服务";
        };
        return switch (category) {
            case TIMEOUT -> subject + "响应超时，本次请求已结束，请稍后重试。";
            case AUTHENTICATION -> subject + "认证失败，请检查模型服务配置。";
            case MODEL_NOT_FOUND -> "当前 AI 模型不可用，请检查模型配置。";
            case RATE_LIMIT -> subject + "请求过多，请稍后重试。";
            case UNSUPPORTED_RESPONSE_FORMAT -> "当前模型不支持结构化输出，兼容模式仍未成功。";
            case CONTEXT_TOO_LARGE -> subject + "输入内容过长，请缩短内容后重试。";
            case OUTPUT_INVALID -> subject + "返回格式不正确，请重试。";
            case NETWORK, SERVER_ERROR -> subject + "暂不可用，请稍后重试。";
            case INVALID_REQUEST -> subject + "请求参数不受当前模型支持，请检查模型配置。";
            case UNKNOWN -> subject + "调用失败，请稍后重试。";
        };
    }
}
