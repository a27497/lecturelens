ALTER TABLE video_keyframe
    ADD COLUMN quality_score DECIMAL(10,6) NULL COMMENT 'Explainable adaptive frame quality score' AFTER size_bytes,
    ADD COLUMN sharpness_score DECIMAL(16,4) NULL COMMENT 'Laplacian variance on a reduced grayscale frame' AFTER quality_score,
    ADD COLUMN brightness_mean DECIMAL(10,4) NULL COMMENT 'Mean grayscale brightness in range 0..255' AFTER sharpness_score,
    ADD COLUMN brightness_variance DECIMAL(16,4) NULL COMMENT 'Grayscale brightness variance' AFTER brightness_mean,
    ADD COLUMN edge_density DECIMAL(10,6) NULL COMMENT 'Normalized edge density' AFTER brightness_variance,
    ADD COLUMN perceptual_hash VARCHAR(32) NULL COMMENT 'Small grayscale perceptual hash, never image content' AFTER edge_density,
    ADD COLUMN degraded BOOLEAN NULL COMMENT 'True when a periodic coverage anchor used relaxed quality thresholds' AFTER perceptual_hash,
    ADD COLUMN source_type VARCHAR(32) NULL COMMENT 'START, END, SCENE_CHANGE, CONTENT_CHANGE, PERIODIC_ANCHOR, or WINDOW_COVERAGE' AFTER degraded;
