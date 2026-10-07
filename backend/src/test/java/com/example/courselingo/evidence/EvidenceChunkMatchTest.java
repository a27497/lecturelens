package com.example.courselingo.evidence;
import static org.assertj.core.api.Assertions.*;
import org.junit.jupiter.api.Test;
class EvidenceChunkMatchTest {
    @Test void codePointsAndUtf8FingerprintAgreeWithPythonBoundaries() {
        String text="😀".repeat(200)+"base case"+"界".repeat(91);
        String chunk=text.substring(text.offsetByCodePoints(0,200));
        var position=EvidenceChunkMatch.resolve(text,EvidenceChunkMatch.fingerprint(chunk));
        assertThat(position.start()).isEqualTo(200);assertThat(position.end()).isEqualTo(300);
        assertThat(position.text()).isEqualTo(chunk);
    }
    @Test void identicalChunksProveTextButNeverInventAPosition() {
        var result=EvidenceChunkMatch.resolve("a".repeat(650),EvidenceChunkMatch.fingerprint("a".repeat(240)));
        assertThat(result.start()).isNull();assertThat(result.end()).isNull();
        assertThat(result.text()).isEqualTo("a".repeat(240));
    }
    @Test void unknownAndNonBoundaryHashesFailClosed() {
        String text="a".repeat(200)+"b".repeat(200)+"c".repeat(200);
        assertThatThrownBy(()->EvidenceChunkMatch.resolve(text,EvidenceChunkMatch.fingerprint(text.substring(10,250))))
            .isInstanceOf(IllegalArgumentException.class);
        assertThatThrownBy(()->EvidenceChunkMatch.resolve(text,"invalid")).isInstanceOf(IllegalArgumentException.class);
    }
}
