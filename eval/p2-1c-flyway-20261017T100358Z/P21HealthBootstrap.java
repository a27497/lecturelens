package com.example.courselingo.systemmodel;

import com.example.courselingo.CourseLingoBackendApplication;
import com.example.courselingo.ai.llm.OpenAiCompatibleLlmProperties;
import com.example.courselingo.modelrouting.*;
import com.fasterxml.jackson.core.*;
import com.fasterxml.jackson.databind.*;
import java.net.URI;
import java.nio.file.*;
import java.sql.*;
import java.util.*;
import java.util.regex.Pattern;
import org.springframework.boot.*;
import org.springframework.boot.autoconfigure.flyway.FlywayMigrationStrategy;
import org.springframework.boot.context.event.ApplicationEnvironmentPreparedEvent;
import org.springframework.boot.context.properties.bind.Binder;
import org.springframework.context.ApplicationListener;
import org.springframework.context.annotation.*;
import org.springframework.core.Ordered;
import org.springframework.core.env.*;

/** Evaluation adapter: one JVM; frozen application Flyway runs before v10 import. */
public final class P21HealthBootstrap {
    static final Path ROOT=Path.of("/home/dev/projects/lecturelens");
    static final Path PRIVATE=Path.of(System.getProperty("p21.private"));
    static final String SCHEMA="lecturelens_p21c_20261017";
    static final ObjectMapper JSON=new ObjectMapper();
    static ConfigurableEnvironment environment;
    static String fingerprint;
    static void require(boolean ok) { if(!ok)throw new IllegalStateException("P21_HEALTH_GATE"); }

