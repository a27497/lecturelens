package com.example.courselingo.storage;

import static org.assertj.core.api.Assertions.assertThat;

import io.minio.Xml;
import io.minio.messages.InitiateMultipartUploadResult;
import java.io.StringReader;
import org.junit.jupiter.api.Test;

class MinioXmlSecurityTest {
    private static final String PROPERTY = "lecturelens.test.xml.sentinel";

    @Test
    void s3UploadIdsNeverResolveProcessPropertiesThroughEitherXmlInput() throws Exception {
        String previous = System.getProperty(PROPERTY);
        System.setProperty(PROPERTY, "synthetic-private-value");
        try {
            String literal = "${" + PROPERTY + "}";
            String xml = upload(literal);
            assertThat(Xml.unmarshal(InitiateMultipartUploadResult.class, xml).uploadId()).isEqualTo(literal);
            assertThat(Xml.unmarshal(InitiateMultipartUploadResult.class, new StringReader(xml)).uploadId())
                .isEqualTo(literal);
        } finally {
            if (previous == null) System.clearProperty(PROPERTY);
            else System.setProperty(PROPERTY, previous);
        }
    }

    @Test
    void ordinaryMultipartResponseRetainsItsUploadId() throws Exception {
        assertThat(Xml.unmarshal(InitiateMultipartUploadResult.class, upload("ordinary-upload")).uploadId())
            .isEqualTo("ordinary-upload");
    }

    private String upload(String id) {
        return "<InitiateMultipartUploadResult><Bucket>test-bucket</Bucket>"
            + "<Key>synthetic.mp4</Key><UploadId>" + id + "</UploadId></InitiateMultipartUploadResult>";
    }
}
