import { describe, expect, it } from "vitest";
import { loginCredentialPolicy } from "./loginCredentialPolicy";

describe("loginCredentialPolicy", () => {
  it("isolates real-AI credentials and blocks automatic demo autofill", () => {
    const policy = loginCredentialPolicy("real");

    expect(policy.formAutocomplete).toBe("off");
    expect(policy.emailAutocomplete).toBe("section-lecturelens-real username");
    expect(policy.passwordAutocomplete).toBe("section-lecturelens-real current-password");
    expect(policy.emailName).toBe("lecturelens-real-email");
    expect(policy.passwordName).toBe("lecturelens-real-password");
    expect(policy.preventInitialAutofill).toBe(true);
  });

  it("keeps demo and real password-manager sections distinct", () => {
    const demo = loginCredentialPolicy("demo");
    const real = loginCredentialPolicy("real");

    expect(demo.formAutocomplete).toBe("on");
    expect(demo.preventInitialAutofill).toBe(false);
    expect(demo.emailAutocomplete).not.toBe(real.emailAutocomplete);
    expect(demo.passwordAutocomplete).not.toBe(real.passwordAutocomplete);
  });
});
