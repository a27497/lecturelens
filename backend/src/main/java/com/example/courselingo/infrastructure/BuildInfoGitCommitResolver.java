package com.example.courselingo.infrastructure;

import org.springframework.beans.factory.ObjectProvider;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.info.BuildProperties;
import org.springframework.stereotype.Component;

@Component
class BuildInfoGitCommitResolver implements GitCommitResolver {

    private static final String UNKNOWN = "unknown";
    private static final String GIT_COMMIT_PROPERTY = "gitCommit";

    private final BuildProperties buildProperties;

    @Autowired
    BuildInfoGitCommitResolver(ObjectProvider<BuildProperties> provider) {
        this(provider.getIfAvailable());
    }

    BuildInfoGitCommitResolver(BuildProperties buildProperties) {
        this.buildProperties = buildProperties;
    }

    @Override
    public String resolveGitCommit() {
        if (buildProperties == null) {
            return UNKNOWN;
        }
        String value = buildProperties.get(GIT_COMMIT_PROPERTY);
        return value == null || value.isBlank() ? UNKNOWN : value.strip();
    }
}
