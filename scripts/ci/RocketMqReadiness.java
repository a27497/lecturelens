import java.time.Duration;
import org.apache.rocketmq.client.apis.ClientConfiguration;
import org.apache.rocketmq.client.apis.ClientServiceProvider;

/** Probe the same gRPC endpoint and topic route as the application, without sending a message. */
class RocketMqReadiness {
    public static void main(String[] args) throws Exception {
        var provider = ClientServiceProvider.loadService();
        var configuration = ClientConfiguration.newBuilder()
            .setEndpoints(args[0])
            .enableSsl(Boolean.parseBoolean(args[2]))
            .setRequestTimeout(Duration.ofMillis(Long.parseLong(args[3])))
            .build();
        long deadline = System.nanoTime() + Duration.ofSeconds(90).toNanos();
        Exception lastFailure = null;
        do {
            try (var producer = provider.newProducerBuilder()
                    .setClientConfiguration(configuration).setTopics(args[1]).build()) {
                System.out.println("PASS RocketMQ client endpoint and topic route ready");
                return;
            } catch (Exception exception) {
                lastFailure = exception;
                System.err.println("WAIT RocketMQ client readiness: " + exception.getClass().getSimpleName());
                Thread.sleep(2000);
            }
        } while (System.nanoTime() < deadline);
        throw new IllegalStateException("RocketMQ client readiness deadline exceeded", lastFailure);
    }
}
