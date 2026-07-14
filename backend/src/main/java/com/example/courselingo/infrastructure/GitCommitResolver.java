package com.example.courselingo.infrastructure;

@FunctionalInterface
interface GitCommitResolver {

    String resolveGitCommit();
}
