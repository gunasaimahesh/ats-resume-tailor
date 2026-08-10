import { useEffect, useMemo, useState } from "react";
import { parseResume, renderResume, tailorResume } from "./api";
import InputStep from "./components/InputStep";
import ReviewStep from "./components/ReviewStep";
import ResultsStep from "./components/ResultsStep";
import type {
  JDKeyword,
  LoadingStage,
  PageChoice,
  ParsedResume,
  PortalInfo,
  RenderResponse,
  ResumeTemplate,
  ScoreReport,
  TailoredResume,
  TailorResponse,
} from "./types";

const STEPS = ["Input", "Review", "Results"] as const;

function base64ToBlobUrl(b64: string): string {
  const bytes = Uint8Array.from(atob(b64), (c) => c.charCodeAt(0));
  return URL.createObjectURL(new Blob([bytes], { type: "application/pdf" }));
}

export default function App() {
  const [step, setStep] = useState<1 | 2 | 3>(1);
  const [file, setFile] = useState<File | null>(null);
  const [jd, setJd] = useState("");
  const [pageChoice, setPageChoice] = useState<PageChoice>("same_as_original");
  const [template, setTemplate] = useState<ResumeTemplate>("classic");
  const [accessCode, setAccessCode] = useState("");
  const [companyName, setCompanyName] = useState("");
  const [jobTitle, setJobTitle] = useState("");
  const [jobPortal, setJobPortal] = useState("generic");

  const [parsed, setParsed] = useState<ParsedResume | null>(null);
  const [jdKeywords, setJdKeywords] = useState<JDKeyword[] | null>(null);
  const [beforePreview, setBeforePreview] = useState<ScoreReport | null>(null);
  const [portalInfo, setPortalInfo] = useState<PortalInfo | null>(null);
  const [tailorResult, setTailorResult] = useState<TailorResponse | null>(null);
  const [renderResult, setRenderResult] = useState<RenderResponse | null>(null);
  const [accepted, setAccepted] = useState<Record<string, boolean>>({});

  const [loading, setLoading] = useState<LoadingStage>(null);
  const [error, setError] = useState<string | null>(null);

  const pdfUrl = useMemo(
    () => (renderResult ? base64ToBlobUrl(renderResult.pdf_base64) : null),
    [renderResult],
  );
  useEffect(() => {
    return () => {
      if (pdfUrl) URL.revokeObjectURL(pdfUrl);
    };
  }, [pdfUrl]);

  const tailorTargetPages = (resume: ParsedResume): number | null => {
    if (pageChoice === "1") return 1;
    if (pageChoice === "2") return 2;
    if (pageChoice === "same_as_original") return resume.page_count;
    return null; // auto -> backend heuristic (prefers original pages when known)
  };

  const renderTargetPages = (): number | "same_as_original" | null => {
    if (pageChoice === "1") return 1;
    if (pageChoice === "2") return 2;
    if (pageChoice === "same_as_original") return "same_as_original";
    return null;
  };

  const beforeMatched = (tailor: TailorResponse): string[] =>
    tailor.before.matches
      .filter((m) => m.status === "matched")
      .map((m) => m.keyword);

  async function handleParse() {
    if (!file) return;
    setError(null);
    setLoading("parsing");
    try {
      const response = await parseResume(file, jd, accessCode, jobPortal);
      setParsed(response.resume);
      setJdKeywords(response.jd_keywords);
      setBeforePreview(response.before);
      setPortalInfo(response.portal);
      if (response.portal?.force_classic_template) {
        setTemplate("classic");
      }
      setStep(2);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Parsing failed.");
    } finally {
      setLoading(null);
    }
  }

  async function handleTailor(edited: ParsedResume) {
    setParsed(edited);
    setError(null);
    try {
      setLoading("tailoring");
      const tailor = await tailorResume(
        edited,
        jd,
        tailorTargetPages(edited),
        accessCode,
        {
          companyName: companyName.trim() || undefined,
          jobTitle: jobTitle.trim() || undefined,
          jobPortal: jobPortal.trim() || undefined,
        },
      );
      setTailorResult(tailor);

      setLoading("rendering");
      const effectiveTemplate =
        tailor.portal?.force_classic_template || portalInfo?.force_classic_template
          ? "classic"
          : template;
      if (effectiveTemplate !== template) setTemplate("classic");
      setPortalInfo(tailor.portal ?? portalInfo);
      const render = await renderResume(
        tailor.tailored,
        tailor.jd_keywords,
        renderTargetPages(),
        edited.page_count,
        accessCode,
        beforeMatched(tailor),
        effectiveTemplate,
        jobPortal,
      );
      setRenderResult(render);

      const initialAccepted: Record<string, boolean> = {};
      for (const entry of tailor.tailored.experience)
        for (const b of entry.bullets) initialAccepted[b.id] = true;
      for (const project of tailor.tailored.projects)
        for (const b of project.bullets) initialAccepted[b.id] = true;
      setAccepted(initialAccepted);
      setStep(3);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Tailoring failed.");
    } finally {
      setLoading(null);
    }
  }

  function withAcceptedOnly(tailored: TailoredResume): TailoredResume {
    const adjusted = structuredClone(tailored);
    const applyChoice = (bullets: TailoredResume["experience"][0]["bullets"]) => {
      for (const bullet of bullets) {
        if (bullet.changed && !(accepted[bullet.id] ?? true)) {
          bullet.text = bullet.original;
          bullet.changed = false;
        }
      }
    };
    adjusted.experience.forEach((e) => applyChoice(e.bullets));
    adjusted.projects.forEach((p) => applyChoice(p.bullets));
    return adjusted;
  }

  async function handleDownload() {
    if (!tailorResult || !parsed) return;
    setError(null);
    setLoading("downloading");
    try {
      const effectiveTemplate =
        tailorResult.portal?.force_classic_template ||
        portalInfo?.force_classic_template
          ? "classic"
          : template;
      const render = await renderResume(
        withAcceptedOnly(tailorResult.tailored),
        tailorResult.jd_keywords,
        renderTargetPages(),
        parsed.page_count,
        accessCode,
        beforeMatched(tailorResult),
        effectiveTemplate,
        jobPortal,
      );
      setRenderResult(render); // refresh preview + after-score too
      const url = base64ToBlobUrl(render.pdf_base64);
      const anchor = document.createElement("a");
      anchor.href = url;
      anchor.download = "tailored_resume.pdf";
      anchor.click();
      setTimeout(() => URL.revokeObjectURL(url), 10_000);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Rendering failed.");
    } finally {
      setLoading(null);
    }
  }

  function startOver() {
    setStep(1);
    setParsed(null);
    setJdKeywords(null);
    setBeforePreview(null);
    setPortalInfo(null);
    setTailorResult(null);
    setRenderResult(null);
    setAccepted({});
    setError(null);
  }

  return (
    <div className="min-h-screen bg-slate-950 text-slate-100">
      <div className="mx-auto max-w-6xl px-6 py-10">
        <header className="mb-8 text-center">
          <h1 className="text-3xl font-bold tracking-tight">
            ATS Resume Tailor
          </h1>
          <p className="mt-1 text-sm text-slate-400">
            Rephrases your real experience in the job description's language —
            never invents anything.
          </p>
        </header>

        {/* Stepper */}
        <nav className="mb-10 flex items-center justify-center gap-2">
          {STEPS.map((label, i) => {
            const n = (i + 1) as 1 | 2 | 3;
            const active = step === n;
            const done = step > n;
            return (
              <div key={label} className="flex items-center gap-2">
                {i > 0 && <div className="h-px w-10 bg-slate-700" />}
                <div className="flex items-center gap-2">
                  <span
                    className={`flex h-7 w-7 items-center justify-center rounded-full text-xs font-bold
                      ${active ? "bg-indigo-500 text-white" : done ? "bg-emerald-500/20 text-emerald-300" : "bg-slate-800 text-slate-500"}`}
                  >
                    {done ? "✓" : n}
                  </span>
                  <span
                    className={`text-sm ${active ? "font-semibold text-slate-100" : "text-slate-500"}`}
                  >
                    {label}
                  </span>
                </div>
              </div>
            );
          })}
        </nav>

        {error && (
          <div className="mb-6 rounded-xl border border-rose-500/40 bg-rose-500/10 px-4 py-3 text-sm text-rose-300">
            {error}
          </div>
        )}

        {step === 1 && (
          <InputStep
            file={file}
            setFile={setFile}
            jd={jd}
            setJd={setJd}
            pageChoice={pageChoice}
            setPageChoice={setPageChoice}
            template={template}
            setTemplate={setTemplate}
            accessCode={accessCode}
            setAccessCode={setAccessCode}
            companyName={companyName}
            setCompanyName={setCompanyName}
            jobTitle={jobTitle}
            setJobTitle={setJobTitle}
            jobPortal={jobPortal}
            setJobPortal={setJobPortal}
            loading={loading}
            onSubmit={handleParse}
          />
        )}

        {step === 2 && parsed && (
          <ReviewStep
            key={parsed.raw_text}
            parsed={parsed}
            jdKeywords={jdKeywords}
            beforePreview={beforePreview}
            portalInfo={portalInfo}
            loading={loading}
            onBack={() => setStep(1)}
            onTailor={handleTailor}
          />
        )}

        {step === 3 && tailorResult && renderResult && (
          <ResultsStep
            tailorResult={tailorResult}
            renderResult={renderResult}
            beforePreview={beforePreview}
            pdfUrl={pdfUrl}
            accepted={accepted}
            onToggle={(id) =>
              setAccepted((a) => ({ ...a, [id]: !(a[id] ?? true) }))
            }
            loading={loading}
            onDownload={handleDownload}
            onStartOver={startOver}
          />
        )}
      </div>
    </div>
  );
}
