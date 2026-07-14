package com.example.courselingo.media;

import com.example.courselingo.common.error.ErrorCode;
import com.example.courselingo.common.exception.BusinessException;

public class MediaRangeNotSatisfiableException extends BusinessException {

    private final long sizeBytes;

    public MediaRangeNotSatisfiableException(long sizeBytes) {
        super(ErrorCode.MEDIA_RANGE_NOT_SATISFIABLE);
        this.sizeBytes = sizeBytes;
    }

    public long sizeBytes() {
        return sizeBytes;
    }
}
