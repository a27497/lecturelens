package baseline.measurement;

import com.example.courselingo.CourseLingoBackendApplication;
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import java.lang.reflect.Field;
import java.lang.reflect.InvocationTargetException;
import java.lang.reflect.Proxy;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardOpenOption;
import java.time.Instant;
import java.util.LinkedHashMap;
import java.util.Map;
import org.springframework.beans.factory.config.BeanPostProcessor;
import org.springframework.boot.SpringApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

/** Evaluation-only response tee: original provider, transport, bytes and timeout. */
public final class BaselineBootstrap {
    private static final ObjectMapper JSON = new ObjectMapper();
    private static final Object LOCK = new Object();

    public static void main(String[] args) {
        SpringApplication.run(new Class<?>[] {CourseLingoBackendApplication.class, MeterConfig.class}, args);
    }

    @Configuration(proxyBeanMethods = false)
    public static class MeterConfig {
        @Bean
        public static BeanPostProcessor responseMeter() {
            return new BeanPostProcessor() {
                @Override
                public Object postProcessAfterInitialization(Object bean, String name) {
                    if (!bean.getClass().getName().equals("com.example.courselingo.ai.asr.BailianAsrProvider")) {
                        return bean;
                    }
                    try {
                        Field field = bean.getClass().getDeclaredField("transport");
                        field.setAccessible(true);
                        Object original = field.get(bean);
                        Class<?> contract = field.getType();
                        Object observed = Proxy.newProxyInstance(contract.getClassLoader(), new Class<?>[] {contract},
                            (proxy, method, arguments) -> {
                                if (!method.getName().equals("send")) {
                                    method.setAccessible(true);
                                    return method.invoke(original, arguments);
                                }
                                Map<String, Object> record = new LinkedHashMap<>();
                                Path base = Path.of(System.getenv("ASR_BASELINE_PRIVATE"));
                                JsonNode marker = JSON.readTree(Files.readString(base.resolve("active-trial.json")));
                                record.put("trial_id", marker.path("trial_id").asText());
                                record.put("kind", "asr");
                                record.put("started_at_utc", Instant.now().toString());
                                record.put("thread", Thread.currentThread().getName());
                                long started = System.nanoTime();
                                try {
                                    method.setAccessible(true);
                                    Object response = method.invoke(original, arguments);
                                    var body = response.getClass().getDeclaredMethod("body");
                                    var status = response.getClass().getDeclaredMethod("statusCode");
                                    body.setAccessible(true);
                                    status.setAccessible(true);
                                    JsonNode parsed = JSON.readTree((String) body.invoke(response));
                                    record.put("http_status", status.invoke(response));
                                    record.put("usage", parsed.get("usage"));
                                    record.put("error_code", parsed.path("code").asText(null));
                                    return response;
                                } catch (InvocationTargetException error) {
                                    record.put("http_status", null);
                                    record.put("usage", null);
                                    record.put("error_type", error.getCause().getClass().getSimpleName());
                                    throw error.getCause();
                                } finally {
                                    record.put("upstream_elapsed_ms", (System.nanoTime() - started) / 1_000_000.0);
                                    record.put("finished_at_utc", Instant.now().toString());
                                    synchronized (LOCK) {
                                        Files.writeString(Path.of(System.getenv("ASR_BASELINE_CALLS")),
                                            JSON.writeValueAsString(record) + "\n",
                                            StandardOpenOption.CREATE, StandardOpenOption.APPEND);
                                    }
                                }
                            });
                        field.set(bean, observed);
                        return bean;
                    } catch (ReflectiveOperationException error) {
                        throw new IllegalStateException("Cannot install evaluation response observer", error);
                    }
                }
            };
        }
    }
}
