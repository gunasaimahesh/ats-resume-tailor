import type {
  Band,
  LoadingStage,
  RenderResponse,
  ScoreReport,
  TailoredBullet,
  TailorResponse,
} from "../types";
import { Spinner } from "./InputStep";

interface Props {
  tailorResult: TailorResponse;
  renderResult: RenderResponse;
  /** Parse-time ATS score (before claimed skills). Preferred for the Before card. */
  beforePreview: ScoreReport | null;
  pdfUrl: string | null;
  accepted: Record<string, boolean>;
  onToggle: (bulletId: string) => void;
  loading: LoadingStage;
  onDownload: () => void;
  onStartOver: () => void;
}

const bandStyles: Record<Band, { chip: string; ring: string; label: string }> = {
  green: {
    chip: "bg-emerald-500/15 text-emerald-300 border-emerald-500/40",
    ring: "text-emerald-400",
    label: "On target",
  },
  yellow: {
    chip: "bg-amber-500/15 text-amber-300 border-amber-500/40",
    ring: "text-amber-400",
    label: "Close — could be stronger",
  },
  red: {
    chip: "bg-rose-500/15 text-rose-300 border-rose-500/40",
    ring: "text-rose-400",
    label: "Below the 70-80% band",
  },
};

function ScoreCard({
  title,
  score,
  requiredCoverage,
  band,
}: {
  title: string;
  score: number;
  requiredCoverage: number;
  band: Band;
}) {
  const styles = bandStyles[band];
  return (
    <div className="flex-1 rounded-2xl border border-slate-800 bg-slate-900/60 p-5">
      <p className="text-xs font-semibold uppercase tracking-widest text-slate-400">
        {title}
      </p>
      <p className={`mt-2 text-4xl font-bold ${styles.ring}`}>
        {score.toFixed(0)}
        <span className="text-lg font-medium text-slate-500">/100</span>
      </p>
      <p className="mt-1 text-xs text-slate-400">
        {requiredCoverage.toFixed(0)}% of required keywords covered
      </p>
      <span
        className={`mt-3 inline-block rounded-full border px-2.5 py-0.5 text-xs font-medium ${styles.chip}`}
      >
        {styles.label}
      </span>
    </div>
  );
}

type KeywordStatus = "matched" | "added" | "missing";

function keywordStatuses(
  beforeScore: ScoreReport,
  renderResult: RenderResponse,
): {
  keyword: string;
  importance: string;
  status: KeywordStatus;
}[] {
  const beforeByName = new Map(
    beforeScore.matches.map((m) => [m.keyword, m.status]),
  );
  const afterMatches = renderResult.after?.matches ?? [];
  return afterMatches.map((m) => {
    const before = beforeByName.get(m.keyword);
    let status: KeywordStatus;
    if (m.importance === "mentioned") {
      // Mentioned never shown as red gaps.
      status = m.status === "matched" ? "matched" : "missing";
    } else if (m.status === "missing") status = "missing";
    else if (before === "missing" || before === undefined) status = "added";
    else status = "matched";
    return { keyword: m.keyword, importance: m.importance, status };
  });
}

const keywordStyles: Record<KeywordStatus, string> = {
  matched: "border-emerald-500/40 bg-emerald-500/10 text-emerald-300",
  added: "border-indigo-500/40 bg-indigo-500/10 text-indigo-300",
  missing: "border-rose-500/40 bg-rose-500/10 text-rose-300",
};

const mentionedStyle =
  "border-slate-600 bg-slate-800/50 text-slate-400";

const keywordIcon: Record<KeywordStatus, string> = {
  matched: "✓",
  added: "＋",
  missing: "✗",
};

function collectBullets(tailorResult: TailorResponse): TailoredBullet[] {
  return [
    ...tailorResult.tailored.experience.flatMap((e) => e.bullets),
    ...tailorResult.tailored.projects.flatMap((p) => p.bullets),
  ];
}

