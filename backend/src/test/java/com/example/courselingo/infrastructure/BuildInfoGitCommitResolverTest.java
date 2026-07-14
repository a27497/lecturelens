package com.example.courselingo.infrastructure;

import static org.assertj.core.api.Assertions.assertThat;

import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.Properties;
import org.junit.jupiter.api.Test;
import org.springframework.boot.info.BuildProperties;

class BuildInfoGitCommitResolverTest {

    private static final String FULL_SHA = "0123456789abcdef0123456789abcdef01234567";
    private static final Path RESOLVER_SOURCE = Path.of(
        "src",
        "main",
        "java",
        "com",
        "example",
        "courselingo",
        "infrastructure",
        "BuildInfoGitCommitResolver.java"
    );

    @Test
    void returnsGitCommitEmbeddedInBuildProperties() {
        BuildInfoGitCommitResolver resolver = resolverWithGitCommit(FULL_SHA);

        assertThat(resolver.resolveGitCommit()).isEqualTo(FULL_SHA);
    }

    @Test
    void stripsWhitespaceAroundEmbeddedGitCommit() {
        BuildInfoGitCommitResolver resolver = resolverWithGitCommit("  " + FULL_SHA + "\n");

        assertThat(resolver.resolveGitCommit()).isEqualTo(FULL_SHA);
    }

    @Test
    void returnsUnknownWhenEmbeddedGitCommitIsBlank() {
        BuildInfoGitCommitResolver resolver = resolverWithGitCommit(" \t\n ");

        assertThat(resolver.resolveGitCommit()).isEqualTo("unknown");
    }

    @Test
    void returnsUnknownWhenBuildPropertiesAreUnavailable() {
        BuildInfoGitCommitResolver resolver = resolverWithBuildProperties(null);

        assertThat(resolver.resolveGitCommit()).isEqualTo("unknown");
    }

    @Test
    void sourceNeverReadsGitOrStartsAProcess() throws Exception {
        String source = Files.readString(RESOLVER_SOURCE, StandardCharsets.UTF_8);

        assertThat(source).doesNotContain("ProcessBuilder", "git rev-parse", "Runtime.exec");
    }

    @Test
    void checkoutStateCannotOverrideEmbeddedCommit() {
        BuildInfoGitCommitResolver resolver = resolverWithGitCommit(FULL_SHA);

        assertThat(resolver.resolveGitCommit()).isEqualTo(FULL_SHA);
    }

    private BuildInfoGitCommitResolver resolverWithGitCommit(String value) {
        Properties properties = new Properties();
        properties.setProperty("gitCommit", value);
        return resolverWithBuildProperties(new BuildProperties(properties));
    }

    private BuildInfoGitCommitResolver resolverWithBuildProperties(BuildProperties buildProperties) {
        return new BuildInfoGitCommitResolver(buildProperties);
    }
}
