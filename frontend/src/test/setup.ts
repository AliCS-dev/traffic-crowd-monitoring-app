import "@testing-library/jest-dom/vitest";
import { afterEach } from "vitest";
import { cleanup } from "@testing-library/react";

afterEach(() => {
  cleanup();
});

// JSDOM does not decode media. Load-event tests use the declared fixture size;
// mismatch tests override it, and Playwright checks real decoded images.
Object.defineProperties(HTMLImageElement.prototype, {
  naturalWidth: {
    configurable: true,
    get() {
      return this.width;
    },
  },
  naturalHeight: {
    configurable: true,
    get() {
      return this.height;
    },
  },
});

Object.defineProperty(window, "matchMedia", {
  writable: true,
  value: (query: string) => ({
    matches: false,
    media: query,
    onchange: null,
    addListener: () => undefined,
    removeListener: () => undefined,
    addEventListener: () => undefined,
    removeEventListener: () => undefined,
    dispatchEvent: () => false,
  }),
});