    static final class ConfigurationInput implements ApplicationListener<ApplicationEnvironmentPreparedEvent>,Ordered {
        public int getOrder(){return Ordered.LOWEST_PRECEDENCE-2;}
        public void onApplicationEvent(ApplicationEnvironmentPreparedEvent event) {
            try {
                require("dev".equals(System.getProperty("user.name")));
                environment=event.getEnvironment();
                String config;
                try(var in=P21HealthBootstrap.class.getResourceAsStream("/application.yml")) {
                    require(in!=null);config=new String(in.readAllBytes(),java.nio.charset.StandardCharsets.UTF_8);
                }
                config+=Files.readString(Path.of("/home/dev/projects/lecturelens-asr-b/.data/asr-b-deploy/asr-bailian.yml"));
                var names=new HashSet<String>();
                var matches=Pattern.compile("\\$\\{([A-Z][A-Z0-9_]*)").matcher(config);
                while(matches.find())names.add(matches.group(1));
                matches=Pattern.compile("api-key-env-name:\\s*[\"']?([A-Z][A-Z0-9_]*)").matcher(config);
                while(matches.find())names.add(matches.group(1));
                names.removeAll(Set.of("MYSQL_ROOT_PASSWORD","SYSTEM_MODEL_MASTER_KEY","SYSTEM_MODEL_CONFIG_ENABLED","FLYWAY_ENABLED"));
                var values=new HashMap<String,Object>();
                // Application process alone consumes approved configuration
                // references. Root password is skipped, never deserialized.
                try(var parser=JSON.getFactory().createParser(ROOT.resolve(".data/live-access/runtime.json").toFile())) {
                    require(parser.nextToken()==JsonToken.START_OBJECT);
                    while(parser.nextToken()!=JsonToken.END_OBJECT) {
                        String name=parser.currentName();parser.nextToken();
                        if(names.contains(name)) {
                            require(parser.currentToken()==JsonToken.VALUE_STRING);
                            values.put(name,parser.getText());
                        } else parser.skipChildren();
                    }
                }
                var credentials=JSON.readTree(Path.of(System.getenv("CREDENTIALS_DIRECTORY")).resolve("bailian-asr").toFile());
                for(String name:List.of("BAILIAN_ASR_API_KEY","BAILIAN_ASR_ENDPOINT","BAILIAN_ASR_MODEL")) {
                    require(credentials.path(name).isTextual()&&!credentials.path(name).asText().isBlank());
                    values.put(name,credentials.path(name).asText());
                }
                require("qwen-audio-3.1-asr-flash".equals(values.get("BAILIAN_ASR_MODEL")));
                var app=JSON.readTree(PRIVATE.resolve("app-credentials.json").toFile());
                require("p21c_app".equals(app.path("username").asText())&&app.path("port").asInt()==33319);
                values.put("MYSQL_JDBC_URL","jdbc:mysql://127.0.0.1:33319/"+SCHEMA+"?useSSL=false&allowPublicKeyRetrieval=true&serverTimezone=UTC");
                values.put("MYSQL_USERNAME",app.path("username").asText());values.put("MYSQL_PASSWORD",app.path("password").asText());
                values.put("APP_PORT","18091");values.put("SERVER_ADDRESS","127.0.0.1");
                values.put("REDIS_HOST","127.0.0.1");values.put("REDIS_PORT","33318");values.put("REDIS_PASSWORD","");values.put("REDIS_DATABASE","15");
                values.put("DENSE_RETRIEVAL_ENABLED","false");values.put("STUDY_AGENT_ENABLED","false");
                String topic="lecturelens-p21-20261016T073754Z";
                values.put("ROCKETMQ_ANALYSIS_TOPIC",topic);values.put("ROCKETMQ_PRODUCER_GROUP",topic+"-producer");values.put("ROCKETMQ_CONSUMER_GROUP",topic+"-consumer");
                values.put("ASR_PROVIDER","bailian");values.put("ASR_CHUNK_DURATION","180s");values.put("ASR_CHUNK_CONCURRENCY","2");
                values.put("ASR_MAX_AUDIO_FILE_SIZE","7MB");values.put("ASR_CHUNK_MAX_FILE_SIZE","6MB");
                environment.getPropertySources().addFirst(new MapPropertySource("p21-approved-runtime",values));
                require("127.0.0.1".equals(environment.getProperty("server.address"))&&environment.getProperty("server.port",Integer.class,0)==18091);
                var uri=URI.create(environment.getProperty("spring.datasource.url").substring(5));
                require("127.0.0.1".equals(uri.getHost())&&uri.getPort()==33319&&("/"+SCHEMA).equals(uri.getPath())&&uri.getUserInfo()==null);
                require("p21c_app".equals(environment.getProperty("spring.datasource.username")));
                require(environment.getProperty("spring.flyway.enabled",Boolean.class,false));
                require(environment.getProperty("spring.flyway.validate-on-migrate",Boolean.class,true));
                require(!environment.getProperty("spring.flyway.baseline-on-migrate",Boolean.class,false));
                require(environment.getProperty("courselingo.ai.system-models.enabled",Boolean.class,false));
                require(!environment.getProperty("courselingo.study.enabled",Boolean.class,true));
                require(!environment.getProperty("courselingo.retrieval.enabled",Boolean.class,true));
                require("127.0.0.1".equals(environment.getProperty("courselingo.redis.host"))&&environment.getProperty("courselingo.redis.port",Integer.class,0)==33318);
                require(environment.getProperty("courselingo.redis.database",Integer.class,-1)==15&&environment.getProperty("courselingo.redis.password","").isEmpty());
                require(topic.equals(environment.getProperty("courselingo.mq.rocketmq.analysis-topic")));
                require((topic+"-producer").equals(environment.getProperty("courselingo.mq.rocketmq.producer-group")));
                require((topic+"-consumer").equals(environment.getProperty("courselingo.mq.rocketmq.consumer-group")));
                require(Path.of(System.getProperty("java.io.tmpdir")).toRealPath().equals(PRIVATE.resolve("tmp").toRealPath()));
                require(Path.of(environment.getProperty("courselingo.task.runner.workspace-dir")).toRealPath().equals(PRIVATE.resolve("workspace").toRealPath()));
                var expected=JSON.readTree(Path.of(System.getProperty("p21.options")).toFile()).path("properties").fields();
                while(expected.hasNext()) { var field=expected.next();require(field.getValue().asText().equals(environment.getProperty(field.getKey()))); }
                var binder=Binder.get(environment);
                var text=binder.bind("courselingo.ai.llm.openai-compatible",OpenAiCompatibleLlmProperties.class).orElseGet(OpenAiCompatibleLlmProperties::new);
                var routing=binder.bind("courselingo.ai.model-routing",AiModelRoutingProperties.class).orElseGet(AiModelRoutingProperties::new);
                fingerprint=new SystemModelEnvironment(environment,new AiModelRouter(routing),text,new SystemModelSecretCipher()).capture().fingerprint();
                System.out.println("P21_FINAL_ISOLATION_GATE_PASS");
            } catch(Exception ignored) { System.out.println("P21_FINAL_ISOLATION_GATE_FAILED");System.exit(44); }
        }
    }

