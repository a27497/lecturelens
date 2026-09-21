# L2.2 长任务：开发修复记录

**2026-09-19 当前验收状态：** 冻结BC在隔离qwen3-max生成／复核下完成L2.2既定Phase验收：20/20类型结构、16/16内容、4/4拒答；391项Python／独立PostgreSQL测试、20份产物重启与幂等恢复、浏览器、取消及删除检查通过。范围为两门已见课程、四段视频上的10道开发与10道新目标，AI来源核查，不代表未见媒体泛化。候选未发布，线上C及个人模型配置不变；L3未启动。 见 [最终报告](FINAL_BC.md)。

以下保留按日期与候选记录的历史过程；旧轮次失败不被覆盖。

**审阅更正：** 后续逐题引用核查发现，部分初步评分误用了其他字段的共享证据。AU、AZ、BA 的完整语义分别更正为 10/16、11/16、13/16；下文历史段落的原计数以 [更正记录](https://github.com/a27497/lecturelens/blob/study-agent-au-evidence-2026-09-20/eval/l22-completion/citation-review-errata.json) 和修正后的 JSON 报告为准。原始模型输出未变，原评分快照保留。BA 正式评测尚未开始，准备的保留题作废于后续新候选，见 [未运行记录](https://github.com/a27497/lecturelens/blob/study-agent-au-evidence-2026-09-20/eval/l22-completion/final-ba-not-run.json)。
2026-09-19启动时状态：**进行中，尚未通过；线上C与个人配置不变。** 完成条件见[验收计划](../../docs/L2_PHASE_COMPLETION.md)。带development命名的试跑均为已见开发材料；FINAL_AT/BB/BC分别记录冻结后新保留的正式配对成绩。

当前实现由模型提交 `answer_points`，Python 从同一组有序要点生成标准答案与评分依据，保留重复输出行。旧自由评分文本不能被静默转换后重新计为正确。新契约每字段只允许一个复核结论；逐题检查自己的引用，程序回填真实证据原文，保存私有纠正观察。该结构消除了两份文本独立生成的冲突，不能证明答案内容正确。

开发过程中发现并修复了三个协议问题：

- 仅凭“行内函数定义”自动判错会误拒绝合法单行 Python。现在保留范围观察，由课程复核判断；字面量换行错误仍直接反馈，代码从不执行。
- 按字符切分的证据引文可能失去句子上下文。新契约使用完整的有界证据段编号；仍拒绝未知编号、其他题的引用和无来源的解释纠正。
- 实际提供方反复输出多余的单引号转义或缺少最外层结束括号。兼容解析仅接受这两类有限形式，并在 `model_finished.protocol_repairs` 留痕；缺失字段、未闭合字符串/嵌套容器、截断响应仍失败，业务结构与课程复核继续执行。历史失败不会重计。

线上决策/复核仍为 qwen-plus / qwen3-max。用户已授权隔离评测采用 qwen3-max 生成；W-max 起隔离决策/复核均为 qwen3-max，配对旧基线也必须使用相同配置。6 次模型调用、8 次工具、64,000 预留、两份候选、900/300 输出上限与 90 秒 deadline 不变。原始响应仅由私有评测记录器按既有大小与时间边界捕获，密钥脱敏，不进入公开事件。

## 已观察结果

所有试验身份、调用数、逐条状态和耗时保存在[开发进度](https://github.com/a27497/lecturelens/blob/study-agent-au-evidence-2026-09-20/eval/l22-completion/development-progress.json)。N、O、P、Q 的课程内生成大量失败；N 的额外单题诊断也失败。R 的四道支持题仅一道完成。失败包括参数格式、复核结构、重复无进展和预算耗尽，均保留。

S 的四道支持题全部完成（11.83–14.88 秒），但 `bailian-03` 的第二题询问完整屏幕输出，参考答案仍遗漏函数内部打印，复核错误接受。**完成率不等于质量合格；S 不能凭本轮 4/4 完成率放行。** 其他产物仍需按逐字段标准复核；本段为 AI 开发诊断，不是盲评或人工金标准。

S 对应实现的 Python 全套 **219 项通过，无跳过**，使用独立真实 PostgreSQL。机制测试不能替代真实模型质量。另已准备隔离 MySQL/Agent PostgreSQL、Redis 数据库、MinIO bucket、MQ topic、Java/Python 端口，开始真实视频上传与 Evidence 链路开发验证；未切换线上服务。

完整保留任务、配对旧基线、20 题质量/延迟报告与浏览器/恢复验收尚未完成。L3 未开放。

## 完整入口开发回归与后续候选

S 隔离全链路已完成全部 10 道已见开发题：7/10 得到正确类型产物，课程内语义 2/8，拒答 2/2；含失败 P50 13.733 秒、P95 91.042 秒。两个请求耗尽 deadline，一个参数校验失败。成功练习中仍有 `world[1:]` 被写成 `lord`、二分排除区间漏掉中点和未约定的取整答案等缺陷。全部结果与 AI 来源复核见[开发报告](https://github.com/a27497/lecturelens/blob/study-agent-au-evidence-2026-09-20/eval/l22-completion/s-full-development-report.json)及[逐题判断](https://github.com/a27497/lecturelens/blob/study-agent-au-evidence-2026-09-20/eval/l22-completion/s-full-development-reviews.json)。不是 20 题 Phase 成绩，也没有消耗新的保留题。

随后增加独立求解：先隐藏草稿答案、评分文本与解释，使用各题引用求解，再交给复核器比较；问题文本或证据变化使缓存失效，题目不变的答案修订可复用求解。结果与拒绝记录一起持久化，崩溃恢复不重复已提交的求解。所有调用仍计入原 6 次/64,000/90 秒预算；题目变更后预算不足会停止，不扩大额度。相应 T 实现的全套 Python 224 项通过，无跳过。

T 四题全部完成但仍漏掉内部打印；U 三题完成、一题反复引用不匹配失败，而且出现语言和目标偏离。不能据此声称独立求解已解决质量问题。当前 V 还向决策模型提供剩余额度，并让结构校验失败走已有的一次有预算格式修复；正在以真实入口复跑已见开发题。线上 C 不受影响。

V 全链路开发回归已结束：9/10 完成，但仍接受错误的字符串切片结果和课程未讲授的细节，不能放行。新增加的 `check_python_example` 是模型选择的有界 AST 解释器，只实现明确列出的 Python 子集；禁止导入、I/O、循环、任意属性和递归调用，并限制节点、步数、数据深度与输出。其结果证明例题计算，不证明课程来源支持。观察和已接受草稿的私有复核依据均持久化，公开事件不暴露答案。

W 的固定证据评测与机制测试误用同一测试数据库，发生 DDL 死锁；首题失败记录和中断原因保留，未运行题不计成功。之后单独使用 `lecturelens_agent_pilot_test`，与 `lecturelens_agent_test` 和完整入口的 `lecturelens_agent_l22test` 分离。

W-max 六题完成五题，但 `bailian-03` 仍漏内部打印、使用错误语言，`bailian-04` 增加无来源的唯一值声明；首题因独立求解返回三条引用超过两条契约而失败。更换生成模型不足以通过质量门槛。随后 X 修复核算观察未传入独立求解的缺陷，观察变化也使求解缓存失效；并修复隔离评测登录刷新写错目录的问题。X 的全套 Python **272 项通过，无跳过，真实独立 PostgreSQL**；真实全链路十题开发回归仍在进行。上述机制结果不计为模型质量通过。

X 回归现已完成：结构与延迟 10/10，拒答 2/2，但完整语义仍只有 **2/8**。P50 13.959 秒，P95 20.265 秒；43 次真实调用。错误包含将 `world` 的切片结果算成 `word`、引入未讲授 API、语言不符和重复题型。见 [逐题来源复核](https://github.com/a27497/lecturelens/blob/study-agent-au-evidence-2026-09-20/eval/l22-completion/x-max-full-development-reviews.json)和[报告](https://github.com/a27497/lecturelens/blob/study-agent-au-evidence-2026-09-20/eval/l22-completion/x-max-full-development-report.json)；这是 AI 复核，不是盲评人工金标准。

Y、Z、AA 十题开发回归分别完成 7、5、6 题，失败均计入[开发进度](https://github.com/a27497/lecturelens/blob/study-agent-au-evidence-2026-09-20/eval/l22-completion/development-progress.json)。Z 的新工具存在程序引用别名未转换的缺陷，已修复；同轮一次课程检索 HTTP 失败发生于并发索引新课程期间，后续评测与新课程准备分时执行，不删除该失败。AA 暴露复核重复生成正确答案时超出字段长度的问题。

当前 AB 变更：新增模型可选的 `create_python_practice`，概念题仍由模型提供，输出题使用同一完整程序生成题面，受限解释器生成标准输出、答案和评分点；不接受错误/不支持/空白或过大输出。私有计算记录持久化，引用须属于当前课程和可见证据。每个草稿仍有一次课程证据复核；接受字段不必重复输出答案，拒绝字段必须有具体修正和自己的来源。双重独立求解默认停用，保留显式回放入口及其恢复测试；历史试验没有证明额外调用的质量收益。模型/工具/候选总额度及 deadline 不变。

代码题机制验证覆盖重复输出行、无答案注入入口、错误/不支持程序拒绝、外国课程引用拒绝、私有答案、提交后崩溃恢复，以及真实协议形状下 5 次调用内修订（测试提供方为确定性夹具，非模型质量）。最近 AB 全套首次运行 280 通过、2 个测试断言失败：一个仍预期双重复核，另一个无序读取到了新保留的接受记录；修正测试预期和拒绝记录选择后，两项重跑通过。前端学习助手 6 项通过。完整验收、新保留集和同配置基线仍待完成，线上不发布。


## AB–AE 全链路结果与当前 AF

四轮均使用同一组 10 道已见开发题与隔离 qwen3-max/qwen3-max，原预算不变。

| 候选 | 正确类型产物 | 完整语义（8 支持题） | 完整拒答 | 含失败 P50 / P95 秒 |
| --- | --- | --- | --- | --- |
| AB | 8/10 | 3/8 | 2/2 | 13.052 / 27.888 |
| AC | 10/10 | 尚未形成完整逐题报告 | 未计质量通过 | 未计质量通过 |
| AD | 9/10 | 5/8 | 2/2 | 13.217 / 28.514 |
| AE | 8/10 | 2/8 | 2/2 | 14.462 / 25.889 |

见 [AB 报告](https://github.com/a27497/lecturelens/blob/study-agent-au-evidence-2026-09-20/eval/l22-completion/ab-max-full-development-report.json)、[AD 报告](https://github.com/a27497/lecturelens/blob/study-agent-au-evidence-2026-09-20/eval/l22-completion/ad-max-full-development-report.json)、[AE 报告](https://github.com/a27497/lecturelens/blob/study-agent-au-evidence-2026-09-20/eval/l22-completion/ae-max-full-development-report.json)及各自逐题复核文件。均为 AI 来源复核，不是盲评人工金标准；不合并不同候选的正确产物。

AC 按实际发送的工具 schema 预留预算，并在复核输入中移除重复课程正文；AD 加入已选字幕的有界相邻引用，避免切片、拼接等证据在字幕边界断开。引用扩展只用当前已授权、已选中的相邻同类字幕，不跨来源、不递归；原始引用不一致检查仍针对扩展前参数。AD 四道字符串题通过，但区间题仍出现保留已排除端点和未约定取整。

AE 新增模型可选的实数区间核算工具，从同一组边界/反馈生成题面、答案和评分点，严格排除猜测值、不默认取整；可在解释中附不同的已解示例。297 项 Python/独立 PostgreSQL 测试通过、无跳过，前端类型检查通过。然而真实运行只完成 8/10：模型仍会选择自由文本工具并算错切片，区间工具的可选已解示例参数两次类型错误；另一次把严格比较及开区间记法误判为必须由课程另行讲授，造成无效拒绝后预算耗尽。有引用的拒绝意见仍可能不成立。

当前 AF 明确区间示例必须为结构化对象，加强计算工具选择指引，并区分“应用已教方法所需的基本运算/比较”和“新引入的课程事实/API/取整惯例”；没有放宽原验收门槛。该轮结果见下文。两段新算法课程已隔离导入，但尚未编写或消费新保留任务。最终冻结、20 题配对基线、质量及最终浏览器/恢复/删除验收均未完成。线上 C 与模型配置不变，L3 未开放。


## AF、AG 失败与 AH 修复

AF 为 8/10 正确类型、4/8 完整语义、2/2 拒答；AG 为 9/10、5/8、2/2。完整逐题报告：[AF](https://github.com/a27497/lecturelens/blob/study-agent-au-evidence-2026-09-20/eval/l22-completion/af-max-full-development-report.json)、[AG](https://github.com/a27497/lecturelens/blob/study-agent-au-evidence-2026-09-20/eval/l22-completion/ag-max-full-development-report.json)。没有将两版正确项拼成成功成绩。AG 的区间核算题减少了错误数学修正，但仍有引用不完整、重构未报告课堂数字及参数类型失败。

AH 修复已见的三个根因：

- 补读窗口中的已有 ID 刷新保留顺序；搜索结果尚不足 8 条时，最多通过两次权威 WINDOW 读取补齐已命中字幕之间不超过 60 秒的短缺口，只加入同类型、缺口内、原时间约束内的证据。读取锚点保存在工具结果中，课程授权、版本 fence 和 deadline 仍生效。
- 对同一题面和答案要点能被受限程序重新构造验证的应用题，复核契约只询问课程支持、目标/语言、题型区别和答案泄露；自由生成的概念题和解释仍检查事实。重新计算不匹配即不能获得该模式；不会因为引用了某个无关程序就跳过答案检查。计算正确不等于课程支持正确。
- 私有协议诊断确认 `worked_example` 是被二次 JSON 编码的对象字符串；仅对此声明的对象字段进行有记录的无损解码，再执行原 schema 和不同示例约束。无结构散文、额外答案字段等仍拒绝。两次额外诊断调用单列，其中首次调用后的原始响应保存因 bytes 序列化错误而失败，未计为成功，未隐藏该次调用。

当前 AH 冻结并继续 10 道已见开发回归。全套 **309 项 Python/独立 PostgreSQL 测试通过，无跳过**；包含错误计算观察/题面不能伪造验证、课程不支持仍拒绝、补读保留顺序、短缺口读取范围与留痕、嵌套 JSON 解码仍受合约约束。此前 AG 全套一项旧测试仍断言没有计算复核模式，修正预期后定向 15 项通过；AH 全套覆盖了最终状态。以上都是机制证据，不替代真实质量与全新保留集。清理脚本新增隔离端点/manifest 参数及跨端点拒绝检查，尚未删除最终评测所需课程。


AH 回归完成：8/10 正确类型，5/8 语义、2/2 拒答；[AH 报告](https://github.com/a27497/lecturelens/blob/study-agent-au-evidence-2026-09-20/eval/l22-completion/ah-max-full-development-report.json)。AI 为 8/10、6/8、2/2；[AI 报告](https://github.com/a27497/lecturelens/blob/study-agent-au-evidence-2026-09-20/eval/l22-completion/ai-max-full-development-report.json)。AI 的参数重试已能依明确的不同示例提示修正输入；仍有复核协议失败，以及虚构“学习者要求整数”的拒绝意见。当前 AJ 缩短复核系统指令，并要求 `goal_mismatch` 附目标原文中的精确片段，回填为私有拒绝依据；这只校验引文存在性，语义是否成立仍需真实评测。新增隔离原始请求/响应记录保存在私有 `.data/`，不含请求凭据、不进入公开事件，不改变模型预算或线上服务。AJ 开发回归进行中。

已新增独立的重启恢复/幂等重放/取消验收脚本，以及浏览器独立报告前缀。AH 的 8 份成功产物已在完整入口验证公开接口隐藏答案、私有答案读取和事件尾游标；跨隔离进程重启的比对另行记录，不能作为最终候选模型质量成绩。最终 20 题与新的保留任务仍未开始。


AJ 已完成：10/10 正确类型、5/8 完整语义、2/2 拒答；[AJ 报告](https://github.com/a27497/lecturelens/blob/study-agent-au-evidence-2026-09-20/eval/l22-completion/aj-max-full-development-report.json)。三份产物分别增加未教的垃圾回收、TypeError 或时间复杂度/原始范围信息，仍不能放行。AJ 全套 **313 项 Python/独立 PostgreSQL 测试通过，无跳过**；引用实际目标文字的要求已纳入测试。AH 的 8 份历史产物经过 AI→AJ 隔离进程更换后完整读取一致，重复 START 返回原 Run、模型调用数不变，答案仍需私有接口请求，事件尾游标为空；这是恢复机制诊断，不是当前最终质量验收。

当前 AK 只进一步明确生成与复核必须保持课程原有细节层级，使用已见的错误作为开发例子，区分泛称错误/命名异常、对象仍在内存/垃圾回收、一次减半计算/复杂度分类。未硬编码这些例题的答案，未放宽原语义门槛，开发回归进行中。新保留题尚未编写或消费，最终验收仍未开始。


AK 已结束：9/10 正确类型、6/8 完整语义、2/2 拒答；[AK 报告](https://github.com/a27497/lecturelens/blob/study-agent-au-evidence-2026-09-20/eval/l22-completion/ak-max-full-development-report.json)。仍把课堂尝试次数重构为未报告的目标值，且相同的例题/应用输入再次耗尽一次格式纠正。AL 将重复输入按工具明示规则生成相反反馈的应用变式，记录原请求与实际问题，已解例题仍按请求计算；不同题面、答案与评分点同源，所有历史失败不变。然而 AL 预检为 308 通过、4 个预算相关测试失败，**未进行真实模型调用**。说明累积提示/schema 长度挤占了修订空间；后继版本压缩决策上下文，保持 6/8/64,000/90 秒上限，不扩大额度。


压缩决策提示后，60 项修订/恢复/区间定向测试通过，AM 随后全套 **314 项 Python/独立 PostgreSQL 测试通过，无跳过**。AM 真实开发回归仍为 8/10 正确类型、6/8 语义、2/2 拒答；[AM 报告](https://github.com/a27497/lecturelens/blob/study-agent-au-evidence-2026-09-20/eval/l22-completion/am-max-full-development-report.json)。私有原始响应定位到两种问题：接受字段重复重写超过长度上限，以及将解释中已回答的原例题与允许变化的练习应用混淆。

当前 AN 对接受字段的冗长可选复述不再使整份草稿失败，也绝不以该复述替换原参考答案；拒绝修正仍限制 200 字符且须非空、有依据。复核进一步区分“解释原例题”和“练习同一方法的新条件”。45 项相关定向测试通过，AN 完整入口开发回归进行中。原质量门槛、全部失败与线上配置不变。


报告说明校正：部分先前复用的通过理由带入了上一轮的具体字符串或区间值，现改为与实际判定相符的方法/来源说明；所有原始试验、逐题通过与失败标签、调用数和汇总指标均未改变。不能用报告中的旧示例文字替代原始产物。


AN 全套 315 项机制测试通过；真实回归为 9/10 正确类型、5/8 完整语义、2/2 拒答，[AN 报告](https://github.com/a27497/lecturelens/blob/study-agent-au-evidence-2026-09-20/eval/l22-completion/an-max-full-development-report.json)。两份草稿未形成实际应用题，另有一次解释拒绝没有指出被拒的解释文本而触发合约失败。AO 将通用出题 schema 显式分为 `concept` 与 `application`，后者要求新的具体情境/条件或错误纠正；存储仍使用原先的两题顺序与同源答案。旧派生评分契约只为回放兼容，混合两种形状或注入自由评分条件仍拒绝。全套 **316 项 Python/独立 PostgreSQL 测试通过，无跳过**。AO 完整入口开发回归正在进行，尚未开始保留集或最终比较。


AO 完成：10/10 正确类型、6/8 完整语义、2/2 拒答；[AO 报告](https://github.com/a27497/lecturelens/blob/study-agent-au-evidence-2026-09-20/eval/l22-completion/ao-max-full-development-report.json)。自由生成的解释仍混淆课堂次数和目标值，以及未声明整数域的区间边界。AP 在首次搜索 schema 中要求模型选择练习方式，后续只提供对应生成工具，模型可在证据改变判断时重新检索改选。该选择保存在 Python 工具观察中，不传给 Java Evidence。旧回放允许省略选择。区间解释保持方法层面，数字示例由结构化工具计算。AP 全套 **318 项 Python/独立 PostgreSQL 测试通过，无跳过**，十题开发回归开始；线上未变，尚未消费新保留题。


AP 完成：10/10 正确类型、6/8 完整语义、2/2 拒答；[AP 报告](https://github.com/a27497/lecturelens/blob/study-agent-au-evidence-2026-09-20/eval/l22-completion/ap-max-full-development-report.json)。区间应用核算正确，但解释增加未报告目标值，字符串说明增加未命名的异常类型，复核均直接接受。AQ 在复核结论前增加短事实对照，作为私有观察保存，不替代带原文依据的拒绝。初次机制预检 315 通过、4 个修订预算测试失败；随后的重复测试因编辑路径错误未应用压缩而中止，记录保留。已压缩重复决策指令，在原预算下重新检查。尚未消费新保留集或变更线上。


AQ 压缩后全套 **319 项 Python/独立 PostgreSQL 测试通过，无跳过**；Ruff 和 diff 空白检查通过，预算未增加。候选已冻结并开始十道已见开发题的完整入口回归。事实对照仅为模型私有观察，不视作已证明支持的课程事实，也不能覆盖已有拒绝。


AQ 结束：6/10 正确类型、2/8 完整语义、2/2 拒答；[AQ 报告](https://github.com/a27497/lecturelens/blob/study-agent-au-evidence-2026-09-20/eval/l22-completion/aq-max-full-development-report.json)。字符串第一题观察到有据拒绝后成功修订；但另有未教 upper 方法、课堂数字误推，四次协议失败未发布，不能算作成功。AR 将短事实对照的存储上限设为800字符（仍提示简短、总输出300 tokens不变），避免无关的可选审计文字长度使有效结论失败。复核合约失败可在同一调用位置纠正一次格式，每次尝试计入持久模型/预留/deadline预算，候选和证据不变；不会将语义拒绝作为协议错误重试。重启可能重新进入未提交的工具，仍受原持久总预算限制。Python 练习方式改为更明确的 `python_strings_or_code`，保留旧名回放。

AR 完整测试318通过、1项旧事件数量断言失败；更新该断言后，连同两项新增预算内复核重试/失败停止用例，定向3项全部通过（覆盖321项不同机制测试，无跳过）。十题真实开发回归开始，新保留集仍未开始。


AR 结束：9/10 正确类型、5/8 完整语义、2/2 拒答；[AR 报告](https://github.com/a27497/lecturelens/blob/study-agent-au-evidence-2026-09-20/eval/l22-completion/ar-max-full-development-report.json)。首次字符串题虽有正确代码结果，其 own citations 仍止于字幕半句，不能算通过；另有课堂次数推断及复核误拒导致预算耗尽。AS 在原两次权威窗口/八条证据限制内，补齐末尾未完字幕，按时间顺序只接续相邻同类型证据，到句末停止；逐题引用也沿已授权、已选中的同类字幕补齐未完句。没有合并或杜撰 Evidence ID。全套322项通过，另新增真实 PostgreSQL 续句/停句/模态隔离/留痕测试1项通过；无跳过。AS 已冻结并开始完整入口十题开发回归。新保留题仍未编写或消费。


AS 完成：8/10 正确类型、4/8 完整语义、2/2 拒答；[AS 报告](https://github.com/a27497/lecturelens/blob/study-agent-au-evidence-2026-09-20/eval/l22-completion/as-max-full-development-report.json)。报告课堂次数的修订有效，但仍有垃圾回收、连续范围必要性等无据细节，以及协议/预算失败。AT 修复了 WINDOW 一次只给相邻一条字幕、预先计算缺口无法补齐连续两条的行为：两次额度内每次重新计算剩余缺口。复核只发送其需要的解释/目标锚点，题目引用仍从原字段程序回填，避免重复题面/答案挤占预算和误选解释锚点；解释要求只保留两句必要内容。全套 **323 项 Python/独立 PostgreSQL 测试通过，无跳过**。AT 已冻结，开发回归开始。未编写保留题，线上及验收门槛不变。


AT 开发回归完成：**10/10 正确类型、8/8 完整语义、2/2 正确拒答**；[开发报告](https://github.com/a27497/lecturelens/blob/study-agent-au-evidence-2026-09-20/eval/l22-completion/at-max-full-development-report.json)。随后冻结 [源码/模型/预算身份](https://github.com/a27497/lecturelens/blob/study-agent-au-evidence-2026-09-20/eval/l22-completion/final-at-freeze.json)，再编写 [十道新保留任务及十道原开发任务](https://github.com/a27497/lecturelens/blob/study-agent-au-evidence-2026-09-20/eval/l22-completion/final-at-cases.json)。正式二十题与开发回归是不同 cohort，不复用或拼接产物。先运行旧 C 的隔离 max/max 基线，再运行同配置 AT；所有失败与延迟均入账。最终 Phase 尚未通过，线上仍不变。


AT正式配对验收完成但失败：[正式报告](FINAL_AT.md)。AT为16/20正确类型、9/16完整语义、4/4拒答；旧C为19/20、3/16、4/4，两版分别72和62次真实模型调用。开发与保留部分分别报告，所有失败计入分母。真实浏览器、重启恢复、幂等重放和取消验证通过，不替代质量门槛。新十题现已消费，后继候选需新保留题。当前继续修复，未部署，未进入L3。


AU 在AT失败后继续开发：修复目标拒绝同时携带两条课程证据时，答案观察与质量依据两层容量冲突；本地重构验证的应用答案不再暴露给课程语义复核器重新计算，原题面/方法及本地证明仍保留。截断决策纳入原一次持久格式纠正额度。新增受限选择排序步骤工具，模型选择课程方法和数据，程序逐轮生成正确状态与同源私有答案，仍复核方法是否有课程支持。当前共八个工具，线上C仍只有四个。

初次协议预检缺少json导入，中止保留；补充后325通过、2失败，定位到答案观察的另一处容量限制及空请求测试兼容，修复后相关68项通过。整合排序步骤后全套 **343项 Python/独立PostgreSQL测试通过，无跳过**；前端类型检查和6项交互测试通过。AU已冻结，以[全部二十道已消费任务](https://github.com/a27497/lecturelens/blob/study-agent-au-evidence-2026-09-20/eval/l22-completion/au-development-cases.json)进行开发回归，明确全部标为dev；这不是新保留集验收。

### AU 二十题已见开发回归（2026-09-19）

71 次真实模型调用；类型/结构 18/20，课程内完整语义 11/16，课程外停止 4/4。全部结果 P50 11.598 秒、P95 23.452 秒。343 项 Python 测试（独立真实 PostgreSQL，无跳过）通过，前端类型检查和 6 项面板测试通过。它们证明机制，不替代质量。

选择排序步骤现由受限计算工具生成，上一轮数组状态错误得到修复，但自由解释仍会说错后缀增长方向；另有遗漏课堂比较次数、以渐近成本断定具体查询次数一定更快、正确数值示例误拒绝、复核协议/预算失败。来源审阅由 AI 完成，不是盲评人工金标。AU 未达标，20 题全部已见，不作为新保留集。

[逐题审阅](https://github.com/a27497/lecturelens/blob/study-agent-au-evidence-2026-09-20/eval/l22-completion/au-max-full-development-reviews.json)、[完整报告](https://github.com/a27497/lecturelens/blob/study-agent-au-evidence-2026-09-20/eval/l22-completion/au-max-full-development-report.json)。线上 C 与原模型配置不变。下一候选 AV 将精确重建并单独标记解释中的程序核算示例；只有完全匹配的计算后缀可从复核请求中隐藏，自由解释和错误/伪造后缀仍接受全文审阅。

### AV 二十题已见开发回归与 AW 修复

AV 为 67 次真实调用，类型结构 18/20、完整语义 12/16、拒答 4/4；全部结果 P50 10.696 秒、P95 21.494 秒，仍未过门槛。课堂6次与76次比较恢复，计算示例后缀可独立重建；自由文字重复数值仍会被误拒绝，自动反转反馈又触发目标不符，此外复杂度被错误换算成具体操作次数。[审阅](https://github.com/a27497/lecturelens/blob/study-agent-au-evidence-2026-09-20/eval/l22-completion/av-max-full-development-reviews.json)、[报告](https://github.com/a27497/lecturelens/blob/study-agent-au-evidence-2026-09-20/eval/l22-completion/av-max-full-development-report.json)。

AW 取消区间工具自动反转反馈，精确保留模型请求的题目条件；概念题要求解释原因，避免与计算题重复，并明确渐近复杂度不能推出具体操作计数或固定规模盈亏点。首次测试 345 通过、2 个旧行为断言失败，更新为新合同后完整 347 项通过，无跳过；两次记录均保留。AW 冻结源码 `4321df74184d895eda9c0a5ad77605a7096a7f28b513fef5ec04b718811eb01a` 后开始同20题开发回归。首次启动评测时服务尚未就绪，CREATE_SESSION 返回503，未创建 Run/调用模型；服务就绪后沿用幂等标签继续，原错误日志保留。线上 C 不变，尚无新保留集验收。

### AW 开发回归与 AX 结构调整

AW 67 次真实调用，类型结构18/20，完整语义9/16，课程外停止4/4；全部结果P50 10.924秒、P95 24.685秒。条件自动反转已移除，但仍有自由解释误拒绝、课堂结果遗漏、未讲授的异常名称、具体复杂度误用和排序区域方向错误；另有一次MODEL_UNAVAILABLE，保留失败而不补跑覆盖。[逐题审阅](https://github.com/a27497/lecturelens/blob/study-agent-au-evidence-2026-09-20/eval/l22-completion/aw-max-full-development-reviews.json)、[报告](https://github.com/a27497/lecturelens/blob/study-agent-au-evidence-2026-09-20/eval/l22-completion/aw-max-full-development-report.json)。

AX 区间工具增加模型选择的 `focus`：减半方法或与逐项猜测比较。方法说明由该受限工具生成；比较引用模型选中的 `reported_evidence_ids` 对应权威原文，数值示例由同一计算器生成，不再邀请模型重复编写数值解释。没有内置课堂6/76或目标值；独立测试使用7/83证明引用来自实际观察。原自由解释合同仅保留旧请求兼容，当前工具schema不提供。其他主题仍有自由解释，方法是否被课程教授仍由模型复核，工具模板不证明课程支持。

首次AX测试343通过、7失败：新增schema文本挤占原预算，旧测试包装器未适配证据参数，新测试引用ID错误，以及可选空解释的再次验证冲突。压缩重复工具描述、修复默认值和测试后，全量350通过，无跳过；保留两次日志。冻结源码 `31e2bbd64f9a745a2a1ebccadbce1d08231f3450c88ae536f9ac20a33e37132b`，仍使用原6次模型/8次工具/64000保留Token/2候选/90秒预算，开始20项已见回归。

### AX 开发回归与 AY 引用修复

AX 65次真实调用：19/20类型结构、14/16完整语义、4/4拒答；全部结果P50 11.699秒、P95 20.24秒。指定区间任务观察到拒绝后的有效修订。未通过项为比较题的新字段短引用转换缺失，以及搜索应用把渐近复杂度错误换算成10010步。[审阅](https://github.com/a27497/lecturelens/blob/study-agent-au-evidence-2026-09-20/eval/l22-completion/ax-max-full-development-reviews.json)、[报告](https://github.com/a27497/lecturelens/blob/study-agent-au-evidence-2026-09-20/eval/l22-completion/ax-max-full-development-report.json)。该组均为已见开发题，不是新保留集。

AY 仅补齐 `reported_evidence_ids` 的短引用/正式ID转换，并加强真实PG测试：权威来源使用 `canonical-e1`，模型只能看到并提交 `e1`，验证正确保存及外部引用拒绝。350项完整测试通过，无跳过。源码 `cb8ef288b0d60c2a168f58312a32d58635bb6ca92e8b5f9f326ceb18b2d8bd57` 冻结后继续同20题回归；不覆盖AX失败。线上C不变，Phase尚未完成。

AY 完整回归：20/20类型结构、14/16完整语义、4/4拒答，仍未过门槛。比较结果引用与区间示例已正确保存；两项质量失败都在查询成本应用（固定查询次数盈亏点、把渐近界当具体代价）。[逐题审阅](https://github.com/a27497/lecturelens/blob/study-agent-au-evidence-2026-09-20/eval/l22-completion/ay-max-full-development-reviews.json)、[报告](https://github.com/a27497/lecturelens/blob/study-agent-au-evidence-2026-09-20/eval/l22-completion/ay-max-full-development-report.json)。下一候选 AZ 将在现有通用出题工具中增加受限成本比较模式，仍需课程支持复核。

### AZ 受限查询成本应用

模型首次检索可选 `search_cost`，随后现有 `create_practice_set` 提供单次或反复查询模式。此模式专用于课程教授的 O(n log n) 排序、O(log n) 二分查询和 O(n) 扫描；其他成本模型使用通用模式。模型选择课程引用、解释和概念题，程序生成纠错应用题及同源答案：检查遗漏排序准备阶段，或纠正不变名单每次查询前重复排序的计划。没有固定n或查询次数输入，不把渐近界换成精确步数或固定规模盈亏点。应用仍由普通课程语义复核检查，没有套用“计算已验证”豁免。

真实PG覆盖短引用到正式ID、外部引用拒绝和私有答案；通用旧合同仍可回放。全量358项通过，无跳过；最终补充工具适用范围文字后，成本/供应商59项相关测试再次通过。工具仍为8个，所有原运行预算不变。新冻结候选开始同20题已见回归，尚不作为正式新保留集验收。

### AZ 完整回归与 BA 概念题边界

AZ 66次真实调用：19/20类型结构、13/16完整语义、4/4拒答；全部结果P50 10.304秒、P95 17.19秒。查询成本组4题均通过；区间自由概念答案仍引入目标值/猜测次数关系及51–100中点75的错误，排序纠错目标又触发无有效纠正意见的复核协议失败。[逐题审阅](https://github.com/a27497/lecturelens/blob/study-agent-au-evidence-2026-09-20/eval/l22-completion/az-max-full-development-reviews.json)、[报告](https://github.com/a27497/lecturelens/blob/study-agent-au-evidence-2026-09-20/eval/l22-completion/az-max-full-development-report.json)。

BA 将区间概念收敛为模型选择的 `midpoint_reason`、`feedback_role`、`compare_methods` 三类，并由程序生成概念问题及同源答案。新工具schema不提供自由概念答案；旧输入仅为回放兼容。模型仍选择目标、课程引用和数值示例，全部概念事实仍经过课程支持复核。这是受限的练习能力，不是通用自动出题。复核说明明确区分学习者引用的错误说法与真正要求。367项Python测试通过（真实独立PG，无跳过），源码 `212c1b7fea97bf82ff814a4d141ea9fd637353a21084a496cc0b0e4eef5ba521` 冻结，继续20项已见回归。没有改变模型/工具调用、Token或时限预算。

### BB 生成成本主张的逐题引用

成本模板会增加排序、二分与扫描的代价，因此 BB 将模型选中的共享方法 `evidence_ids` 与 `application_evidence_ids` 一并作为该应用题自身的引用，不借用概念题独有来源，也不将整个产物的引用当作自动支持证明。真实PG测试刻意拉开两条证据的时间，排除相邻引用补全掩盖问题，验证短ID转换、两类来源加入、越权拒绝及私有答案。368项完整测试通过，无跳过。冻结源码 `2f917dfb336a7a9fb5661bec8902a314bb26207be6b905f67698c525464f5863` 后继续20题已见回归；报分前须按每个字段自己的引用核查。BA预先编写但未调用模型的10道题不作为BB的新保留集。

## BB 正式验收进行中

BB 已见开发为20/20结构、16/16语义、4/4拒答，63次真实调用，P50/P95为10.858/13.396秒；368项机制测试通过、无跳过。该开发集不算新保留验收。新20题配对队列（10已见、10冻结后新题）已固定，见 [冻结身份](https://github.com/a27497/lecturelens/blob/study-agent-au-evidence-2026-09-20/eval/l22-completion/final-bb-freeze.json)和[任务集](https://github.com/a27497/lecturelens/blob/study-agent-au-evidence-2026-09-20/eval/l22-completion/final-bb-cases.json)。逐题来源标准沿用引用审阅更正；BA预备题不复用。正式结果及恢复/删除验收尚未完成，线上不变。

BB正式配对已完成并失败：19/20结构、13/16语义、4/4拒答；旧C为19/20、4/16、4/4，共131次真实模型调用。开发16/16未复现。详见 [BB正式报告](FINAL_BB.md)。保留任务已消费，BC继续修复，Phase未完成。

BC通过391项机制测试，已见开发为19/20结构、15/16语义、4/4拒答（63次调用）。唯一失败为误读排序边界后修订触及原预留预算；没有增加预算或替换失败。BC源码已冻结，新保留任务已编写，正式C/BC配对进行中，Phase尚未完成。

## 最终完成

BC正式20题达到20/20类型、16/16语义、4/4拒答；恢复、浏览器、取消和删除均完成。全部失败保留，完整历史已私有备份，候选未部署。详见 [最终报告](FINAL_BC.md)和[验收摘要](https://github.com/a27497/lecturelens/blob/study-agent-au-evidence-2026-09-20/eval/l22-completion/verification.json)。
