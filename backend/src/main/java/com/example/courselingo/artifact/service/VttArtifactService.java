package com.example.courselingo.artifact.service;

import com.example.courselingo.artifact.dto.ArtifactFileView;

public interface VttArtifactService {

    ArtifactFileView generateVttArtifact(GenerateVttArtifactCommand command);
}
