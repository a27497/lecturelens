// These are intentionally PUBLIC demo-account credentials, never provider secrets.
// Configure only in the isolated demo build; normal builds leave all three empty.
export const recruiterDemo = {
  taskId: import.meta.env.VITE_RECRUITER_DEMO_COURSE_ID || "",
  email: import.meta.env.VITE_RECRUITER_DEMO_EMAIL || "",
  password: import.meta.env.VITE_RECRUITER_DEMO_PASSWORD || "",
};
export const recruiterDemoEnabled = Boolean(recruiterDemo.taskId && recruiterDemo.email && recruiterDemo.password);
export const demoGoals = [
  { label: "1 · 解释概念与练习", goal: "解释字符串不可变与变量重新绑定的区别，并给我一道概念题和一道新字符串代码输出题。" },
  { label: "2 · 根据 Evidence 回答", goal: "根据课程证据，为什么不能用 s[0] = 'y' 修改字符串，却可以把 s 重新赋值为 'yello'？解释并给两道自测题。" },
  { label: "3 · 课程外问题", goal: "这段课程如何配置 Kubernetes 生产集群？请给出节点数量和部署步骤，并出两道题。" },
];
