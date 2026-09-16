import { describe, expect, it } from "vitest";
import { renderMarkdown } from "./markdown";

function preview(source: string) {
  const container = window.document.createElement("div");
  container.innerHTML = renderMarkdown(source);
  return container;
}

describe("assistant Markdown preview", () => {
  it("renders rule tables, emphasis and literal template variables", () => {
    const result = preview(
      [
        "你目前共有 **1 条**中转规则：",
        "",
        "## 夜莺监控告警",
        "",
        "| 项目 | 配置 |",
        "|---|---|",
        "| 来源模板 | `{{payload}}` |",
        "| 目标模板 | `[{{source_name}}] {{event}}`<br>`{{llm_output}}` |",
        "",
        "- 开启来源鉴权",
        "- 查询日志",
      ].join("\n"),
    );
    expect(result.querySelector("strong")?.textContent).toBe("1 条");
    expect(result.querySelector("h2")?.textContent).toBe("夜莺监控告警");
    expect(result.querySelectorAll("tbody tr")).toHaveLength(2);
    expect(result.querySelector("code")?.textContent).toBe("{{payload}}");
    expect(result.querySelector("td br")).not.toBeNull();
    expect(result.querySelectorAll("li")).toHaveLength(2);
  });

  it("preserves fenced code and does not interpret its HTML", () => {
    const result = preview("```html\n<script>alert(1)</script>\n```");
    expect(result.querySelector("script")).toBeNull();
    expect(result.querySelector("pre code")?.textContent).toContain(
      "<script>alert(1)</script>",
    );
  });

  it("removes active HTML, remote images and unsafe attributes", () => {
    const result = preview(
      '<script>alert(1)</script><img src="https://example.com/track" onerror="alert(1)"><iframe src="https://example.com"></iframe><p onclick="alert(1)" style="color:red">内容</p>',
    );
    expect(
      result.querySelector(
        "script, img, iframe, [onclick], [onerror], [style]",
      ),
    ).toBeNull();
    expect(result.textContent).toContain("内容");
  });

  it("removes unsafe link schemes but preserves normal links", () => {
    const result = preview(
      '<a href="javascript:alert(1)">危险</a>\n\n[文档](https://example.com/docs)',
    );
    expect(result.querySelector("a")?.hasAttribute("href")).toBe(false);
    expect(
      result.querySelector('a[href="https://example.com/docs"]'),
    ).not.toBeNull();
  });

  it("renders quotes, ordered lists, line breaks and empty replies", () => {
    const result = preview("> 提示\n\n1. 第一步\n2. 第二步\n\n第一行\n第二行");
    expect(result.querySelector("blockquote")).not.toBeNull();
    expect(result.querySelectorAll("ol li")).toHaveLength(2);
    expect(result.querySelector("p br")).not.toBeNull();
    expect(renderMarkdown("")).toBe("");
  });
});
