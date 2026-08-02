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

    private static final int MAX_QUERY_TERMS = 32;

    private static final List<String> CHINESE_BOUNDARY_TERMS = List.of(
        "这节课程", "这节课", "本节课程", "本节", "课程", "视频", "内容",
        "为什么", "如何", "什么", "请问", "这个", "哪里", "哪儿", "哪个", "老师",
        "讲解", "介绍", "讲了", "提到", "提及", "使用", "主要", "概述", "总结", "附近", "左右", "前后", "分钟",
        "请指出", "指出", "相关", "时间段", "一个", "请", "被",
        "这节", "的是", "是在", "以及", "是否", "是", "的", "在", "中", "与", "和", "吗", "呢"
    );
    private static final Set<String> ENGLISH_BOUNDARY_TERMS = Set.of(
        "the", "and", "for", "with", "where", "what", "when", "why", "how",
        "course", "video", "lesson", "explain", "explains", "introduced", "introduce",
        "does", "do", "did", "this", "that", "is", "are", "was", "were", "in", "of", "to",
        "use", "used", "uses", "using", "work", "works", "working", "can", "could", "would",
        "should", "you", "please", "about", "tell", "me", "who", "which",
        "has", "have", "had", "his", "her", "their", "from", "according",
        "say", "says", "said", "mention", "mentions", "answer",
        "at", "ask", "asks", "asked", "us", "second", "seconds", "sec", "secs",
        "minute", "minutes", "min", "mins", "near", "around"
    );
    private static final Pattern TERM_RUN = Pattern.compile(
        "[\\p{IsHan}]+|[a-z0-9+#._-]+(?:\\s+[a-z0-9+#._-]+)*"
    );
    private static final Pattern LATIN_WORD = Pattern.compile("[a-z0-9+#._-]+");
    private static final Pattern HAS_LATIN_LETTER = Pattern.compile(".*[a-z].*");
    private static final Pattern DASH_SEPARATOR = Pattern.compile("[\\p{Pd}\\u2212]+");

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
                addChineseTerms(terms, run);
                continue;
            }
            List<String> words = new ArrayList<>();
            boolean naturalLanguageQuestion = false;
            Matcher wordMatcher = LATIN_WORD.matcher(run);
            while (wordMatcher.find()) {
                String word = wordMatcher.group();
                if (ENGLISH_BOUNDARY_TERMS.contains(word)) {
                    naturalLanguageQuestion = true;
                } else if (word.length() >= 2 && HAS_LATIN_LETTER.matcher(word).matches()) {
                    words.add(word);
                }
            }
            if (!words.isEmpty()) {
                terms.add(String.join(" ", words));
                if (naturalLanguageQuestion && words.size() >= 2) {
                    words.forEach(word -> addBounded(terms, word));
                }
            }
            if (terms.size() >= MAX_QUERY_TERMS) {
                break;
            }
        }
        return List.copyOf(terms);
    }

    private static void addChineseTerms(LinkedHashSet<String> terms, String run) {
        int[] codePoints = run.codePoints().toArray();
        if (codePoints.length < 2) {
            return;
        }
        addBounded(terms, run);
        if (codePoints.length <= 6) {
            return;
        }
        for (int size = 4; size >= 2 && terms.size() < MAX_QUERY_TERMS; size--) {
            for (int start = 0; start + size <= codePoints.length && terms.size() < MAX_QUERY_TERMS; start++) {
                addBounded(terms, new String(codePoints, start, size));
            }
        }
    }

    private static void addBounded(LinkedHashSet<String> terms, String term) {
        if (terms.size() < MAX_QUERY_TERMS && term != null && !term.isBlank()) {
            terms.add(term);
        }
    }

    private static String normalize(String value) {
        if (value == null) return "";
        String normalized = Normalizer.normalize(value, Normalizer.Form.NFKC).toLowerCase(Locale.ROOT);
        return DASH_SEPARATOR.matcher(normalized).replaceAll("-").replaceAll("\\s+", " ").strip();
    }

    private static boolean isHan(int codePoint) {
        return Character.UnicodeScript.of(codePoint) == Character.UnicodeScript.HAN;
    }
}
