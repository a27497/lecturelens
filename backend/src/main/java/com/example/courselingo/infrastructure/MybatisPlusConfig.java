package com.example.courselingo.infrastructure;

import org.mybatis.spring.annotation.MapperScan;
import org.springframework.context.annotation.Configuration;

@Configuration
@MapperScan({
    "com.example.courselingo.*.mapper",
    "com.example.courselingo.vision.keyframe.mapper",
    "com.example.courselingo.vision.ocr.mapper",
    "com.example.courselingo.vision.analysis.mapper",
    "com.example.courselingo.video.context.mapper"
})
public class MybatisPlusConfig {
}
