# 来源、署名与参考字幕

评测限定非商业工程研究。MIT OpenCourseWare 是发布者，许可为 [CC BY-NC-SA 4.0](https://creativecommons.org/licenses/by-nc-sa/4.0/)，按 [MIT OCW 条款](https://ocw.mit.edu/pages/privacy-and-terms-of-use/) 保留署名、非商业及相同方式共享要求。MIT 未背书本项目。视频留在 Git 忽略的 `.data/`，只公开来源、哈希、参考字幕及评测衍生结果；不重新发布视频或第三方插图。

|课程/讲次|主要讲者|官方资源页|完整时长|
|---|---|---|---:|
|6.006 Fall 2011, lecture 1|Srini Devadas；Erik Demaine 在开场短暂出声|[Algorithmic Thinking, Peak Finding](https://ocw.mit.edu/courses/6-006-introduction-to-algorithms-fall-2011/resources/lecture-1-algorithmic-thinking-peak-finding/)|53.351 min|
|18.02 Fall 2007, lecture 1|Denis Auroux|[Dot Product](https://ocw.mit.edu/courses/18-02-multivariable-calculus-fall-2007/resources/lecture-1-dot-product/)|38.672 min|
|14.01SC Fall 2011, lecture 1|Jonathan Gruber|[Introduction to Microeconomics](https://ocw.mit.edu/courses/14-01sc-principles-of-microeconomics-fall-2011/resources/lecture-1-introduction-to-microeconomics/)|34.232 min|
|18.06 Spring 2010 发布版, lecture 1|Gilbert Strang|[Geometry of Linear Equations](https://ocw.mit.edu/courses/18-06-linear-algebra-spring-2010/resources/lecture-1-the-geometry-of-linear-equations/)|39.814 min|
|6.041 Fall 2010 发布版, lecture 1|John Tsitsiklis|[Probability Models and Axioms](https://ocw.mit.edu/courses/6-041-probabilistic-systems-analysis-and-applied-probability-fall-2010/resources/lecture-1-probability-models-and-axioms/)|51.177 min|

总时长精确值为 **13,034,758 ms / 3.620766111 h**，以 ffprobe 实测及 `assets.lock.json` 为准。以上涵盖不同讲者的英语发音，但没有独立人工口音标签或按口音推断总体准确率。视频归档 URL 中的 S05/F10/F11 是原文件命名，与页面发布学期均保留，不改称新拍摄。

五份英文参考字幕是 OCW 官方页面的 `<track kind="captions" srclang="en">` 文件。原字节保存在 `references/*.vtt.txt`（内容仍为 WebVTT，扩展名避免仓库全局字幕忽略规则），文件和视频 SHA-256 逐一记在 `assets.lock.json`。页面 HTML 快照保存在 `.data/baseline-asr-20261015/*.html`。

参考的人工制作依据：[MIT News 对 OCW/3Play 工作流程的报道](https://news.mit.edu/2015/3play-media-more-efficient-video-captioning-0408)描述了自动初稿、人工编辑及管理者终审。这里使用官方专业字幕，而非 YouTube 自动字幕或本轮模型自行生成的参考。**没有取得这五份字幕各自的编辑/终审日志，也没有本轮独立人类逐字复标**；因此不能把本轮参考称作独立盲审的人类金标准。字幕本身的编辑遗漏、口语省略及术语写法差异仍会影响 CER。

冻结元数据中 algorithms 的主要讲者初填为 Erik Demaine；字幕第 34 行明确自我介绍为 Srini Devadas，纠正依据单独保存在 `metadata-errata.json`。原冻结文件不改写；媒体、字幕及评分规则均未因模型评分而变更。

所有下载视频包含内嵌英文字幕。评测以 `ffmpeg -map 0:v:0 -map 0:a:0 -c copy -sn -dn` 仅移除字幕/附属轨，原音视频数据包 SHA-256 与评测输入一致。不切片、不转码、不去静音、不修改音频时间。参考文件不上传，避免现有 EMBEDDED_SUBTITLE_FIRST 路径直接复制参考造成数据泄漏。
