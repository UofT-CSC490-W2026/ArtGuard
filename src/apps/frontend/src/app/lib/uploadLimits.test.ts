import { describe, expect, it } from "vitest";
import {
  hasAllowedImageExtension,
  IMAGE_EXTENSIONS,
  MAX_UPLOAD_BYTES,
} from "./uploadLimits";

describe("hasAllowedImageExtension", () => {
  it("accepts allowed extensions case-insensitively", () => {
    expect(hasAllowedImageExtension("photo.JPG")).toBe(true);
    expect(hasAllowedImageExtension("x.PNG")).toBe(true);
    expect(hasAllowedImageExtension("scan.tiff")).toBe(true);
    expect(hasAllowedImageExtension("w.webp")).toBe(true);
  });

  it("rejects files without extension", () => {
    expect(hasAllowedImageExtension("noext")).toBe(false);
    expect(hasAllowedImageExtension("")).toBe(false);
  });

  it("rejects disallowed extensions", () => {
    expect(hasAllowedImageExtension("file.gif")).toBe(false);
    expect(hasAllowedImageExtension("doc.pdf")).toBe(false);
  });

  it("uses last dot for extension", () => {
    expect(hasAllowedImageExtension("archive.tar.jpg")).toBe(true);
  });
});

describe("constants", () => {
  it("IMAGE_EXTENSIONS matches backend-aligned set", () => {
    expect(IMAGE_EXTENSIONS.has(".jpeg")).toBe(true);
    expect(MAX_UPLOAD_BYTES).toBe(20 * 1024 * 1024);
  });
});