    @Configuration(proxyBeanMethods=false)
    static class MigrationImportBarrier {
        @Bean FlywayMigrationStrategy p21HealthMigrationStrategy() {
            return flyway -> {
                // This is Spring Boot's actual Flyway initializer. Keep normal
                // validation/migrations; withhold downstream DB initialization
                // until the encrypted configuration has been imported/verified.
                // Fence Flyway's actual datasource as well as Spring's URL;
                // never let a separate flyway.url reach a shared instance.
                try(var c=flyway.getConfiguration().getDataSource().getConnection()) {
                    var uri=URI.create(c.getMetaData().getURL().substring(5));
                    require("127.0.0.1".equals(uri.getHost())&&uri.getPort()==33319&&("/"+SCHEMA).equals(uri.getPath()));
                    try(var s=c.createStatement();var r=s.executeQuery("SELECT DATABASE(),@@log_bin")) {
                        require(r.next()&&SCHEMA.equals(r.getString(1))&&!r.getBoolean(2));
                    }
                } catch(SQLException ignored) { throw new IllegalStateException("P21_FLYWAY_DATASOURCE_GATE"); }
                flyway.migrate();
                require(flyway.info().applied().length==32);
                System.out.println("P21_MIGRATIONS_COMPLETE");
                long until=System.nanoTime()+java.time.Duration.ofSeconds(90).toNanos();
                try {
                    while(!Files.exists(PRIVATE.resolve("copy.complete"))) {
                        require(System.nanoTime()<until);Thread.sleep(100);
                    }
                    require(Files.readString(PRIVATE.resolve("copy.complete")).equals("VERIFIED"));
                    try(var c=DriverManager.getConnection(environment.getProperty("spring.datasource.url"),environment.getProperty("spring.datasource.username"),environment.getProperty("spring.datasource.password"));
                        var s=c.createStatement();var r=s.executeQuery("SELECT v.version,v.config_json,v.config_sha256 FROM system_model_config_state s JOIN system_model_config_version v ON v.version=s.current_version WHERE s.id=1")) {
                        require(r.next()&&r.getLong(1)==10);
                        var stored=new SystemModelConfigCodec().decode(r.getString(2),r.getString(3));
                        require(Objects.equals(stored.environmentFingerprint(),fingerprint));
                    }
                    System.out.println("P21_CAPTURE_GATE_PASS");
                } catch(Exception ignored) { throw new IllegalStateException("P21_IMPORT_OR_CAPTURE_GATE"); }
            };
        }
    }

    public static void main(String[] args) {
        try {
            require(!Files.exists(PRIVATE.resolve("copy.complete")));
            var app=new SpringApplication(CourseLingoBackendApplication.class,MigrationImportBarrier.class);
            app.addListeners(new ConfigurationInput());app.run(args);
        } catch(Throwable failure) {
            var seen=new IdentityHashMap<Throwable,Boolean>();int n=0;
            for(Throwable t=failure;t!=null&&n<16&&seen.put(t,true)==null;t=t.getCause()) {
                String kind=t instanceof SQLException?"SQL":t instanceof org.flywaydb.core.api.FlywayException?"FLYWAY":"STARTUP";
                String row="P21_STARTUP_CAUSE index="+(n++)+" kind="+kind;
                if(t instanceof SQLException sql) {
                    String state=sql.getSQLState();if(state!=null&&state.matches("[A-Z0-9]{5}"))row+=" sqlState="+state;
                    row+=" vendorCode="+sql.getErrorCode();
                }
                System.out.println(row);
            }
            System.exit(45);
        }
    }
}
