package com.example.courselingo.artifact.service;

import com.example.courselingo.artifact.dto.ArtifactFileView;

public interface SrtArtifactService {

    ArtifactFileView generateSrtArtifact(GenerateSrtArtifactCommand command);
}
