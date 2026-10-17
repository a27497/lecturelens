package com.example.courselingo.systemmodel;

import com.example.courselingo.CourseLingoBackendApplication;
import com.example.courselingo.ai.llm.*;
import com.example.courselingo.modelrouting.*;
import org.springframework.boot.*;
import org.springframework.boot.context.event.ApplicationEnvironmentPreparedEvent;
import org.springframework.boot.context.properties.bind.Binder;
import org.springframework.context.ApplicationListener;
import org.springframework.beans.factory.config.BeanPostProcessor;
import java.nio.file.*;
import java.sql.*;
import java.util.*;

/** Evaluation instrumentation; the candidate classes and their bytes remain frozen. */
public class P21Bootstrap {
    static Path privateRoot = Path.of(System.getProperty("p21.private"));
    static boolean shouldBlock(long succeeded, long total) {
        return succeeded >= 2 && total > succeeded && succeeded * 2 >= total;
    }
    static void requireIdentity(long version, String stored, String captured) {
        if (version != 10 || !Objects.equals(stored, captured)) throw new IllegalStateException("P21_CAPTURE_IDENTITY_MISMATCH");
    }
    static Connection connection() throws Exception {
        return DriverManager.getConnection(System.getenv("MYSQL_JDBC_URL"), System.getenv("MYSQL_USERNAME"), System.getenv("MYSQL_PASSWORD"));
    }
    public static void main(String[] args) throws Exception {
        if(args.length>0 && args[0].equals("mqcheck")) {
            try {
                var configuration=org.apache.rocketmq.client.apis.ClientConfiguration.newBuilder().setEndpoints(System.getenv("ROCKETMQ_ENDPOINT"))
                    .setRequestTimeout(java.time.Duration.ofSeconds(3)).enableSsl(false).build();
                try(var p=org.apache.rocketmq.client.apis.ClientServiceProvider.loadService().newProducerBuilder().setClientConfiguration(configuration).setTopics(System.getenv("ROCKETMQ_ANALYSIS_TOPIC")).build()) {
                    System.out.println("P21_MQ_CLIENT_PASS");
                }
            } catch(Exception e){for(Throwable t=e;t!=null;t=t.getCause())System.out.println("P21_MQ_CAUSE "+t.getClass().getSimpleName()+" "+t.getMessage());System.exit(43);}
            return;
        }
        if(args.length>0 && args[0].equals("migrate")) {
            if(!System.getenv("MYSQL_JDBC_URL").contains("/lecturelens_p21_20261016?"))throw new IllegalStateException();
            org.flywaydb.core.Flyway.configure().dataSource(System.getenv("MYSQL_JDBC_URL"),System.getenv("MYSQL_USERNAME"),System.getenv("MYSQL_PASSWORD"))
                .locations("classpath:db/migration").load().migrate();
            System.out.println("P21_MIGRATE_PASS");return;
        }
        if (args.length > 0 && args[0].equals("selftest")) {
            if (shouldBlock(1, 2) || shouldBlock(2, 2) || shouldBlock(2, 5) || !shouldBlock(3, 6)) throw new AssertionError();
            requireIdentity(10, "same", "same");
            for (int i=0;i<2;i++) {
                boolean rejected=false;
                try {requireIdentity(i==0?11:10,"same",i==0?"same":"different");} catch(IllegalStateException expected){rejected=true;}
                if(!rejected)throw new AssertionError();
            }
            var armed=Files.createTempFile(privateRoot,"mock-barrier-", ".armed");
            var calls=new java.util.concurrent.atomic.AtomicInteger();
            var entered=new java.util.concurrent.CountDownLatch(1);
            var t=new Thread(()->{try{entered.countDown();waitWhileArmed(armed);calls.incrementAndGet();}catch(Exception e){throw new RuntimeException(e);}});
            t.start();entered.await();Thread.sleep(200);
            if(calls.get()!=0)throw new AssertionError("provider reached during barrier");
            Files.delete(armed);t.join(2000);
            if(t.isAlive()||calls.get()!=1)throw new AssertionError("barrier failed to release");
            System.out.println("P21_SELFTEST_PASS identity_match,version_rejection,fingerprint_rejection,barrier_threshold,zero_dispatch_while_blocked,release_once");
            return;
        }
        boolean preflight = args.length > 0 && args[0].equals("preflight");
        String[] appArgs=preflight?Arrays.copyOfRange(args,1,args.length):args;
        var app = new SpringApplication(CourseLingoBackendApplication.class);
        app.addListeners((ApplicationListener<ApplicationEnvironmentPreparedEvent>) event -> {
            try {
                var env=event.getEnvironment();
                var binder=Binder.get(env);
                var text=binder.bind("courselingo.ai.llm.openai-compatible",OpenAiCompatibleLlmProperties.class).orElseGet(OpenAiCompatibleLlmProperties::new);
                var routing=binder.bind("courselingo.ai.model-routing",AiModelRoutingProperties.class).orElseGet(AiModelRoutingProperties::new);
                var captured=new SystemModelEnvironment(env,new AiModelRouter(routing),text,new SystemModelSecretCipher()).capture();
                try(var c=connection();var s=c.createStatement();var r=s.executeQuery("SELECT v.version,v.config_json,v.config_sha256 FROM system_model_config_state s JOIN system_model_config_version v ON v.version=s.current_version WHERE s.id=1")) {
                    if(!r.next())throw new IllegalStateException();
                    var stored=new SystemModelConfigCodec().decode(r.getString(2),r.getString(3));
                    requireIdentity(r.getLong(1),stored.environmentFingerprint(),captured.fingerprint());
                    System.out.println("P21_CAPTURE_GATE_PASS version=10 fingerprint_equal=true");
                }
                if(preflight)System.exit(0);
            } catch(Exception e){System.err.println("P21_CAPTURE_GATE_FAILED "+e.getClass().getSimpleName());System.exit(42);}
        });
        app.addInitializers(context -> context.addBeanFactoryPostProcessor(factory -> factory.addBeanPostProcessor(new BeanPostProcessor() {
            @Override public Object postProcessAfterInitialization(Object bean,String name) {
                if(!(bean instanceof LlmProvider provider))return bean;
                return new LlmProvider() {
                    public String providerName(){return provider.providerName();}
                    public String modelNameForDiagnostics(){return provider.modelNameForDiagnostics();}
                    public LlmResult generate(LlmRequest request) {
                        if(Boolean.TRUE.equals(request.metadata().get("translationV2")))barrier(request.taskId());
                        return provider.generate(request);
                    }
                };
            }
        })));
        app.run(appArgs);
    }
    static void barrier(String task) {
        Path armed=privateRoot.resolve("recovery-armed");
        try {
            if(!Files.exists(armed)||!Files.readString(armed).trim().equals(task))return;
            try(var c=connection();var s=c.prepareStatement("SELECT SUM(status='SUCCEEDED') done,COUNT(*) total FROM translation_batch WHERE task_id=? AND parent_batch_no IS NULL")) {
                s.setString(1,task);
                try(var r=s.executeQuery()){r.next();if(!shouldBlock(r.getLong(1),r.getLong(2)))return;}
            }
            // No HTTP call has reached the provider/usage observer at this barrier. A checkpoint
            // attempt may already exist, so recovery evidence distinguishes reservations from calls.
            Files.writeString(privateRoot.resolve("recovery-barrier-reached"),task);
            waitWhileArmed(armed);
        } catch(Exception e){throw new IllegalStateException("P21_BARRIER_FAILED");}
    }
    static void waitWhileArmed(Path armed)throws InterruptedException {while(Files.exists(armed))Thread.sleep(100);}
}
