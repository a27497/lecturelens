package com.example.courselingo.fusion;

import java.util.LinkedHashMap;
import java.util.List;
import java.util.Locale;
import java.util.Map;
import java.util.Set;
import java.util.regex.Matcher;
import java.util.regex.Pattern;

public class KeywordExtractor {

    private static final Pattern TOKEN = Pattern.compile("[\\p{IsHan}]{2,}|[A-Za-z][A-Za-z0-9_+.#-]{1,}");
    private static final Set<String> STOP_WORDS = Set.of(
        "the", "and", "for", "with", "this", "that", "from", "are", "was", "were", "you", "your",
        "have", "has", "will", "can", "into", "about", "here", "there", "本段", "主要", "讲解", "画面",
        "文字", "包括", "显示", "一个", "这个", "我们", "可以", "进行", "内容"
    );

    public List<String> extract(String text, int maxKeywords) {
        if (text == null || text.isBlank() || maxKeywords <= 0) {
            return List.of();
        }
        Map<String, String> ordered = new LinkedHashMap<>();
        Matcher matcher = TOKEN.matcher(text);
        while (matcher.find() && ordered.size() < maxKeywords) {
            String token = matcher.group().strip();
            String key = token.toLowerCase(Locale.ROOT);
            if (!STOP_WORDS.contains(key) && !STOP_WORDS.contains(token)) {
                ordered.putIfAbsent(key, token);
            }
        }
        return List.copyOf(ordered.values());
    }
}
