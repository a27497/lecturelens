package com.example.courselingo.upload.service;

import com.example.courselingo.common.error.ErrorCode;
import com.example.courselingo.common.exception.BusinessException;
import java.io.IOException;
import java.io.InputStream;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.Locale;
import java.util.Set;
import org.springframework.stereotype.Component;

@Component
public class BasicVideoHeaderValidator {

    private static final int BMFF_SCAN_BYTES = 64;
    private static final int BMFF_BOX_HEADER_BYTES = 8;
    private static final byte[] EBML_MAGIC = new byte[] {0x1A, 0x45, (byte) 0xDF, (byte) 0xA3};
    private static final Set<String> BMFF_EXTENSIONS = Set.of("mp4", "mov");
    private static final Set<String> EBML_EXTENSIONS = Set.of("mkv", "webm");

    public void validate(Path file, String ext) {
        String normalizedExt = normalizeExt(ext);
        if (BMFF_EXTENSIONS.contains(normalizedExt)) {
            validateBmff(file);
            return;
        }
        if (EBML_EXTENSIONS.contains(normalizedExt)) {
            validateEbml(file);
            return;
        }
        throw new BusinessException(ErrorCode.UPLOAD_INVALID_EXTENSION);
    }

    private String normalizeExt(String ext) {
        if (ext == null || ext.isBlank()) {
            throw new BusinessException(ErrorCode.UPLOAD_INVALID_EXTENSION);
        }
        return ext.toLowerCase(Locale.ROOT);
    }

    private void validateBmff(Path file) {
        byte[] header = readPrefix(file, BMFF_SCAN_BYTES);
        if (header.length < BMFF_BOX_HEADER_BYTES) {
            throw new BusinessException(ErrorCode.UPLOAD_INVALID_VIDEO_HEADER);
        }
        int offset = 0;
        while (offset <= header.length - BMFF_BOX_HEADER_BYTES) {
            long boxSize = unsignedInt(header, offset);
            if (isBoxType(header, offset + 4, "ftyp")) {
                if (boxSize >= BMFF_BOX_HEADER_BYTES && offset + boxSize <= header.length) {
                    return;
                }
                throw new BusinessException(ErrorCode.UPLOAD_INVALID_VIDEO_HEADER);
            }
            if (boxSize < BMFF_BOX_HEADER_BYTES) {
                break;
            }
            long nextOffset = offset + boxSize;
            if (nextOffset > Integer.MAX_VALUE || nextOffset <= offset) {
                break;
            }
            offset = (int) nextOffset;
        }
        throw new BusinessException(ErrorCode.UPLOAD_INVALID_VIDEO_HEADER);
    }

    private void validateEbml(Path file) {
        byte[] header = readPrefix(file, EBML_MAGIC.length);
        if (header.length < EBML_MAGIC.length) {
            throw new BusinessException(ErrorCode.UPLOAD_INVALID_VIDEO_HEADER);
        }
        for (int i = 0; i < EBML_MAGIC.length; i++) {
            if (header[i] != EBML_MAGIC[i]) {
                throw new BusinessException(ErrorCode.UPLOAD_INVALID_VIDEO_HEADER);
            }
        }
    }

    private byte[] readPrefix(Path file, int maxBytes) {
        try {
            if (!Files.isRegularFile(file) || Files.size(file) <= 0) {
                throw new BusinessException(ErrorCode.UPLOAD_INVALID_VIDEO_HEADER);
            }
            byte[] buffer = new byte[maxBytes];
            int read;
            try (InputStream inputStream = Files.newInputStream(file)) {
                read = inputStream.read(buffer);
            }
            if (read <= 0) {
                throw new BusinessException(ErrorCode.UPLOAD_INVALID_VIDEO_HEADER);
            }
            return java.util.Arrays.copyOf(buffer, read);
        } catch (IOException exception) {
            throw new BusinessException(ErrorCode.UPLOAD_MERGE_FAILED, exception);
        }
    }

    private long unsignedInt(byte[] bytes, int offset) {
        return ((long) bytes[offset] & 0xff) << 24
            | ((long) bytes[offset + 1] & 0xff) << 16
            | ((long) bytes[offset + 2] & 0xff) << 8
            | ((long) bytes[offset + 3] & 0xff);
    }

    private boolean isBoxType(byte[] bytes, int offset, String type) {
        return bytes[offset] == type.charAt(0)
            && bytes[offset + 1] == type.charAt(1)
            && bytes[offset + 2] == type.charAt(2)
            && bytes[offset + 3] == type.charAt(3);
    }
}
