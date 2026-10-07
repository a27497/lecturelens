package com.example.courselingo.ai.asr;

import java.util.ArrayList;
import java.util.List;
import org.springframework.context.annotation.Condition;
import org.springframework.context.annotation.ConditionContext;
import org.springframework.core.env.Environment;
import org.springframework.core.type.AnnotatedTypeMetadata;

/** Explicit selection wins; legacy flags remain supported only when unambiguous. */
final class AsrProviderSelection {
    private static final String PREFIX = "courselingo.ai.asr.";

    private static String selected(Environment environment) {
        String explicit = environment.getProperty(PREFIX + "provider", "").strip();
        if (!explicit.isEmpty()) {
            if (!List.of("bailian", "siliconflow", "mock", "none").contains(explicit)) {
                throw new IllegalStateException("Unknown ASR provider selection");
            }
            return explicit;
        }
        List<String> enabled = new ArrayList<>();
        for (String name : List.of("bailian", "silicon-flow", "mock")) {
            if (environment.getProperty(PREFIX + name + ".enabled", Boolean.class, false)) {
                enabled.add(name.replace("-", ""));
            }
        }
        if (enabled.size() > 1) {
            throw new IllegalStateException("Multiple legacy ASR providers enabled; set courselingo.ai.asr.provider");
        }
        return enabled.isEmpty() ? "none" : enabled.getFirst();
    }

    abstract static class Selected implements Condition {
        private final String name;
        Selected(String name) { this.name = name; }
        @Override
        public boolean matches(ConditionContext context, AnnotatedTypeMetadata metadata) {
            return name.equals(selected(context.getEnvironment()));
        }
    }
    static final class Bailian extends Selected { Bailian() { super("bailian"); } }
    static final class SiliconFlow extends Selected { SiliconFlow() { super("siliconflow"); } }
    static final class Mock extends Selected { Mock() { super("mock"); } }
}
