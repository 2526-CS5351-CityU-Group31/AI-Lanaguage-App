/**
 * Vitest global test setup.
 *
 * Element: frontend test harness (test-only, no production authority)
 * Implements: V1-V4 verification constraints, VS-16 accessibility
 *
 * Registers jest-dom matchers and the jest-axe `toHaveNoViolations` matcher,
 * with a single Vitest type augmentation matching the core Assertion shape.
 * MSW server lifecycle is managed per test file.
 */
import * as matchers from "@testing-library/jest-dom/matchers";
import type { TestingLibraryMatchers } from "@testing-library/jest-dom/matchers";
import { cleanup } from "@testing-library/react";
import { expect, afterEach } from "vitest";
import { toHaveNoViolations } from "jest-axe";

expect.extend(matchers as unknown as Parameters<typeof expect.extend>[0]);
expect.extend(toHaveNoViolations as unknown as Parameters<typeof expect.extend>[0]);

declare module "vitest" {
  interface Assertion<R extends void | Promise<void> = void, T = unknown>
    extends TestingLibraryMatchers<unknown, R> {
    toHaveNoViolations(): R;
  }
  interface AsymmetricMatchersContaining {
    toHaveNoViolations(): void;
  }
}

afterEach(() => {
  cleanup();
  document.body.innerHTML = "";
});
