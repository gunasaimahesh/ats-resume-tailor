import type {
  JDKeyword,
  ParsedResume,
  ParseResponse,
  RenderResponse,
  ResumeTemplate,
  TailoredResume,
  TailorResponse,
} from "./types";

async function handle<T>(response: Response): Promise<T> {
  if (!response.ok) {
    let detail = `Request failed (${response.status})`;
    try {
      const body = await response.json();
      if (typeof body.detail === "string") detail = body.detail;
    } catch {
      // keep the generic message
    }
    throw new Error(detail);
  }
  return response.json() as Promise<T>;
}

function headers(accessCode: string): Record<string, string> {
  return accessCode ? { "X-Access-Code": accessCode } : {};
}

export async function parseResume(
  file: File,
  jobDescription: string,
  accessCode: string,
  jobPortal?: string,
): Promise<ParseResponse> {
  const form = new FormData();
  form.append("file", file);
  if (jobDescription.trim()) form.append("job_description", jobDescription);
  if (jobPortal?.trim()) form.append("job_portal", jobPortal.trim());
  const response = await fetch("/api/parse", {
    method: "POST",
    headers: headers(accessCode),
    body: form,
  });
  return handle<ParseResponse>(response);
}

export async function tailorResume(
  resume: ParsedResume,
  jobDescription: string,
  targetPages: number | null,
  accessCode: string,
  context?: {
    companyName?: string;
    jobTitle?: string;
    jobPortal?: string;
  },
): Promise<TailorResponse> {
  const response = await fetch("/api/tailor", {
    method: "POST",
    headers: { "Content-Type": "application/json", ...headers(accessCode) },
    body: JSON.stringify({
      resume,
      job_description: jobDescription,
      target_pages: targetPages,
      company_name: context?.companyName || null,
      job_title: context?.jobTitle || null,
      job_portal: context?.jobPortal || null,
    }),
  });
  return handle<TailorResponse>(response);
}

export async function renderResume(
  tailored: TailoredResume,
  jdKeywords: JDKeyword[],
  targetPages: number | "same_as_original" | null,
  originalPages: number | null,
  accessCode: string,
  beforeMatchedKeywords: string[] = [],
  template: ResumeTemplate = "classic",
  jobPortal?: string,
): Promise<RenderResponse> {
  const response = await fetch("/api/render", {
    method: "POST",
    headers: { "Content-Type": "application/json", ...headers(accessCode) },
    body: JSON.stringify({
      tailored,
      jd_keywords: jdKeywords,
      target_pages: targetPages,
      original_pages: originalPages,
      before_matched_keywords: beforeMatchedKeywords,
      template,
      job_portal: jobPortal || null,
    }),
  });
  return handle<RenderResponse>(response);
}
