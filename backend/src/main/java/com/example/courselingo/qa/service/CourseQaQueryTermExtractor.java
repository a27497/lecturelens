package com.example.courselingo.qa.service;

import java.text.Normalizer;
import java.util.ArrayList;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Locale;
import java.util.Set;
import java.util.regex.Matcher;
import java.util.regex.Pattern;
import org.springframework.stereotype.Component;

@Component
public class CourseQaQueryTermExtractor {

    private static final List<String> CHINESE_BOUNDARY_TERMS = List.of(
        "这节课程", "这节课", "本节课程", "本节", "课程", "视频", "内容",
        "为什么", "如何", "什么", "请问", "这个", "哪里", "哪儿", "哪个", "老师",
        "讲解", "介绍", "讲了", "使用",
        "这节", "的是", "是在", "以及", "是否", "是", "的", "在", "中", "与", "和", "吗", "呢"
    );
    private static final Set<String> ENGLISH_BOUNDARY_TERMS = Set.of(
        "the", "and", "for", "with", "where", "what", "when", "why", "how",
        "course", "video", "lesson", "explain", "explains", "introduced", "introduce",
        "does", "do", "did", "this", "that", "is", "are", "was", "were", "in", "of", "to",
        "use", "used", "uses", "using", "work", "works", "working", "can", "could", "would",
        "should", "you", "please", "about", "tell", "me"
    );
    private static final Pattern TERM_RUN = Pattern.compile(
        "[\\p{IsHan}]+|[a-z0-9+#._-]+(?:\\s+[a-z0-9+#._-]+)*"
    );
    private static final Pattern LATIN_WORD = Pattern.compile("[a-z0-9+#._-]+");
    private static final Pattern HAS_LATIN_LETTER = Pattern.compile(".*[a-z].*");

    public List<String> extract(String question) {
        String normalized = normalize(question)
            .replaceAll("(?<=\\p{IsHan})(?=[a-z0-9])", " ")
            .replaceAll("(?<=[a-z0-9+#._-])(?=\\p{IsHan})", " ");
        for (String boundary : CHINESE_BOUNDARY_TERMS) {
            normalized = normalized.replace(boundary, " ");
        }
        LinkedHashSet<String> terms = new LinkedHashSet<>();
        Matcher matcher = TERM_RUN.matcher(normalized);
        while (matcher.find()) {
            String run = matcher.group().strip();
            if (run.isBlank()) {
                continue;
            }
            if (run.codePoints().allMatch(CourseQaQueryTermExtractor::isHan)) {
                if (run.codePointCount(0, run.length()) >= 2) {
                    terms.add(run);
                }
                continue;
            }
            List<String> words = new ArrayList<>();
            Matcher wordMatcher = LATIN_WORD.matcher(run);
            while (wordMatcher.find()) {
                String word = wordMatcher.group();
                if (!ENGLISH_BOUNDARY_TERMS.contains(word) && HAS_LATIN_LETTER.matcher(word).matches()) {
                    words.add(word);
                }
            }
            if (!words.isEmpty()) {
                terms.add(String.join(" ", words));
            }
        }
        return List.copyOf(terms);
    }

    private static String normalize(String value) {
        return value == null
            ? ""
            : Normalizer.normalize(value, Normalizer.Form.NFKC)
                .toLowerCase(Locale.ROOT)
                .replaceAll("\\s+", " ")
                .strip();
    }

    private static boolean isHan(int codePoint) {
        return Character.UnicodeScript.of(codePoint) == Character.UnicodeScript.HAN;
    }
}
