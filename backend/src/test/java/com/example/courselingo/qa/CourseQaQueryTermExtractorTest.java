package com.example.courselingo.qa;

import static org.assertj.core.api.Assertions.assertThat;

import com.example.courselingo.qa.service.CourseQaQueryTermExtractor;
import org.junit.jupiter.api.Test;

class CourseQaQueryTermExtractorTest {

    private final CourseQaQueryTermExtractor extractor = new CourseQaQueryTermExtractor();

    @Test
    void extractsEnglishAndTechnicalIdentifiersWithoutLosingIdentifierCharacters() {
        assertThat(extractor.extract("Transformer")).containsExactly("transformer");
        assertThat(extractor.extract("Spring Boot")).containsExactly("spring boot");
        assertThat(extractor.extract("OpenCL")).containsExactly("opencl");
        assertThat(extractor.extract("GPT-5")).containsExactly("gpt-5");
        assertThat(extractor.extract("JavaParser")).containsExactly("javaparser");
        assertThat(extractor.extract("LangChain4j")).containsExactly("langchain4j");
        assertThat(extractor.extract("C++ C# api.v2 model_name"))
            .containsExactly("c++ c# api.v2 model_name");
    }

    @Test
    void extractsTechnicalTermsFromNaturalEnglishQuestions() {
        assertThat(extractor.extract("How does Spring Boot work?"))
            .containsExactly("spring boot");
        assertThat(extractor.extract("What is Transformer used for?"))
            .containsExactly("transformer");
        assertThat(extractor.extract("Can you please explain GPT-5?"))
            .containsExactly("gpt-5");
    }

    @Test
    void splitsChineseEnglishTransitionsAndFiltersQuestionWords() {
        assertThat(extractor.extract("课程中介绍的Transformer是什么"))
            .containsExactly("transformer");
        assertThat(extractor.extract("Transformer是什么"))
            .containsExactly("transformer");
    }

    @Test
    void extractsChineseTechnicalTermsFromCompleteQuestions() {
        assertThat(extractor.extract("这节课讲解的反向传播是什么"))
            .containsExactly("反向传播");
        assertThat(extractor.extract("课程中如何使用依赖注入"))
            .containsExactly("依赖注入");
    }

    @Test
    void returnsNoTermsForGenericQuestionsAndKeepsFirstOccurrenceOrder() {
        assertThat(extractor.extract("这节课程视频讲了什么？")).isEmpty();
        assertThat(extractor.extract("What does this course video explain?")).isEmpty();
        assertThat(extractor.extract("Transformer 和反向传播与 Transformer"))
            .containsExactly("transformer", "反向传播");
    }
}