export default function ResultsStep({
  tailorResult,
  renderResult,
  beforePreview,
  pdfUrl,
  accepted,
  onToggle,
  loading,
  onDownload,
  onStartOver,
}: Props) {
  // Prefer parse-time before (true original) over tailor-time before
  // (which already includes claimed skills from Review).
  const beforeScore = beforePreview ?? tailorResult.before;
  const keywords = keywordStatuses(beforeScore, renderResult);
  const bullets = collectBullets(tailorResult);
  const changedBullets = bullets.filter((b) => b.changed);
  const revertedBullets = bullets.filter((b) => b.reverted);
  const after = renderResult.after;
  const fit = renderResult.fit;

  return (
    <div className="space-y-6">
      {/* Scores */}
      <div className="flex flex-col gap-4 sm:flex-row">
        <ScoreCard
          title="Before"
          score={beforeScore.score}
          requiredCoverage={beforeScore.required_coverage}
          band={beforeScore.band}
        />
        <div className="flex items-center justify-center text-2xl text-slate-500">
          →
        </div>
        {after && (
          <ScoreCard
            title="After"
            score={after.score}
            requiredCoverage={after.required_coverage}
            band={after.band}
          />
        )}
      </div>

      {/* Keyword checklist */}
      <section className="rounded-2xl border border-slate-800 bg-slate-900/60 p-5">
        <h3 className="mb-3 text-sm font-semibold uppercase tracking-widest text-indigo-300">
          Keyword checklist
        </h3>
        <div className="flex flex-wrap gap-2">
          {keywords.map(({ keyword, importance, status }) => {
            const isMentioned = importance === "mentioned";
            const style = isMentioned
              ? mentionedStyle
              : status === "missing"
                ? keywordStyles.missing
                : keywordStyles[status];
            return (
              <span
                key={keyword}
                title={
                  importance === "required"
                    ? "Required"
                    : importance === "nice_to_have"
                      ? "Nice to have"
                      : "Mentioned in About / marketing"
                }
                className={`inline-flex items-center gap-1.5 rounded-full border px-3 py-1 text-xs font-medium ${style}`}
              >
                <span>
                  {isMentioned
                    ? status === "matched"
                      ? "✓"
                      : "·"
                    : keywordIcon[status]}
                </span>
                {keyword}
                {importance === "required" && (
                  <span className="opacity-60">*</span>
                )}
                {isMentioned && (
                  <span className="opacity-50">mentioned</span>
                )}
              </span>
            );
          })}
        </div>
        <p className="mt-3 text-xs text-slate-500">
          ✓ matched &nbsp;·&nbsp; ＋ newly added &nbsp;·&nbsp; ✗ still missing
          &nbsp;·&nbsp; * required &nbsp;·&nbsp; mentioned = About/marketing (not a gap)
        </p>
        {(tailorResult.keyword_repairs.length > 0 ||
          renderResult.keyword_repairs.length > 0) && (
          <p className="mt-2 text-xs text-emerald-400/90">
            Preserved / repaired in Skills:{" "}
            {[
              ...new Set([
                ...tailorResult.keyword_repairs,
                ...renderResult.keyword_repairs,
              ]),
            ].join(", ")}
          </p>
        )}
        {tailorResult.keyword_gaps.length > 0 && (
          <p className="mt-2 text-xs text-amber-300/90">
            Gaps (no evidence on your resume — not invented):{" "}
            {tailorResult.keyword_gaps.join(", ")}
          </p>
        )}
        {tailorResult.summary_flags.length > 0 && (
          <p className="mt-2 text-xs text-slate-400">
            Summary notes: {tailorResult.summary_flags.join("; ")}
          </p>
        )}
      </section>

      <div className="grid gap-6 lg:grid-cols-2">
        {/* Diff + toggles */}
        <div className="space-y-4">
          <section className="rounded-2xl border border-slate-800 bg-slate-900/60 p-5">
            <h3 className="mb-1 text-sm font-semibold uppercase tracking-widest text-indigo-300">
              Changed bullets
            </h3>
            <p className="mb-4 text-xs text-slate-500">
              Reject any rewrite to keep the original wording. The download
              re-renders with only what you accept.
            </p>
            <div className="space-y-4">
              {changedBullets.map((bullet) => {
                const isAccepted = accepted[bullet.id] ?? true;
                return (
                  <div
                    key={bullet.id}
                    className="rounded-xl border border-slate-800 p-3"
                  >
                    <div className="mb-2 flex items-center justify-between">
                      <span className="rounded bg-slate-800 px-1.5 py-0.5 text-[10px] font-mono text-slate-400">
                        {bullet.id}
                      </span>
                      <button
                        onClick={() => onToggle(bullet.id)}
                        className={`rounded-full px-3 py-1 text-xs font-semibold transition ${
                          isAccepted
                            ? "bg-emerald-500/20 text-emerald-300 hover:bg-emerald-500/30"
                            : "bg-slate-700/60 text-slate-300 hover:bg-slate-700"
                        }`}
                      >
                        {isAccepted ? "✓ Accepted" : "Rejected — keeps original"}
                      </button>
                    </div>
                    <div className="grid gap-2 sm:grid-cols-2">
                      <div
                        className={`rounded-lg p-2.5 text-xs leading-relaxed ${
                          isAccepted
                            ? "bg-slate-950/60 text-slate-500"
                            : "bg-slate-950 text-slate-200 ring-1 ring-slate-600"
                        }`}
                      >
                        <p className="mb-1 text-[10px] font-semibold uppercase text-slate-500">
                          Original
                        </p>
                        {bullet.original}
                      </div>
                      <div
                        className={`rounded-lg p-2.5 text-xs leading-relaxed ${
                          isAccepted
                            ? "bg-indigo-950/40 text-slate-100 ring-1 ring-indigo-500/40"
                            : "bg-slate-950/60 text-slate-500"
                        }`}
                      >
                        <p className="mb-1 text-[10px] font-semibold uppercase text-indigo-400">
                          Tailored
                        </p>
                        {bullet.text}
                      </div>
                    </div>
                  </div>
                );
              })}
              {changedBullets.length === 0 && (
                <p className="text-sm text-slate-500">
                  No bullets were changed.
                </p>
              )}
            </div>
          </section>

          {revertedBullets.length > 0 && (
            <section className="rounded-2xl border border-amber-500/30 bg-amber-500/5 p-5">
              <h3 className="mb-1 text-sm font-semibold uppercase tracking-widest text-amber-300">
                Auto-reverted for safety
              </h3>
              <p className="mb-3 text-xs text-slate-400">
                The AI's rewrite of these bullets couldn't be verified against
                your original resume, so the original wording was kept.
              </p>
              <div className="space-y-3">
                {revertedBullets.map((bullet) => (
                  <div
                    key={bullet.id}
                    className="rounded-xl border border-slate-800 bg-slate-950/40 p-3"
                  >
                    <span className="rounded bg-slate-800 px-1.5 py-0.5 text-[10px] font-mono text-slate-400">
                      {bullet.id}
                    </span>
                    <p className="mt-2 text-xs text-slate-200">{bullet.text}</p>
                    <ul className="mt-2 space-y-1">
                      {bullet.flags.map((flag, i) => (
                        <li key={i} className="text-[11px] text-amber-300/80">
                          ⚑ {flag}
                        </li>
                      ))}
                    </ul>
                  </div>
                ))}
              </div>
            </section>
          )}

          {fit && (
            <p className="text-xs text-slate-500">
              Kept all experience
              {fit.density_step !== "normal"
                ? ` · rendered at ${fit.density_step} density`
                : ""}
              {fit.actual_pages > fit.requested_pages
                ? ` · used ${fit.actual_pages} page${fit.actual_pages > 1 ? "s" : ""} (requested ${fit.requested_pages})`
                : ` · ${fit.actual_pages} page${fit.actual_pages > 1 ? "s" : ""}`}
              {fit.template === "two_column" ? " · two-column template" : ""}.
            </p>
          )}
          {!renderResult.roundtrip.passed && (
            <p className="text-xs text-rose-400">
              Self-check warnings: {renderResult.roundtrip.issues.join("; ")}
            </p>
          )}
        </div>

        {/* PDF preview + download */}
        <div className="flex flex-col gap-4">
          <section className="flex-1 overflow-hidden rounded-2xl border border-slate-800 bg-slate-900/60">
            {pdfUrl ? (
              <object
                data={pdfUrl}
                type="application/pdf"
                className="h-full min-h-[540px] w-full"
              >
                <p className="p-6 text-sm text-slate-400">
                  Your browser can't preview PDFs inline —{" "}
                  <a href={pdfUrl} className="text-indigo-300 underline">
                    open it here
                  </a>
                  .
                </p>
              </object>
            ) : (
              <div className="flex h-full min-h-[540px] items-center justify-center text-slate-500">
                No preview available
              </div>
            )}
          </section>
          <div className="flex gap-3">
            <button
              onClick={onStartOver}
              className="rounded-xl border border-slate-700 px-5 py-3 text-sm font-medium text-slate-300 transition hover:border-slate-500"
            >
              Start over
            </button>
            <button
              onClick={onDownload}
              disabled={loading !== null}
              className="flex-1 rounded-xl bg-indigo-500 px-6 py-3 font-semibold text-white transition hover:bg-indigo-400 disabled:cursor-not-allowed disabled:bg-slate-700 disabled:text-slate-400"
            >
              {loading === "downloading" ? (
                <span className="inline-flex items-center justify-center gap-2">
                  <Spinner /> Re-rendering with your choices…
                </span>
              ) : (
                "Download PDF"
              )}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
