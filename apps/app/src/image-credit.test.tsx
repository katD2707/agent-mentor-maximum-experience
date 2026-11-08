import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import i18n from "./i18n";
import { StaticBlock } from "./screens/courses/blocks";
import type { ImageBlock } from "./api";

const ref = { path: "images/a.webp", sha256: "x", bytes: 1, mime: "image/webp" } as ImageBlock["image"];
const ctx = { lang: "vi" as const, url: () => "blob:x" };

describe("image credit", () => {
  const block: ImageBlock = {
    id: "b1", kind: "image", image: ref, alt: "Đường sức",
    attribution: { provider: "Wikimedia Commons", title: "Field lines", author: "A. Author", license: "CC BY-SA 4.0",
      license_url: "https://creativecommons.org/licenses/by-sa/4.0/", source_url: "https://commons.wikimedia.org/wiki/File:x.png" },
  };

  it("shows a quiet credit line in vi and en, with links", async () => {
    await i18n.changeLanguage("vi");
    const { unmount } = render(<StaticBlock b={block} ctx={ctx} />);
    expect(screen.getByText("Ảnh:")).toBeTruthy();
    expect(screen.getByRole("link", { name: /Field lines, A\. Author, Wikimedia Commons/ }).getAttribute("href")).toContain("commons.wikimedia.org");
    expect(screen.getByRole("link", { name: "CC BY-SA 4.0" })).toBeTruthy();
    unmount();
    await i18n.changeLanguage("en");
    render(<StaticBlock b={block} ctx={ctx} />);
    expect(screen.getByText("Image:")).toBeTruthy();
    await i18n.changeLanguage("vi");
  });

  it("shows nothing for a picture we drew, and drops non-http links", () => {
    const { container, unmount } = render(<StaticBlock b={{ ...block, attribution: null }} ctx={ctx} />);
    expect(container.querySelector(".img-credit")).toBeNull();
    unmount();
    render(<StaticBlock b={{ ...block, attribution: { title: "t", source_url: "javascript:alert(1)" } }} ctx={ctx} />);
    expect(screen.queryByRole("link")).toBeNull();
  });
});
