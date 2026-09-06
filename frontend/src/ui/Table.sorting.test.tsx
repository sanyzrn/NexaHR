import { describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { Table } from "./Table";

const headers = ["نام", "واحد", ""];
const rows = [["آرش", "فروش", "…"]];

describe("Table sorting", () => {
  it("بی `onSort` هیچ سرستونی دکمه نمی‌شود", () => {
    render(<Table headers={headers} rows={rows} />);
    expect(screen.queryByRole("button")).not.toBeInTheDocument();
  });

  it("فقط ستون‌های اعلام‌شده دکمه می‌گیرند", () => {
    render(<Table headers={headers} rows={rows} onSort={vi.fn()} sortableColumns={[0, 1]} />);
    expect(screen.getAllByRole("button")).toHaveLength(2);
  });

  it("کلیک، شمارهٔ ستون را می‌دهد", async () => {
    const onSort = vi.fn();
    render(<Table headers={headers} rows={rows} onSort={onSort} sortableColumns={[0, 1]} />);
    await userEvent.click(screen.getByRole("button", { name: /واحد/ }));
    expect(onSort).toHaveBeenCalledWith(1);
  });

  it("`aria-sort` وضعیت را به صفحه‌خوان می‌گوید", () => {
    render(
      <Table
        headers={headers}
        rows={rows}
        onSort={vi.fn()}
        sortableColumns={[0, 1]}
        sort={{ column: 1, direction: "desc" }}
      />
    );
    const cells = screen.getAllByRole("columnheader");
    expect(cells[0]).toHaveAttribute("aria-sort", "none");
    expect(cells[1]).toHaveAttribute("aria-sort", "descending");
    // ستونِ غیرِقابلِ مرتب‌سازی اصلاً ادعایی نمی‌کند
    expect(cells[2]).not.toHaveAttribute("aria-sort");
  });

  it("جدولِ خالی نوارِ مرتب‌سازی نمی‌سازد", () => {
    render(<Table headers={headers} rows={[]} onSort={vi.fn()} sortableColumns={[0]} />);
    expect(screen.queryByRole("button")).not.toBeInTheDocument();
  });
});
