package com.example.courselingo.ai.llm;

import com.fasterxml.jackson.databind.*;
import java.net.URI;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.util.*;
import java.util.function.Supplier;
import java.util.regex.Pattern;

/** Accounting failure stops the caller; upstream bodies and cause chains never become exceptions. */
public final class ObservedModelCall {
    private static final ObjectMapper JSON=new ObjectMapper();
    private static final Pattern FIELD=Pattern.compile("(?i)([\\\"']?(?:authorization|api[_-]?key|apikey|access[_-]?token|secret|password)[\\\"']?\\s*[:=]\\s*)(\\\"(?:\\\\.|[^\\\"])*\\\"|'[^']*'|[^\\s,;}]+)");
    private ObservedModelCall(){}
    public static OpenAiCompatibleClientResponse execute(ModelCallObserver observer,URI address,Map<String,String> headers,
            byte[] body,boolean jsonBody,Supplier<OpenAiCompatibleClientResponse> call) {
        var context=ModelCallScope.current();
        if(context==null || observer==ModelCallObserver.NOOP)return call.get();
        String id;
        try {id=observer.begin(context,new ModelCallObserver.RequestSummary(safeAddress(address),hash(body),body.length,summary(body,jsonBody)));}
        catch(RuntimeException ignored){throw TranslationFailure.of(TranslationFailure.Reason.ACCOUNTING_INCOMPLETE);}
        if(id==null)return call.get();
        ModelCallScope.recorded(id);
        var start=System.nanoTime();OpenAiCompatibleClientResponse response=null;String category=null;
        try {response=call.get();return response;}
        catch(RuntimeException failure){category=TranslationFailure.from(failure).reason().name();throw failure;}
        finally {
            JsonNode root=null;
            if(response!=null)try {root=JSON.readTree(response.body());}catch(Exception ignored){}
            Integer status=response==null?null:response.statusCode();
            if(response==null && category==null)category="UNKNOWN_OUTCOME";
            if(category==null && status!=null && (status<200 || status>=300))category=status==401||status==403?"AUTHENTICATION":status==429?"RATE_LIMITED":status==404?"MODEL_NOT_FOUND":status>=500?"UPSTREAM_5XX":"INVALID_REQUEST";
            if(category==null && root==null)category="FORMAT_INVALID";
            String finish=root==null?null:root.path("choices").path(0).path("finish_reason").asText(null);
            if("length".equals(finish))category="TRUNCATED";
            if(category==null && !"ASR_TRANSCRIPTION".equals(context.feature()) && root!=null) {
                var content=root.path("choices").path(0).path("message").path("content");
                if(content.isNull() || content.isTextual()&&content.asText().isBlank())category="EMPTY_OUTPUT";
                else if(!content.isTextual())category="FORMAT_INVALID";
                else if(jsonBody)try {
                    if("json_object".equals(JSON.readTree(body).path("response_format").path("type").asText())
                        && !JSON.readTree(content.asText()).isObject())category="FORMAT_INVALID";
                }catch(Exception ignored){category="FORMAT_INVALID";}
            }
            String excerpt=status!=null && status==400?redact(response.body(),headers):null;
            boolean truncated=excerpt!=null && excerpt.length()>4000;
            if(truncated)excerpt=excerpt.substring(0,4000);
            var completion=new ModelCallObserver.Completion(status,LlmUsage.parse(root),safeFinish(finish),category,
                Math.max(0,(System.nanoTime()-start)/1000000),excerpt,response==null?null:response.body().length(),truncated,
                fieldHash(root,"model"),fieldHash(root,"system_fingerprint"));
            try {observer.complete(id,completion);}catch(RuntimeException ignored){throw TranslationFailure.of(TranslationFailure.Reason.ACCOUNTING_INCOMPLETE);}
        }
    }
    private static String summary(byte[] body,boolean isJson) {
        var safe=new TreeMap<String,Object>();
        if(isJson)try {
            var root=JSON.readTree(body);
            for(String field:List.of("model","max_tokens","stream","temperature","response_format","thinking")) {
                var node=root.path(field);
                if(node.isNumber()||node.isBoolean())safe.put(field,node);
                else if(field.equals("response_format")||field.equals("thinking")) {
                    String type=node.path("type").asText("");if(Set.of("json_object","text","enabled","disabled").contains(type))safe.put(field,type);
                }
            }
            if(root.path("messages").isArray())safe.put("messageCount",root.path("messages").size());
        }catch(Exception ignored){safe.put("parse","UNAVAILABLE");}
        try{return JSON.writeValueAsString(safe);}catch(Exception ignored){return "{}";}
    }
    private static String safeAddress(URI address){return address.getScheme()+"://"+address.getHost()+(address.getPort()<0?"":":"+address.getPort())+(address.getRawPath()==null?"":address.getRawPath());}
    private static String hash(byte[] bytes){try{return HexFormat.of().formatHex(MessageDigest.getInstance("SHA-256").digest(bytes));}catch(Exception ignored){throw new IllegalStateException("Hash unavailable");}}
    private static String fieldHash(JsonNode root,String key){return root!=null && root.path(key).isTextual()?hash(root.path(key).asText().getBytes(StandardCharsets.UTF_8)):null;}
    private static String safeFinish(String f){return f!=null&&Set.of("stop","length","content_filter","tool_calls","insufficient_system_resource").contains(f)?f:null;}
    private static String redact(String body,Map<String,String> headers) {
        String value=body;
        for(var entry:headers.entrySet())if(entry.getKey().equalsIgnoreCase("Authorization")) {
            String key=entry.getValue().replaceFirst("(?i)^Bearer\\s+","");
            if(!key.isBlank()) {value=value.replace(key,"[redacted]");try {String encoded=JSON.writeValueAsString(key);value=value.replace(encoded.substring(1,encoded.length()-1),"[redacted]");}catch(Exception ignored){return "[redacted]";}}
        }
        value=FIELD.matcher(value).replaceAll("$1\"[redacted]\"");
        value=value.replaceAll("(?i)bearer\\s+[^\\s\\\"'\\\\,;]+","Bearer [redacted]");
        return value.replaceAll("(?i)\\bsk-[a-z0-9_-]+","[redacted]");
    }
}
