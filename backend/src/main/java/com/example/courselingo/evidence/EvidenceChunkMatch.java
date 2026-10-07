package com.example.courselingo.evidence;

import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.util.HexFormat;

/** Resolve the legacy hash-only projection against authoritative normalized text. */
public final class EvidenceChunkMatch {
    private EvidenceChunkMatch() { }

    public record Position(Integer start, Integer end, String text) { }

    public static Position resolve(String canonical, String hash) {
        if (hash == null || !hash.matches("[0-9a-f]{64}")) {
            throw new IllegalArgumentException("Invalid chunk fingerprint");
        }
        int length = canonical.codePointCount(0, canonical.length());
        Position found = null;
        boolean ambiguous = false;
        // These are the existing Python splitter's boundaries, in Unicode code
        // points. Neither the batch chunk ID nor retrieval rank participates.
        for (int start = 0; start < length; start += 200) {
            int end = Math.min(start + 240, length);
            String text = canonical.substring(canonical.offsetByCodePoints(0, start),
                canonical.offsetByCodePoints(0, end));
            if (fingerprint(text).equals(hash)) {
                if (found != null) ambiguous = true;
                else found = new Position(start, end, text);
            }
            if (end == length) break;
        }
        if (found == null) throw new IllegalArgumentException("Chunk does not match canonical text");
        // Repeated identical chunks prove the text but not its location. Preserve
        // that excerpt without fabricating a position or changing source time.
        return ambiguous ? new Position(null, null, found.text()) : found;
    }

    public static String fingerprint(String text) {
        try {
            return HexFormat.of().formatHex(MessageDigest.getInstance("SHA-256")
                .digest(text.getBytes(StandardCharsets.UTF_8)));
        } catch (NoSuchAlgorithmException impossible) {
            throw new IllegalStateException(impossible);
        }
    }
}
