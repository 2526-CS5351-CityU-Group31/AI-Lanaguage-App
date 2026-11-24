/**
 * Ambient type declarations for jest-axe (test-only, no production authority).
 *
 * Implements: VS-16 accessibility verification.
 *
 * The installed jest-axe version ships no TypeScript types, so the subset used
 * by the frontend tests is declared here.
 */
declare module "jest-axe" {
  export interface AxeViolation {
    id: string;
    impact?: string | null;
    description: string;
    help: string;
  }

  export interface AxeResults {
    violations: AxeViolation[];
    passes: unknown[];
    incomplete: unknown[];
  }

  export function axe(
    html: Element | string,
    options?: Record<string, unknown>,
  ): Promise<AxeResults>;

  export const toHaveNoViolations: () => {
    pass: boolean;
    message: () => string;
  };
}
