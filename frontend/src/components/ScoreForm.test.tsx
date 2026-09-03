import { describe, expect, it, vi } from "vitest";
import { act, fireEvent, render, renderHook, screen } from "@testing-library/react";
import { ScoreFormTable, computePreview, scoredRows, useScoreForm } from "./ScoreForm";
import { DEFAULT_APP_CONFIG, type Indicator } from "../types";

function indicator(id: number, section: "general" | "specialized" = "general"): Indicator {
  return {
    id,
    section,
    category: `دسته ${id}`,
    description: `شرح ${id}`,
    display_order: id,
    is_active: true,
    created_at: "",
    updated_at: "",
    usage_count: 0,
    scheme_weight: 1,
  };
}

const INDICATORS = [indicator(1), indicator(2), indicator(3, "specialized")];

describe("useScoreForm", () => {
  it("starts every indicator UNSCORED (null) so the evaluator must touch each one", () => {
    const { result } = renderHook(() => useScoreForm(INDICATORS, []));
    expect(result.current.drafts.every((d) => d.score === null)).toBe(true);
    // با شاخص‌های بی‌امتیاز فرم معتبر نیست
    expect(result.current.isValid).toBe(false);
    expect(result.current.unscored).toHaveLength(INDICATORS.length);
  });

  it("becomes valid only once every indicator has a score", () => {
    const { result } = renderHook(() => useScoreForm(INDICATORS, []));
    act(() => {
      result.current.setScore(1, 3);
      result.current.setScore(2, 4);
    });
    expect(result.current.isValid).toBe(false); // indicator 3 still null
    act(() => {
      result.current.setScore(3, 2);
    });
    expect(result.current.unscored).toHaveLength(0);
    expect(result.current.isValid).toBe(true);
  });

  it("requires evidence only for scores 1 and 5 (min 3 words)", () => {
    const { result } = renderHook(() => useScoreForm(INDICATORS, []));
    act(() => {
      result.current.setScore(1, 5);
      result.current.setScore(2, 4);
      result.current.setScore(3, 3);
    });
    // امتیاز ۵ بدون شواهد → نقض؛ ۴ و ۳ نیازی ندارند
    expect(result.current.violations).toHaveLength(1);
    expect(result.current.isValid).toBe(false);

    act(() => {
      result.current.setEvidence(1, "یک دو سه");
    });
    expect(result.current.violations).toHaveLength(0);
    expect(result.current.isValid).toBe(true);
  });

  it("does not require evidence for middle scores 2/3/4", () => {
    const { result } = renderHook(() => useScoreForm([indicator(1)], []));
    act(() => {
      result.current.setScore(1, 2);
    });
    expect(result.current.violations).toHaveLength(0);
    expect(result.current.isValid).toBe(true);
  });

  it("hydrates existing saved scores", () => {
    const existing = [{ id: 10, indicator_id: 2, score: 4, evidence_text: "شواهد قبلی" }];
    const { result } = renderHook(() => useScoreForm(INDICATORS, existing));
    const draft = result.current.drafts.find((d) => d.indicator_id === 2);
    expect(draft?.score).toBe(4);
    expect(draft?.evidence_text).toBe("شواهد قبلی");
  });

  it("re-initialises when indicators arrive after the first render (manager-path race)", () => {
    const { result, rerender } = renderHook(
      ({ inds }) => useScoreForm(inds, []),
      { initialProps: { inds: [] as Indicator[] } }
    );
    expect(result.current.drafts).toHaveLength(0);
    expect(result.current.isValid).toBe(false);

    rerender({ inds: INDICATORS });
    expect(result.current.drafts).toHaveLength(INDICATORS.length);
    // بازسازی‌شده اما هنوز بی‌امتیاز → نامعتبر
    expect(result.current.isValid).toBe(false);
  });

  it("hydrates saved scores that arrive AFTER the first render", () => {
    // باگ واقعی: کاربر چند شاخص را امتیاز می‌داد (پیش‌نویس ذخیره می‌شد)، به داشبورد
    // می‌رفت و بدون رفرش برمی‌گشت. کش react-query هنوز نسخهٔ *پیش از ذخیره* را
    // داشت، پس فرم با آن پر می‌شد؛ refetch پس‌زمینه امتیازها را می‌آورد ولی فرم
    // فقط یک‌بار seed می‌شد و دیگر به‌روز نمی‌شد → «پیش‌نویس‌ها نیستند».
    const { result, rerender } = renderHook(
      ({ existing }) => useScoreForm(INDICATORS, existing),
      { initialProps: { existing: [] as { id: number; indicator_id: number; score: number; evidence_text: string | null }[] } }
    );
    expect(result.current.drafts.every((d) => d.score === null)).toBe(true);

    rerender({ existing: [{ id: 7, indicator_id: 2, score: 5, evidence_text: "شواهد ذخیره‌شده" }] });

    const draft = result.current.drafts.find((d) => d.indicator_id === 2);
    expect(draft?.score).toBe(5);
    expect(draft?.evidence_text).toBe("شواهد ذخیره‌شده");
  });

  it("never overwrites what the evaluator is typing with late server data", () => {
    const { result, rerender } = renderHook(
      ({ existing }) => useScoreForm(INDICATORS, existing),
      { initialProps: { existing: [] as { id: number; indicator_id: number; score: number; evidence_text: string | null }[] } }
    );
    act(() => {
      result.current.setScore(1, 4);
      result.current.setEvidence(1, "در حال تایپ");
    });

    // پاسخ کهنهٔ سرور می‌رسد — نباید ویرایش کاربر را پاک کند
    rerender({ existing: [{ id: 1, indicator_id: 1, score: 1, evidence_text: "" }] });

    const draft = result.current.drafts.find((d) => d.indicator_id === 1);
    expect(draft?.score).toBe(4);
    expect(draft?.evidence_text).toBe("در حال تایپ");
  });

  it("keeps the same drafts array when server data repeats, so autosave is not retriggered", () => {
    // یک آرایهٔ نو در هر refetch باعث می‌شد افکت autosave شلیک کند، آن هم کش را
    // به‌روز کند و دوباره همین چرخه — یک حلقهٔ ذخیرهٔ بی‌پایان.
    const row = { id: 3, indicator_id: 1, score: 3, evidence_text: null };
    const { result, rerender } = renderHook(({ e }) => useScoreForm(INDICATORS, e), {
      initialProps: { e: [row] },
    });
    const first = result.current.drafts;

    rerender({ e: [{ ...row }] }); // همان محتوا، آرایه/شیء تازه

    expect(result.current.drafts).toBe(first);
  });
});

