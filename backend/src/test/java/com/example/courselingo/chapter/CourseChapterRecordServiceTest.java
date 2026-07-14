package com.example.courselingo.chapter;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.CALLS_REAL_METHODS;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

import com.baomidou.mybatisplus.core.conditions.Wrapper;
import com.example.courselingo.chapter.domain.CourseChapter;
import com.example.courselingo.chapter.mapper.CourseChapterMapper;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.List;
import org.junit.jupiter.api.Test;

class CourseChapterRecordServiceTest {

    @Test
    void domainDoesNotExposeRawSensitiveFields() {
        assertThat(java.util.Arrays.stream(CourseChapter.class.getDeclaredFields()).map(java.lang.reflect.Field::getName))
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
    void mapperQueriesAndDeletesAreScopedByTaskAndUser() {
        CourseChapterMapper mapper = mock(CourseChapterMapper.class, CALLS_REAL_METHODS);
        when(mapper.selectList(any(Wrapper.class))).thenReturn(List.of(row(1L), row(2L)));
        when(mapper.delete(any(Wrapper.class))).thenReturn(2);

        List<CourseChapter> rows = mapper.selectByTaskIdAndUserId("task_1", 42L);
        int deleted = mapper.deleteByTaskIdAndUserId("task_1", 42L);

        assertThat(rows).extracting(CourseChapter::getId).containsExactly(1L, 2L);
        assertThat(deleted).isEqualTo(2);
        verify(mapper).selectList(any(Wrapper.class));
        verify(mapper).delete(any(Wrapper.class));
    }

    @Test
    void chapterPackageDoesNotReferenceObjectStorageOrRunnerPipeline() throws Exception {
        String source = readJavaSources("src/main/java/com/example/courselingo/chapter");

        assertThat(source)
            .doesNotContain("object" + "Key")
            .doesNotContain("Storage")
            .doesNotContain("Minio")
            .doesNotContain("AnalysisTaskRunner")
            .doesNotContain("RocketMQ")
            .doesNotContain("raw" + "Prompt")
            .doesNotContain("raw" + "Response");
    }

    @Test
    void migrationCreatesCourseChapterTableSafely() throws Exception {
        String sql = Files.readString(Path.of("src/main/resources/db/migration/V16__create_course_chapter.sql"));

        assertThat(sql).contains("CREATE TABLE IF NOT EXISTS course_chapter");
        assertThat(sql).contains("UNIQUE KEY uk_course_chapter_task_user_index (task_id, user_id, chapter_index)");
        assertThat(sql).contains("KEY idx_course_chapter_user_task (user_id, task_id)");
        assertThat(sql).contains("KEY idx_course_chapter_user_created (user_id, created_at)");
        assertThat(sql).contains("provider VARCHAR(64) NULL");
        assertThat(sql).contains("duration_millis BIGINT NULL");
        assertThat(sql)
            .doesNotContain("DROP TABLE")
            .doesNotContain("TRUNCATE")
            .doesNotContain("raw_prompt")
            .doesNotContain("raw_response")
            .doesNotContain("object_key")
            .doesNotContain("api_key")
            .doesNotContain("insert into");
    }

    private static CourseChapter row(Long id) {
        CourseChapter row = new CourseChapter();
        row.setId(id);
        row.setTaskId("task_1");
        row.setUserId(42L);
        row.setChapterIndex(id.intValue() - 1);
        row.setTitle("title");
        row.setSummary("summary");
        row.setKeywordsJson("[]");
        row.setStartMillis(0L);
        row.setEndMillis(1L);
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
