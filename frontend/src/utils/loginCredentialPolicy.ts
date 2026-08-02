export type LoginCredentialMode = "demo" | "real";

export type LoginCredentialPolicy = {
  formAutocomplete: "on" | "off";
  emailAutocomplete: string;
  emailName: string;
  passwordAutocomplete: string;
  passwordName: string;
  preventInitialAutofill: boolean;
};

export function loginCredentialPolicy(mode: LoginCredentialMode): LoginCredentialPolicy {
  const section = mode === "demo" ? "section-lecturelens-demo" : "section-lecturelens-real";
  return {
    formAutocomplete: mode === "demo" ? "on" : "off",
    emailAutocomplete: `${section} username`,
    emailName: `lecturelens-${mode}-email`,
    passwordAutocomplete: `${section} current-password`,
    passwordName: `lecturelens-${mode}-password`,
    preventInitialAutofill: mode === "real",
  };
}