describe("scoredRows", () => {
  it("omits unscored (null) rows and nullifies empty evidence", () => {
    const rows = scoredRows([
      { indicator_id: 1, score: 4, evidence_text: "متن" },
      { indicator_id: 2, score: null, evidence_text: "" },
      { indicator_id: 3, score: 3, evidence_text: "" },
    ]);
    expect(rows).toEqual([
      { indicator_id: 1, score: 4, evidence_text: "متن" },
      { indicator_id: 3, score: 3, evidence_text: null },
    ]);
  });
});

describe("ScoreFormTable slider", () => {
  it("renders an unset slider (no default) with the 'not chosen' label", () => {
    render(
      <ScoreFormTable
        section="general"
        indicators={[indicator(1)]}
        drafts={[{ indicator_id: 1, score: null, evidence_text: "" }]}
        onScoreChange={() => {}}
        onEvidenceChange={() => {}}
      />
    );
    const slider = screen.getByRole("slider");
    expect(slider).toHaveAttribute("aria-valuetext", "امتیازی انتخاب نشده");
    expect(slider).not.toHaveAttribute("aria-valuenow");
  });

  it("reports a score via keyboard (End = 5)", () => {
    const onScoreChange = vi.fn();
    render(
      <ScoreFormTable
        section="general"
        indicators={[indicator(1)]}
        drafts={[{ indicator_id: 1, score: null, evidence_text: "" }]}
        onScoreChange={onScoreChange}
        onEvidenceChange={() => {}}
      />
    );
    const slider = screen.getByRole("slider");
    fireEvent.keyDown(slider, { key: "End" });
    expect(onScoreChange).toHaveBeenCalledWith(1, 5);
  });

  it("جعبهٔ شواهد برای هر امتیازی قابل نوشتن است — اجباری بودنش فرق دارد", () => {
    /* پیش از این برای امتیازِ ۲ و ۳ و ۴ `disabled` بود و در همان حال خودش را
       «اختیاری» معرفی می‌کرد. سرور هیچ‌وقت شواهد را *ممنوع* نمی‌کند
       (`validate_evidence` فقط حداقل را برای امتیازهای اجباری می‌خواهد و سقف
       را برای همه)، پس ارزیابی که می‌خواست امتیاز ۲ — یعنی همان نمره‌ای که
       بیشتر از همه محل اعتراض است — را مستند کند، *نمی‌توانست*.

       و دادهٔ بی‌صاحب هم می‌ساخت: شواهد را روی ۵ می‌نوشتی، اسلایدر را به ۴
       می‌بردی، متن در پیش‌نویس می‌ماند، به سرور فرستاده می‌شد، همهٔ
       بازبین‌های بعدی می‌دیدندش، و نویسنده‌اش دیگر نمی‌توانست عوضش کند. */
    const { rerender } = render(
      <ScoreFormTable
        section="general"
        indicators={[indicator(1)]}
        drafts={[{ indicator_id: 1, score: 3, evidence_text: "" }]}
        onScoreChange={() => {}}
        onEvidenceChange={() => {}}
      />
    );
    expect(screen.getByRole("textbox")).toBeEnabled();
    // ستارهٔ «اجباری» نباید باشد…
    expect(screen.queryByText("*")).toBeNull();

    rerender(
      <ScoreFormTable
        section="general"
        indicators={[indicator(1)]}
        drafts={[{ indicator_id: 1, score: 5, evidence_text: "" }]}
        onScoreChange={() => {}}
        onEvidenceChange={() => {}}
      />
    );
    expect(screen.getByRole("textbox")).toBeEnabled();
    // …و برای امتیازِ اجباری، شمارنده کمبود را می‌گوید.
    expect(screen.getByText(/واژهٔ دیگر لازم است/)).toBeInTheDocument();
  });
});

