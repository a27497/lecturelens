package perf;

import com.example.courselingo.ai.llm.DemoMockLlmProvider;
import com.example.courselingo.ai.llm.LlmProvider;
import com.example.courselingo.ai.llm.LlmRequest;
import com.example.courselingo.ai.llm.LlmResult;
import org.springframework.beans.factory.config.BeanPostProcessor;
import org.springframework.context.ApplicationContextInitializer;
import org.springframework.context.ConfigurableApplicationContext;

/** Eval-only wrapper, loaded outside the packaged application; no replacement QA logic. */
public final class PerfDelayInitializer
        implements ApplicationContextInitializer<ConfigurableApplicationContext> {
    @Override
    public void initialize(ConfigurableApplicationContext context) {
        int delay = Integer.parseInt(System.getenv("PERF_MOCK_MODEL_DELAY_MS"));
        if (delay < 0 || delay > 5000) throw new IllegalArgumentException("Invalid mock delay");
        context.getBeanFactory().addBeanPostProcessor(new BeanPostProcessor() {
            @Override
            public Object postProcessAfterInitialization(Object bean, String name) {
                if (!(bean instanceof LlmProvider provider)) return bean;
                if (!(provider instanceof DemoMockLlmProvider)) {
                    throw new IllegalStateException("Perf forbids non-demo LlmProvider");
                }
                System.out.println("PERF_MOCK_QA_WRAPPER delay_ms=" + delay);
                return new LlmProvider() {
                    @Override
                    public LlmResult generate(LlmRequest request) {
                        if ("COURSE_QA".equals(request.metadata().get("stage"))) {
                            try {
                                Thread.sleep(delay);
                            } catch (InterruptedException interrupted) {
                                Thread.currentThread().interrupt();
                                throw new IllegalStateException("Perf mock interrupted", interrupted);
                            }
                            System.out.println("PERF_MOCK_QA_DECIDE delay_ms=" + delay);
                        }
                        return provider.generate(request);
                    }
                    @Override public String providerName() { return provider.providerName(); }
                    @Override public String modelNameForDiagnostics() {
                        return provider.modelNameForDiagnostics();
                    }
                };
            }
        });
    }
}
