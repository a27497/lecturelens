package com.example.courselingo.vision.ocr;

import org.springframework.boot.autoconfigure.condition.ConditionalOnMissingBean;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class OcrConfiguration {

    @Bean
    @ConditionalOnMissingBean
    OcrProcessExecutor ocrProcessExecutor() {
        return new ProcessBuilderOcrProcessExecutor();
    }

    @Bean
    @ConditionalOnMissingBean
    OcrProvider ocrProvider(VisionOcrProperties properties, OcrProcessExecutor processExecutor) {
        return new TesseractOcrProvider(properties, processExecutor);
    }
}