describe("computePreview", () => {
  it("returns null for an empty draft list", () => {
    expect(computePreview([], INDICATORS)).toBeNull();
  });

  it("returns null while any indicator is still unscored", () => {
    const preview = computePreview(
      [
        { indicator_id: 1, score: 5, evidence_text: "" },
        { indicator_id: 2, score: null, evidence_text: "" },
        { indicator_id: 3, score: 1, evidence_text: "" },
      ],
      INDICATORS
    );
    expect(preview).toBeNull();
  });

  it("computes weighted percentages with the server formula", () => {
    // عمومی: (5+1)/10 = 60٪ ، تخصصی: 1/5 = 20٪ ← نهایی: 60*0.6 + 20*0.4 = 44٪
    const preview = computePreview(
      [
        { indicator_id: 1, score: 5, evidence_text: "" },
        { indicator_id: 2, score: 1, evidence_text: "" },
        { indicator_id: 3, score: 1, evidence_text: "" },
      ],
      INDICATORS
    );
    expect(preview).toEqual({ general_pct: 60, specialized_pct: 20, final_pct: 44 });
  });

  /* دو چیزی که این فرمول نداشت و هر دو عددِ حلقهٔ پیش‌نمایش را با عددِ
     ثبت‌شده جدا می‌کرد — و ارزیاب تصمیمش را روی همان حلقه می‌سازد. */

  it("وزنِ هر شاخص را مثل سرور اعمال می‌کند", () => {
    // شاخصِ ۱ وزن ۳ دارد: عمومی = (5×3 + 1×1)/(5×3 + 5×1) = 16/20 = ۸۰٪
    // تخصصی = 1/5 = ۲۰٪ ← نهایی = 80×0.6 + 20×0.4 = ۵۶٪
    const preview = computePreview(
      [
        { indicator_id: 1, score: 5, evidence_text: "" },
        { indicator_id: 2, score: 1, evidence_text: "" },
        { indicator_id: 3, score: 1, evidence_text: "" },
      ],
      INDICATORS,
      { ...DEFAULT_APP_CONFIG, indicator_weights: { "1": 3 } }
    );
    expect(preview).toEqual({ general_pct: 80, specialized_pct: 20, final_pct: 56 });
  });

  it("چارچوبِ تک‌بخشی: فرمِ پُرِ ۵ باید ۱۰۰٪ باشد، نه ۶۰٪", () => {
    // بخشِ تخصصی در این پرونده شاخصی ندارد، پس وزنش بین بخش‌های موجود پخش
    // می‌شود و سقف ۱۰۰ می‌ماند. پیش از این `general × 0.6 + 0 × 0.4` حساب
    // می‌شد: نمرهٔ کامل به‌عنوان «تمدید مشروط» پیش‌نمایش می‌شد و ۱۰۰٪ ثبت.
    const generalOnly = INDICATORS.filter((i) => i.section === "general");
    const preview = computePreview(
      generalOnly.map((i) => ({ indicator_id: i.id, score: 5, evidence_text: "دلیل" })),
      generalOnly
    );
    expect(preview).toEqual({ general_pct: 100, specialized_pct: 0, final_pct: 100 });
  });

  it("و قرینه‌اش برای چارچوبی که فقط شاخصِ تخصصی دارد", () => {
    const specializedOnly = INDICATORS.filter((i) => i.section !== "general");
    const preview = computePreview(
      specializedOnly.map((i) => ({ indicator_id: i.id, score: 5, evidence_text: "دلیل" })),
      specializedOnly
    );
    expect(preview).toEqual({ general_pct: 0, specialized_pct: 100, final_pct: 100 });
  });
});
