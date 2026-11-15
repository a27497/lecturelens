package com.example.courselingo.learning.service;

import com.example.courselingo.ai.llm.*;
import com.example.courselingo.modelrouting.AiModelRoutedLlmRequestFactory;
import com.fasterxml.jackson.databind.ObjectMapper;
import java.nio.file.*;
import java.time.Duration;
import java.util.*;

/** Supplemental real-model context test only: no service stack, DB writes, publication or ASR. */
public class MaterialsSupplement {
    public static void main(String[] args) throws Exception {
        var json = new ObjectMapper();
        var input = json.readTree(System.in);
        Path privateRoot = Path.of(args[0]);
        var properties = new LearningPackageProperties();
        var llm = new OpenAiCompatibleLlmProperties();
        llm.setBaseUrl(input.path("baseUrl").asText());
        llm.setModel(input.path("model").asText());
        llm.setApiKey(System.getenv("OPENAI_COMPATIBLE_API_KEY"));
        llm.setMaxTokens(4096);
        llm.setRequestTimeout(Duration.ofSeconds(180));
        var real = new OpenAiCompatibleLlmProvider(llm, new JavaHttpOpenAiCompatibleLlmClient(Duration.ofSeconds(5)));
        var calls = new ArrayList<Map<String,Object>>();
        LlmProvider observed = new LlmProvider() {
            public String providerName() { return real.providerName(); }
            public LlmResult generate(LlmRequest request) {
                var result = real.generate(request);
                int actual = result.usage().promptTokens();
                int limit = ((Number) request.metadata().get("learningInputTokenLimit")).intValue();
                if (actual > limit || actual + request.maxTokens() + properties.contextReserve() > 8192)
                    throw new IllegalStateException("ACTUAL_CONTEXT_BUDGET_EXCEEDED");
                var row = new LinkedHashMap<String,Object>();
                row.put("phase",request.metadata().get("learningPhase"));
                row.put("estimated_input_tokens",request.metadata().get("learningEstimatedInputTokens"));
                row.put("input_limit",limit);
                row.put("max_output_tokens",request.maxTokens());
                row.put("prompt_tokens",actual);
                row.put("completion_tokens",result.usage().completionTokens());
                row.put("duration_millis",result.duration().toMillis());
                row.put("finish_reason",result.finishReason());
                calls.add(row);
                return result;
            }
        };
        var guard = new LearningPackageContextGuard(observed, properties, () -> {});
        var command = new ValidatedLearningPackageCommand("p21c-materials-supplement-1",9L,"en","zh-CN","p21c-supplement");
        var request = LearningPackagePromptFactory.buildFromFullText(command, input.path("source").asText(),
            input.path("translated").asText(), Duration.ofSeconds(180));
        var meta = new HashMap<>(request.metadata());
        meta.put(AiModelRoutedLlmRequestFactory.METADATA_MODEL_NAME, llm.getModel());
        meta.put(AiModelRoutedLlmRequestFactory.METADATA_STAGE,"LEARNING_PACKAGE");
        request = new LlmRequest(request.requestId(),request.taskId(),request.messages(),request.timeout(),request.temperature(),
            request.maxTokens(),1,meta,request.responseFormat());
        var report = new LinkedHashMap<String,Object>();
        report.put("kind","SUPPLEMENTAL_MATERIALS_ONLY_REUSED_EVIDENCE");
        report.put("original_input_estimate",LearningPackageContextGuard.estimate(request));
        report.put("model",llm.getModel());
        report.put("asr_calls",0); report.put("translation_calls",0);report.put("publication",false);
        try {
            var result=guard.generate(request);
            var parsed=new LearningPackageResponseParser().parse(result.content(),"zh-CN");
            report.put("structured_valid",true);
            var quality=new LearningPackageQualityProfile("LONG",220,800,6,12,8,15,5,8,false);
            var validation=LearningPackageQualityValidator.validate(parsed,quality,"zh-CN");
            report.put("long_course_quality_valid",validation.valid());
            report.put("quality_deficits",validation.deficits());
            report.put("aggregate_usage",result.usage());
            report.put("aggregate_duration_millis",result.duration().toMillis());
            Files.writeString(privateRoot.resolve("supplement-materials.json"),result.content());
        } catch(Exception failure) {
            report.put("structured_valid",false);
            report.put("exception_class",failure.getClass().getSimpleName());
            throw failure;
        } finally {
            report.put("calls",calls);
            Files.writeString(privateRoot.resolve("supplement-summary.json"),json.writerWithDefaultPrettyPrinter().writeValueAsString(report));
        }
    }
}
