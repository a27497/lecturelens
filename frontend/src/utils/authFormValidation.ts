const EMAIL_PATTERN = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;

export interface AuthFormFields {
  email: string;
  password: string;
}

function validateEmail(email: string): string {
  const trimmedEmail = email.trim();
  if (!trimmedEmail) {
    return "请输入邮箱";
  }
  if (!EMAIL_PATTERN.test(trimmedEmail)) {
    return "邮箱格式不正确，请检查是否包含 @ 和域名";
  }
  return "";
}

export function validateLoginForm(form: AuthFormFields): string {
  const emailError = validateEmail(form.email);
  if (emailError) {
    return emailError;
  }
  if (!form.password) {
    return "请输入密码";
  }
  return "";
}

export function validateRegisterForm(form: AuthFormFields): string {
  const emailError = validateEmail(form.email);
  if (emailError) {
    return emailError;
  }
  if (!form.password) {
    return "请输入密码";
  }
  if (form.password.length < 8) {
    return "密码至少需要 8 位";
  }
  if (!/[A-Za-z]/.test(form.password) || !/\d/.test(form.password)) {
    return "密码需要同时包含字母和数字";
  }
  return "";
}
