package com.example.courselingo.vision.keyframe;

import java.util.List;

public interface VideoKeyframeService {

    List<VideoKeyframeView> listKeyframes(String authorizationHeader, String taskId);

    VideoKeyframeImage downloadKeyframeImage(String authorizationHeader, String taskId, Long frameId);
}
