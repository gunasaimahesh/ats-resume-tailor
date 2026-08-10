import { useRef, useState } from "react";
import type { LoadingStage, PageChoice, ResumeTemplate } from "../types";

interface Props {
  file: File | null;
  setFile: (f: File | null) => void;
  jd: string;
  setJd: (v: string) => void;
  pageChoice: PageChoice;
  setPageChoice: (v: PageChoice) => void;
  template: ResumeTemplate;
  setTemplate: (v: ResumeTemplate) => void;
  accessCode: string;
  setAccessCode: (v: string) => void;
  companyName: string;
  setCompanyName: (v: string) => void;
  jobTitle: string;
  setJobTitle: (v: string) => void;
  jobPortal: string;
  setJobPortal: (v: string) => void;
  loading: LoadingStage;
  onSubmit: () => void;
}

export default function InputStep({
  file,
  setFile,
  jd,
  setJd,
  pageChoice,
  setPageChoice,
  template,
  setTemplate,
  accessCode,
  setAccessCode,
  companyName,
  setCompanyName,
  jobTitle,
  setJobTitle,
  jobPortal,
  setJobPortal,
  loading,
  onSubmit,
}: Props) {
  const [dragging, setDragging] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);

  const acceptFile = (f: File | undefined) => {
    if (!f) return;
    const name = f.name.toLowerCase();
    if (name.endsWith(".pdf") || name.endsWith(".docx")) setFile(f);
  };

  const ready = file !== null && jd.trim().length > 0 && loading === null;

  return (
    <div className="grid gap-6 lg:grid-cols-2">
      <div className="space-y-6">
        <div
          onDragOver={(e) => {
            e.preventDefault();
            setDragging(true);
          }}
          onDragLeave={() => setDragging(false)}
          onDrop={(e) => {
            e.preventDefault();
            setDragging(false);
            acceptFile(e.dataTransfer.files[0]);
          }}
          onClick={() => inputRef.current?.click()}
          className={`flex h-52 cursor-pointer flex-col items-center justify-center rounded-2xl border-2 border-dashed p-6 text-center transition
            ${dragging ? "border-indigo-400 bg-indigo-500/10" : "border-slate-700 bg-slate-900/60 hover:border-slate-500"}`}
        >
          <input
            ref={inputRef}
            type="file"
            accept=".pdf,.docx"
            className="hidden"
            onChange={(e) => acceptFile(e.target.files?.[0])}
          />
          {file ? (
            <>
              <p className="text-lg font-medium text-slate-100">{file.name}</p>
              <p className="mt-1 text-sm text-slate-400">
                {(file.size / 1024).toFixed(0)} KB — click to replace
              </p>
            </>
          ) : (
            <>
              <p className="text-lg font-medium text-slate-200">
                Drop your resume here
              </p>
              <p className="mt-1 text-sm text-slate-400">
                PDF or DOCX — or click to browse
              </p>
            </>
          )}
        </div>

        <div className="grid gap-4 sm:grid-cols-2">
          <label className="block">
            <span className="mb-1.5 block text-sm font-medium text-slate-300">
              Page count
            </span>
            <select
              value={pageChoice}
              onChange={(e) => setPageChoice(e.target.value as PageChoice)}
              className="w-full rounded-lg border border-slate-700 bg-slate-900 px-3 py-2.5 text-sm text-slate-100 outline-none focus:border-indigo-400"
            >
              <option value="same_as_original">Same as original (recommended)</option>
              <option value="auto">Auto (by experience)</option>
              <option value="1">1 page</option>
              <option value="2">2 pages</option>
            </select>
          </label>
          <label className="block">
            <span className="mb-1.5 block text-sm font-medium text-slate-300">
              Template
            </span>
            <select
              value={template}
              onChange={(e) => setTemplate(e.target.value as ResumeTemplate)}
              className="w-full rounded-lg border border-slate-700 bg-slate-900 px-3 py-2.5 text-sm text-slate-100 outline-none focus:border-indigo-400"
            >
              <option value="classic">Classic (single column — safest for ATS)</option>
              <option value="two_column">Two-column (fits more on one page)</option>
            </select>
          </label>
          <label className="block sm:col-span-2">
            <span className="mb-1.5 block text-sm font-medium text-slate-300">
              Access code
            </span>
            <input
              type="password"
              value={accessCode}
              onChange={(e) => setAccessCode(e.target.value)}
              placeholder="Shared access code"
              className="w-full rounded-lg border border-slate-700 bg-slate-900 px-3 py-2.5 text-sm text-slate-100 outline-none placeholder:text-slate-600 focus:border-indigo-400"
            />
          </label>
        </div>
        <p className="text-xs text-slate-500">
          Experience is never dropped to fit a page count — denser layout or an
          extra page is used instead. Two-column packs more content per page.
        </p>

        <div className="grid gap-4 sm:grid-cols-3">
          <label className="block sm:col-span-1">
            <span className="mb-1.5 block text-sm font-medium text-slate-300">
              Company <span className="font-normal text-slate-500">(optional)</span>
            </span>
            <input
              type="text"
              value={companyName}
              onChange={(e) => setCompanyName(e.target.value)}
              placeholder="e.g. Stripe"
              className="w-full rounded-lg border border-slate-700 bg-slate-900 px-3 py-2.5 text-sm text-slate-100 outline-none placeholder:text-slate-600 focus:border-indigo-400"
            />
          </label>
          <label className="block sm:col-span-1">
            <span className="mb-1.5 block text-sm font-medium text-slate-300">
              Job title <span className="font-normal text-slate-500">(optional)</span>
            </span>
            <input
              type="text"
              value={jobTitle}
              onChange={(e) => setJobTitle(e.target.value)}
              placeholder="e.g. Staff Engineer"
              className="w-full rounded-lg border border-slate-700 bg-slate-900 px-3 py-2.5 text-sm text-slate-100 outline-none placeholder:text-slate-600 focus:border-indigo-400"
            />
          </label>
          <label className="block sm:col-span-1">
            <span className="mb-1.5 block text-sm font-medium text-slate-300">
              Job portal / ATS
            </span>
            <select
              value={jobPortal}
              onChange={(e) => setJobPortal(e.target.value)}
              className="w-full rounded-lg border border-slate-700 bg-slate-900 px-3 py-2.5 text-sm text-slate-100 outline-none focus:border-indigo-400"
            >
              <option value="generic">Other / Unknown (safe default)</option>
              <option value="greenhouse">Greenhouse</option>
              <option value="ashby">Ashby</option>
              <option value="workday">Workday</option>
              <option value="lever">Lever</option>
              <option value="taleo">Taleo (Oracle)</option>
              <option value="icims">iCIMS</option>
              <option value="successfactors">SuccessFactors (SAP)</option>
              <option value="linkedin">LinkedIn</option>
              <option value="indeed">Indeed</option>
            </select>
          </label>
        </div>
        <p className="text-xs text-slate-500">
          Portal selects ATS screening knobs (exact vs criteria, template safety).
          Company / title only tune phrasing — never invents employment there.
        </p>
      </div>

      <div className="flex flex-col">
        <span className="mb-1.5 block text-sm font-medium text-slate-300">
          Job description
        </span>
        <textarea
          value={jd}
          onChange={(e) => setJd(e.target.value)}
          placeholder="Paste the full job description here..."
          className="min-h-64 flex-1 resize-y rounded-2xl border border-slate-700 bg-slate-900/60 p-4 text-sm leading-relaxed text-slate-100 outline-none placeholder:text-slate-600 focus:border-indigo-400"
        />
        <button
          onClick={onSubmit}
          disabled={!ready}
          className="mt-4 rounded-xl bg-indigo-500 px-6 py-3 font-semibold text-white transition hover:bg-indigo-400 disabled:cursor-not-allowed disabled:bg-slate-700 disabled:text-slate-400"
        >
          {loading === "parsing" ? (
            <span className="inline-flex items-center gap-2">
              <Spinner /> Extracting text from your resume…
            </span>
          ) : (
            "Extract & review"
          )}
        </button>
      </div>
    </div>
  );
}

export function Spinner() {
  return (
    <span className="inline-block h-4 w-4 animate-spin rounded-full border-2 border-white/30 border-t-white" />
  );
}
