package com.example.courselingo.ai.asr;

import com.example.courselingo.systemmodel.SystemModelProtocol;
import com.example.courselingo.systemmodel.SystemModelResolvedRoute;

public interface AsrAdapterFactory {
    SystemModelProtocol protocol();

    SpeechToTextProvider create(SystemModelResolvedRoute route, String credential);
}
