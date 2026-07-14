package com.example.courselingo.storage;

import java.io.InputStream;
import java.nio.file.Path;

public interface StorageService {

    void putObject(String objectKey, Path sourceFile, long sizeBytes, String contentType);

    InputStream openObject(String objectKey);

    boolean objectExists(String objectKey);

    void deleteObject(String objectKey);
}
