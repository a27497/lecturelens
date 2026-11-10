package perf;

import org.springframework.boot.SpringApplication;

/** Same primary application source as Start-Class, plus the eval-only Mock wrapper. */
public final class PerfMain {
    public static void main(String[] args) throws ClassNotFoundException {
        Class<?> original = Class.forName(System.getenv("PERF_APP_MAIN_CLASS"));
        SpringApplication application = new SpringApplication(original);
        application.addInitializers(new PerfDelayInitializer());
        application.run(args);
    }
}
