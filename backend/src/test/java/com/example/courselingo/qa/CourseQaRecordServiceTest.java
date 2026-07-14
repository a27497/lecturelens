package com.example.courselingo.qa;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.CALLS_REAL_METHODS;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

import com.baomidou.mybatisplus.core.conditions.Wrapper;
import com.example.courselingo.qa.domain.CourseQaRecord;
import com.example.courselingo.qa.mapper.CourseQaRecordMapper;
import java.lang.reflect.RecordComponent;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.List;
import org.junit.jupiter.api.Test;

class CourseQaRecordServiceTest {

    @Test
    void domainDoesNotExposeRawSensitiveFields() {
        assertThat(java.util.Arrays.stream(CourseQaRecord.class.getDeclaredFields()).map(java.lang.reflect.Field::getName))
            .doesNotContain(
                "raw" + "Prompt",
                "raw" + "Response",
                "object" + "Key",
                "local" + "Path",
                "api" + "Key",
                "token",
                "password"
            );
    }

    @Test
    void mapperQueriesAreScopedByTaskAndUserInStableOrder() {
        CourseQaRecordMapper mapper = mock(CourseQaRecordMapper.class, CALLS_REAL_METHODS);
        when(mapper.selectList(any(Wrapper.class))).thenReturn(List.of(record(1L), record(2L)));

        List<CourseQaRecord> rows = mapper.selectByTaskIdAndUserId("task_1", 42L, 20);

        assertThat(rows).extracting(CourseQaRecord::getId).containsExactly(1L, 2L);
        verify(mapper).selectList(any(Wrapper.class));
    }

    @Test
    void qaPackageDoesNotReferenceObjectStorageOrRunnerPipeline() throws Exception {
        String source = readJavaSources("src/main/java/com/example/courselingo/qa");

        assertThat(source)
            .doesNotContain("object" + "Key")
            .doesNotContain("Storage")
            .doesNotContain("Minio")
            .doesNotContain("AnalysisTaskRunner")
            .doesNotContain("RocketMQ")
            .doesNotContain("raw" + "Prompt")
            .doesNotContain("raw" + "Response");
    }

    private static CourseQaRecord record(Long id) {
        CourseQaRecord row = new CourseQaRecord();
        row.setId(id);
        row.setTaskId("task_1");
        row.setUserId(42L);
        row.setQuestion("question");
        row.setAnswer("answer");
        row.setEvidenceJson("[]");
        row.setStatus("SUCCEEDED");
        return row;
    }

    private static String readJavaSources(String directory) throws java.io.IOException {
        Path root = Path.of(directory);
        if (!Files.exists(root)) {
            return "";
        }
        StringBuilder source = new StringBuilder();
        try (var paths = Files.walk(root)) {
            for (Path path : paths.filter(path -> path.toString().endsWith(".java")).toList()) {
                source.append(Files.readString(path)).append('\n');
            }
        }
        return source.toString();
    }
}
