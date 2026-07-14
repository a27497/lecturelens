package com.example.courselingo.artifact.service;

import com.example.courselingo.artifact.dto.ArtifactFileView;

public interface MarkdownArtifactService {

    ArtifactFileView generateMarkdownArtifact(GenerateMarkdownArtifactCommand command);
}
