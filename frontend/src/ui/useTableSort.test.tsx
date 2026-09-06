import { describe, expect, it } from "vitest";
import { sortRows, type TableSort } from "./useTableSort";

type Row = { name: string; score: number | null };

const asc: TableSort = { column: 0, direction: "asc" };
const desc: TableSort = { column: 0, direction: "desc" };
const byName = [(r: Row) => r.name];
const byScore = [(r: Row) => r.score];

describe("sortRows", () => {
  it("بدون مرتب‌سازی، ترتیبِ اصلی را دست‌نخورده برمی‌گرداند", () => {
    const rows: Row[] = [{ name: "ب", score: 1 }, { name: "الف", score: 2 }];
    expect(sortRows(rows, null, byName).map((r) => r.name)).toEqual(["ب", "الف"]);
  });

  it("ورودی را تغییر نمی‌دهد", () => {
    const rows: Row[] = [{ name: "ب", score: 1 }, { name: "الف", score: 2 }];
    sortRows(rows, asc, byName);
    expect(rows.map((r) => r.name)).toEqual(["ب", "الف"]);
  });

  it("«آ» را کنارِ «ا» می‌گذارد، نه هفت خانه دورتر", () => {
    // ترتیبِ کدنقطه «امیر» را پیش از «آرش» می‌گذارد؛ خوانندهٔ فارسی برعکس.
    const rows: Row[] = [
      { name: "بهرام", score: 0 },
      { name: "امیر", score: 0 },
      { name: "آرش", score: 0 },
    ];
    expect(sortRows(rows, asc, byName).map((r) => r.name)).toEqual(["آرش", "امیر", "بهرام"]);
  });

  it("دو شکلِ «ی» و «ک» را یکی می‌شمارد", () => {
    // دادهٔ واردشده از اکسل هر دو شکل را دارد؛ بی نرمال‌سازی، این دو نام دو
    // سرِ فهرست می‌افتند.
    const rows: Row[] = [
      { name: "يوسفی", score: 0 },   // «ي» عربی
      { name: "احمدی", score: 0 },
      { name: "یوسفی", score: 0 },   // «ی» فارسی
    ];
    const names = sortRows(rows, asc, byName).map((r) => r.name);
    expect(names[0]).toBe("احمدی");
    expect(names.slice(1)).toEqual(expect.arrayContaining(["یوسفی", "يوسفی"]));
  });

  it("فاصله‌های ابتدای رشته را نادیده می‌گیرد", () => {
    const rows: Row[] = [{ name: " بهرام", score: 0 }, { name: "آرش", score: 0 }];
    expect(sortRows(rows, asc, byName).map((r) => r.name.trim())).toEqual(["آرش", "بهرام"]);
  });

  it("عدد را عددی مقایسه می‌کند، نه متنی", () => {
    const rows: Row[] = [
      { name: "a", score: 9 },
      { name: "b", score: 10 },
      { name: "c", score: 2 },
    ];
    expect(sortRows(rows, { column: 0, direction: "asc" }, byScore).map((r) => r.score)).toEqual([
      2, 9, 10,
    ]);
  });

  it("null همیشه آخر می‌ماند — در هر دو جهت", () => {
    // «ثبت‌نشده» مقدارِ کوچک نیست، نبودِ مقدار است. کسی که نزولی مرتب می‌کند
    // دنبالِ بزرگ‌ترین‌هاست، نه دنبالِ خالی‌ها.
    const rows: Row[] = [
      { name: "a", score: null },
      { name: "b", score: 5 },
      { name: "c", score: 8 },
    ];
    expect(sortRows(rows, asc, byScore).map((r) => r.score)).toEqual([5, 8, null]);
    expect(sortRows(rows, desc, byScore).map((r) => r.score)).toEqual([8, 5, null]);
  });

  it("ستونی که استخراج‌کننده ندارد، ترتیب را عوض نمی‌کند", () => {
    const rows: Row[] = [{ name: "ب", score: 1 }, { name: "الف", score: 2 }];
    expect(sortRows(rows, { column: 5, direction: "asc" }, byName).map((r) => r.name)).toEqual([
      "ب",
      "الف",
    ]);
  });
});
