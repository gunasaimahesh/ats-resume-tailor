import { useMemo, useState } from "react";
import type {
  AwardEntry,
  Band,
  CertificationEntry,
  EducationEntry,
  ExperienceEntry,
  JDKeyword,
  LanguageEntry,
  LoadingStage,
  ParsedResume,
  ProjectEntry,
  PublicationEntry,
  PortalInfo,
  ScoreReport,
  SkillGroup,
} from "../types";
import { Spinner } from "./InputStep";

interface Props {
  parsed: ParsedResume;
  jdKeywords: JDKeyword[] | null;
  beforePreview: ScoreReport | null;
  portalInfo: PortalInfo | null;
  loading: LoadingStage;
  onBack: () => void;
  onTailor: (edited: ParsedResume) => void;
}

const inputCls =
  "w-full rounded-lg border border-slate-700 bg-slate-900 px-3 py-2 text-sm text-slate-100 outline-none focus:border-indigo-400";
const labelCls = "mb-1 block text-xs font-medium uppercase tracking-wide text-slate-400";
const btnGhost =
  "rounded-lg border border-slate-700 px-3 py-1.5 text-xs font-medium text-slate-300 transition hover:border-slate-500 disabled:opacity-50";
const btnDanger =
  "rounded-lg border border-rose-900/60 px-2 py-1 text-xs text-rose-300 transition hover:border-rose-500 disabled:opacity-50";

function Card({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section className="rounded-2xl border border-slate-800 bg-slate-900/60 p-5">
      <h3 className="mb-4 text-sm font-semibold uppercase tracking-widest text-indigo-300">
        {title}
      </h3>
      {children}
    </section>
  );
}

function nextBulletId(resume: ParsedResume): string {
  let max = 0;
  for (const e of resume.experience)
    for (const b of e.bullets) {
      const n = Number(b.id.replace(/\D/g, ""));
      if (n > max) max = n;
    }
  for (const p of resume.projects)
    for (const b of p.bullets) {
      const n = Number(b.id.replace(/\D/g, ""));
      if (n > max) max = n;
    }
  return `B${max + 1}`;
}

function flattenSkills(groups: SkillGroup[]): string[] {
  const seen = new Set<string>();
  const out: string[] = [];
  for (const g of groups) {
    for (const item of g.items) {
      const key = item.toLowerCase();
      if (!item || seen.has(key)) continue;
      seen.add(key);
      out.push(item);
    }
  }
  return out;
}

function emptyEducation(): EducationEntry {
  return {
    school: null,
    degree: null,
    gpa: null,
    location: null,
    dates: null,
    raw_lines: [],
  };
}

function emptyExperience(): ExperienceEntry {
  return {
    company: null,
    title: null,
    location: null,
    dates: null,
    header_raw: "",
    bullets: [],
  };
}

function emptyProject(): ProjectEntry {
  return { name: "", dates: null, url: null, tech: null, bullets: [] };
}

function emptyCert(): CertificationEntry {
  return { name: "", issuer: null, date: null, url: null };
}

function emptyAward(): AwardEntry {
  return { text: "" };
}

function emptyPublication(): PublicationEntry {
  return { text: "" };
}

function emptyLanguage(): LanguageEntry {
  return { language: "", proficiency: null };
}

const bandChip: Record<Band, string> = {
  green: "bg-emerald-500/15 text-emerald-300 border-emerald-500/40",
  yellow: "bg-amber-500/15 text-amber-300 border-amber-500/40",
  red: "bg-rose-500/15 text-rose-300 border-rose-500/40",
};

const CATEGORY_ORDER = [
  "Languages",
  "Frameworks & Libraries",
  "Data & ML",
  "Cloud & DevOps",
  "Databases",
  "Observability",
  "Practices",
  "Tools",
  "Other",
];

function addClaimedSkill(
  groups: SkillGroup[],
  skill: string,
  category: string | null | undefined,
): SkillGroup[] {
  const lower = skill.toLowerCase();
  const targetCategory = category?.trim() || "Other";
  const next = groups.map((g) => ({
    ...g,
    items: [...g.items],
  }));
  for (const g of next) {
    if (g.items.some((i) => i.toLowerCase() === lower)) return next;
  }
  const existing = next.find((g) => g.category === targetCategory);
  if (existing) {
    existing.items.push(skill);
    return next;
  }
  // Insert new category in standard order when possible.
  const newGroup: SkillGroup = { category: targetCategory, items: [skill] };
  const targetIdx = CATEGORY_ORDER.indexOf(targetCategory);
  if (targetIdx === -1) return [...next, newGroup];
  let insertAt = next.length;
  for (let i = 0; i < next.length; i++) {
    const cat = next[i].category ?? "Other";
    const idx = CATEGORY_ORDER.indexOf(cat);
    if (idx === -1 || idx > targetIdx) {
      insertAt = i;
      break;
    }
  }
  next.splice(insertAt, 0, newGroup);
  return next;
}

function removeClaimedSkill(
  groups: SkillGroup[],
  skill: string,
): SkillGroup[] {
  const lower = skill.toLowerCase();
  return groups
    .map((g) => ({
      ...g,
      items: g.items.filter((i) => i.toLowerCase() !== lower),
    }))
    .filter((g) => g.items.length > 0 || g.category == null);
}

export default function ReviewStep({
  parsed,
  jdKeywords,
  beforePreview,
  portalInfo,
  loading,
  onBack,
  onTailor,
}: Props) {
  const [draft, setDraft] = useState<ParsedResume>(() => {
    const clone = structuredClone(parsed);
    if (!clone.skill_groups?.length && clone.skills?.length) {
      clone.skill_groups = [{ category: null, items: [...clone.skills] }];
    }
    clone.skill_groups ??= [];
    clone.certifications ??= [];
    clone.awards ??= [];
    clone.publications ??= [];
    clone.languages ??= [];
    clone.education ??= [];
    clone.headline ??= null;
    return clone;
  });
  // Skills the user claimed via the ATS checklist (not already on the resume).
  const [claimedSkills, setClaimedSkills] = useState<Set<string>>(() => new Set());

  const update = (patch: Partial<ParsedResume>) =>
    setDraft((d) => ({ ...d, ...patch }));

  const setContact = (field: keyof ParsedResume["contact"], value: string) => {
    update({
      contact: { ...draft.contact, [field]: value || null },
    });
  };

  const keywordByName = useMemo(() => {
    const map = new Map<string, JDKeyword>();
    for (const kw of jdKeywords ?? []) map.set(kw.keyword, kw);
    return map;
  }, [jdKeywords]);

  const matchedKeywords = useMemo(() => {
    if (!beforePreview) return [];
    // Show matched required/nice only in the primary chips (not mentioned).
    return beforePreview.matches.filter(
      (m) => m.status === "matched" && m.importance !== "mentioned",
    );
  }, [beforePreview]);

  const mentionedKeywords = useMemo(() => {
    if (!beforePreview) return [];
    return beforePreview.matches.filter((m) => m.importance === "mentioned");
  }, [beforePreview]);

  const claimableMissing = useMemo(() => {
    if (!beforePreview) return [];
    return beforePreview.matches
      .filter((m) => m.status === "missing")
      .map((m) => keywordByName.get(m.keyword))
      .filter(
        (kw): kw is JDKeyword =>
          !!kw &&
          kw.in_dictionary &&
          kw.importance !== "mentioned",
      )
      .sort((a, b) => {
        if (a.importance !== b.importance) {
          return a.importance === "required" ? -1 : 1;
        }
        return a.keyword.localeCompare(b.keyword);
      });
  }, [beforePreview, keywordByName]);

  const nonClaimableMissing = useMemo(() => {
    if (!beforePreview) return [];
    return beforePreview.matches
      .filter((m) => m.status === "missing")
      .map((m) => keywordByName.get(m.keyword))
      .filter(
        (kw): kw is JDKeyword =>
          !!kw && !kw.in_dictionary && kw.importance !== "mentioned",
      )
      .map((kw) => kw.keyword);
  }, [beforePreview, keywordByName]);

  const toggleClaim = (skill: string, checked: boolean) => {
    setClaimedSkills((prev) => {
      const next = new Set(prev);
      if (checked) next.add(skill);
      else next.delete(skill);
      return next;
    });
    setDraft((d) => {
      const category = keywordByName.get(skill)?.category ?? "Other";
      const skill_groups = checked
        ? addClaimedSkill(d.skill_groups, skill, category)
        : removeClaimedSkill(d.skill_groups, skill);
      return {
        ...d,
        skill_groups,
        skills: flattenSkills(skill_groups),
      };
    });
  };

  const submit = () => {
    const skills = flattenSkills(draft.skill_groups);
    onTailor({ ...draft, skills });
  };

  const busy = loading !== null;

  const addExperienceBullet = (i: number) => {
    const experience = [...draft.experience];
    const entry = experience[i];
    experience[i] = {
      ...entry,
      bullets: [
        ...entry.bullets,
        { id: nextBulletId(draft), text: "" },
      ],
    };
    update({ experience });
  };

  const addProjectBullet = (i: number) => {
    const projects = [...draft.projects];
    const project = projects[i];
    projects[i] = {
      ...project,
      bullets: [
        ...project.bullets,
        { id: nextBulletId(draft), text: "" },
      ],
    };
    update({ projects });
  };

  return (
    <div className="space-y-5">
      <p className="text-sm text-slate-400">
        This is what we extracted. Fix anything that looks off — the AI only
        ever sees and rewrites what&apos;s shown here (after you click Tailor).
      </p>

      {beforePreview && jdKeywords && jdKeywords.length > 0 && (
        <Card title="ATS fit for this JD">
          {portalInfo && (
            <p className="mb-3 text-xs text-slate-400">
              Screening as <span className="text-slate-200">{portalInfo.display_name}</span>
              {" — "}
              {portalInfo.hint}
            </p>
          )}
          <div className="mb-4 flex flex-wrap items-center gap-3">
            <p className="text-3xl font-bold text-slate-100">
              {beforePreview.score.toFixed(0)}
              <span className="text-base font-medium text-slate-500">/100</span>
            </p>
            <span
              className={`rounded-full border px-2.5 py-0.5 text-xs font-medium ${bandChip[beforePreview.band]}`}
            >
              {beforePreview.required_coverage.toFixed(0)}% of required keywords
            </span>
            {claimedSkills.size > 0 && (
              <span className="text-xs text-indigo-300">
                +{claimedSkills.size} skill{claimedSkills.size === 1 ? "" : "s"}{" "}
                claimed — will raise score after tailor
              </span>
            )}
          </div>

          {matchedKeywords.length > 0 && (
            <div className="mb-4">
              <p className={labelCls}>Already on your resume</p>
              <div className="mt-1.5 flex flex-wrap gap-2">
                {matchedKeywords.map((m) => (
                  <span
                    key={m.keyword}
                    className="inline-flex items-center gap-1 rounded-full border border-emerald-500/40 bg-emerald-500/10 px-2.5 py-1 text-xs text-emerald-300"
                  >
                    ✓ {m.keyword}
                    {m.importance === "required" && (
                      <span className="opacity-60">*</span>
                    )}
                  </span>
                ))}
              </div>
            </div>
          )}

          {claimableMissing.length > 0 && (
            <div className="mb-2">
              <p className={labelCls}>Missing skills — check if you have them</p>
              <p className="mb-2 text-xs text-slate-500">
                Only check skills you can defend in an interview. Checked items
                are added to your Skills section before tailoring.
              </p>
              <ul className="space-y-2">
                {claimableMissing.map((kw) => {
                  const checked = claimedSkills.has(kw.keyword);
                  return (
                    <li key={kw.keyword}>
                      <label className="flex cursor-pointer items-start gap-3 rounded-xl border border-slate-800 bg-slate-950/40 px-3 py-2.5 hover:border-slate-600">
                        <input
                          type="checkbox"
                          className="mt-0.5 h-4 w-4 rounded border-slate-600 bg-slate-900 text-indigo-500 focus:ring-indigo-400"
                          checked={checked}
                          disabled={busy}
                          onChange={(e) =>
                            toggleClaim(kw.keyword, e.target.checked)
                          }
                        />
                        <span className="flex-1 text-sm text-slate-200">
                          {kw.keyword}
                          {kw.importance === "required" ? (
                            <span className="ml-2 text-[10px] font-semibold uppercase tracking-wide text-rose-300/80">
                              required
                            </span>
                          ) : (
                            <span className="ml-2 text-[10px] font-semibold uppercase tracking-wide text-slate-500">
                              nice to have
                            </span>
                          )}
                        </span>
                      </label>
                    </li>
                  );
                })}
              </ul>
            </div>
          )}

          {claimableMissing.length === 0 && matchedKeywords.length > 0 && (
            <p className="text-xs text-slate-500">
              No missing dictionary skills to claim for this JD.
            </p>
          )}

          {mentionedKeywords.length > 0 && (
            <div className="mt-4">
              <p className={labelCls}>Also mentioned in the JD (marketing / about)</p>
              <p className="mb-1.5 text-xs text-slate-500">
                Not treated as required — kept for context only. No claim checkbox.
              </p>
              <div className="flex flex-wrap gap-2">
                {mentionedKeywords.map((m) => (
                  <span
                    key={m.keyword}
                    className={`inline-flex items-center gap-1 rounded-full border px-2.5 py-1 text-xs ${
                      m.status === "matched"
                        ? "border-slate-600 bg-slate-800/60 text-slate-300"
                        : "border-slate-700 bg-slate-900/40 text-slate-500"
                    }`}
                  >
                    {m.status === "matched" ? "✓ " : ""}
                    {m.keyword}
                  </span>
                ))}
              </div>
            </div>
          )}

          {nonClaimableMissing.length > 0 && (
            <p className="mt-3 text-xs text-slate-500">
              In qualifications but not a dictionary skill checkbox:{" "}
              {nonClaimableMissing.join(", ")}.
            </p>
          )}
        </Card>
      )}

      <Card title="Heading">
        <div className="grid gap-3 sm:grid-cols-2">
          <label>
            <span className={labelCls}>name</span>
            <input
              className={inputCls}
              value={draft.contact.name ?? ""}
              onChange={(e) => setContact("name", e.target.value)}
            />
          </label>
          <label>
            <span className={labelCls}>headline</span>
            <input
              className={inputCls}
              placeholder="e.g. Senior Software Engineer"
              value={draft.headline ?? ""}
              onChange={(e) => update({ headline: e.target.value || null })}
            />
          </label>
        </div>
        <div className="mt-3 grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
          {(
            [
              "email",
              "phone",
              "location",
              "linkedin",
              "github",
              "website",
            ] as const
          ).map((field) => (
            <label key={field}>
              <span className={labelCls}>{field}</span>
              <input
                className={inputCls}
                value={draft.contact[field] ?? ""}
                onChange={(e) => setContact(field, e.target.value)}
              />
            </label>
          ))}
        </div>
        {draft.contact.links.length > 0 && (
          <p className="mt-3 text-xs text-slate-400">
            Other links: {draft.contact.links.join("  ·  ")}
          </p>
        )}
      </Card>

      <Card title="Summary">
        <textarea
          className={`${inputCls} min-h-20 resize-y`}
          value={draft.summary ?? ""}
          placeholder="(no summary detected — you can write one, or leave blank for AI to draft from bullets)"
          onChange={(e) => update({ summary: e.target.value || null })}
        />
      </Card>

      <Card title="Skills">
        <div className="space-y-3">
          {draft.skill_groups.map((group, i) => (
            <div key={i} className="grid gap-2 sm:grid-cols-[10rem_1fr_auto]">
              <input
                className={inputCls}
                placeholder="Category"
                value={group.category ?? ""}
                onChange={(e) => {
                  const skill_groups = [...draft.skill_groups];
                  skill_groups[i] = {
                    ...group,
                    category: e.target.value || null,
                  };
                  update({ skill_groups });
                }}
              />
              <input
                className={inputCls}
                placeholder="Comma-separated skills"
                value={group.items.join(", ")}
                onChange={(e) => {
                  const skill_groups = [...draft.skill_groups];
                  skill_groups[i] = {
                    ...group,
                    items: e.target.value
                      .split(",")
                      .map((s) => s.trim())
                      .filter(Boolean),
                  };
                  update({ skill_groups });
                }}
              />
              <button
                type="button"
                className={btnDanger}
                disabled={busy}
                onClick={() =>
                  update({
                    skill_groups: draft.skill_groups.filter((_, j) => j !== i),
                  })
                }
              >
                Remove
              </button>
            </div>
          ))}
          <button
            type="button"
            className={btnGhost}
            disabled={busy}
            onClick={() =>
              update({
                skill_groups: [
                  ...draft.skill_groups,
                  { category: null, items: [] },
                ],
              })
            }
          >
            Add skill group
          </button>
        </div>
        <p className="mt-2 text-xs text-slate-500">
          The AI can only pick skills from these lists — it can never add ones
          you don&apos;t have.
        </p>
      </Card>

      <Card title="Experience">
        <div className="space-y-6">
          {draft.experience.map((entry, i) => (
            <div key={i} className="rounded-xl border border-slate-800 p-4">
              <div className="mb-3 flex justify-end">
                <button
                  type="button"
                  className={btnDanger}
                  disabled={busy}
                  onClick={() =>
                    update({
                      experience: draft.experience.filter((_, j) => j !== i),
                    })
                  }
                >
                  Remove job
                </button>
              </div>
              <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
                {(["title", "company", "location", "dates"] as const).map(
                  (field) => (
                    <label key={field}>
                      <span className={labelCls}>{field}</span>
                      <input
                        className={inputCls}
                        value={entry[field] ?? ""}
                        onChange={(e) => {
                          const experience = [...draft.experience];
                          experience[i] = {
                            ...entry,
                            [field]: e.target.value || null,
                            header_raw:
                              entry.header_raw ||
                              [entry.title, entry.company]
                                .filter(Boolean)
                                .join(" — "),
                          };
                          update({ experience });
                        }}
                      />
                    </label>
                  ),
                )}
              </div>
              <div className="mt-3 space-y-2">
                {entry.bullets.map((bullet, j) => (
                  <div key={bullet.id} className="flex items-start gap-2">
                    <span className="mt-2 shrink-0 rounded bg-slate-800 px-1.5 py-0.5 text-[10px] font-mono text-slate-400">
                      {bullet.id}
                    </span>
                    <textarea
                      className={`${inputCls} min-h-10 resize-y`}
                      rows={2}
                      value={bullet.text}
                      onChange={(e) => {
                        const experience = [...draft.experience];
                        const bullets = [...entry.bullets];
                        bullets[j] = { ...bullet, text: e.target.value };
                        experience[i] = { ...entry, bullets };
                        update({ experience });
                      }}
                    />
                    <button
                      type="button"
                      className={btnDanger}
                      disabled={busy}
                      onClick={() => {
                        const experience = [...draft.experience];
                        experience[i] = {
                          ...entry,
                          bullets: entry.bullets.filter((_, k) => k !== j),
                        };
                        update({ experience });
                      }}
                    >
                      ×
                    </button>
                  </div>
                ))}
                <button
                  type="button"
                  className={btnGhost}
                  disabled={busy}
                  onClick={() => addExperienceBullet(i)}
                >
                  Add bullet
                </button>
              </div>
            </div>
          ))}
          <button
            type="button"
            className={btnGhost}
            disabled={busy}
            onClick={() =>
              update({ experience: [...draft.experience, emptyExperience()] })
            }
          >
            Add job
          </button>
        </div>
      </Card>

      <Card title="Projects">
        <div className="space-y-4">
          {draft.projects.map((project, i) => (
            <div key={i} className="rounded-xl border border-slate-800 p-4">
              <div className="mb-3 flex justify-end">
                <button
                  type="button"
                  className={btnDanger}
                  disabled={busy}
                  onClick={() =>
                    update({
                      projects: draft.projects.filter((_, j) => j !== i),
                    })
                  }
                >
                  Remove
                </button>
              </div>
              <div className="grid gap-3 sm:grid-cols-2">
                {(["name", "dates", "url", "tech"] as const).map((field) => (
                  <label key={field}>
                    <span className={labelCls}>{field}</span>
                    <input
                      className={inputCls}
                      value={project[field] ?? ""}
                      onChange={(e) => {
                        const projects = [...draft.projects];
                        projects[i] = {
                          ...project,
                          [field]: e.target.value || (field === "name" ? "" : null),
                        };
                        update({ projects });
                      }}
                    />
                  </label>
                ))}
              </div>
              <div className="mt-3 space-y-2">
                {project.bullets.map((bullet, j) => (
                  <div key={bullet.id} className="flex items-start gap-2">
                    <span className="mt-2 shrink-0 rounded bg-slate-800 px-1.5 py-0.5 text-[10px] font-mono text-slate-400">
                      {bullet.id}
                    </span>
                    <textarea
                      className={`${inputCls} min-h-10 resize-y`}
                      rows={2}
                      value={bullet.text}
                      onChange={(e) => {
                        const projects = [...draft.projects];
                        const bullets = [...project.bullets];
                        bullets[j] = { ...bullet, text: e.target.value };
                        projects[i] = { ...project, bullets };
                        update({ projects });
                      }}
                    />
                    <button
                      type="button"
                      className={btnDanger}
                      disabled={busy}
                      onClick={() => {
                        const projects = [...draft.projects];
                        projects[i] = {
                          ...project,
                          bullets: project.bullets.filter((_, k) => k !== j),
                        };
                        update({ projects });
                      }}
                    >
                      ×
                    </button>
                  </div>
                ))}
                <button
                  type="button"
                  className={btnGhost}
                  disabled={busy}
                  onClick={() => addProjectBullet(i)}
                >
                  Add bullet
                </button>
              </div>
            </div>
          ))}
          <button
            type="button"
            className={btnGhost}
            disabled={busy}
            onClick={() =>
              update({ projects: [...draft.projects, emptyProject()] })
            }
          >
            Add project
          </button>
        </div>
      </Card>

      <Card title="Education">
        <div className="space-y-4">
          {draft.education.map((edu, i) => (
            <div key={i} className="rounded-xl border border-slate-800 p-4">
              <div className="mb-3 flex justify-end">
                <button
                  type="button"
                  className={btnDanger}
                  disabled={busy}
                  onClick={() =>
                    update({
                      education: draft.education.filter((_, j) => j !== i),
                    })
                  }
                >
                  Remove
                </button>
              </div>
              <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
                {(
                  ["school", "degree", "gpa", "location", "dates"] as const
                ).map((field) => (
                  <label key={field}>
                    <span className={labelCls}>
                      {field === "gpa" ? "CGPA / GPA" : field}
                    </span>
                    <input
                      className={inputCls}
                      value={edu[field] ?? ""}
                      onChange={(e) => {
                        const education = [...draft.education];
                        education[i] = {
                          ...edu,
                          [field]: e.target.value || null,
                        };
                        update({ education });
                      }}
                    />
                  </label>
                ))}
              </div>
            </div>
          ))}
          <button
            type="button"
            className={btnGhost}
            disabled={busy}
            onClick={() =>
              update({ education: [...draft.education, emptyEducation()] })
            }
          >
            Add education
          </button>
        </div>
      </Card>

      <Card title="Certifications">
        <div className="space-y-4">
          {draft.certifications.map((cert, i) => (
            <div key={i} className="rounded-xl border border-slate-800 p-4">
              <div className="mb-3 flex justify-end">
                <button
                  type="button"
                  className={btnDanger}
                  disabled={busy}
                  onClick={() =>
                    update({
                      certifications: draft.certifications.filter(
                        (_, j) => j !== i,
                      ),
                    })
                  }
                >
                  Remove
                </button>
              </div>
              <div className="grid gap-3 sm:grid-cols-2">
                {(["name", "issuer", "date", "url"] as const).map((field) => (
                  <label key={field}>
                    <span className={labelCls}>{field}</span>
                    <input
                      className={inputCls}
                      value={cert[field] ?? ""}
                      onChange={(e) => {
                        const certifications = [...draft.certifications];
                        certifications[i] = {
                          ...cert,
                          [field]:
                            e.target.value || (field === "name" ? "" : null),
                        };
                        update({ certifications });
                      }}
                    />
                  </label>
                ))}
              </div>
            </div>
          ))}
          <button
            type="button"
            className={btnGhost}
            disabled={busy}
            onClick={() =>
              update({
                certifications: [...draft.certifications, emptyCert()],
              })
            }
          >
            Add certification
          </button>
        </div>
      </Card>

      <Card title="Awards">
        <div className="space-y-3">
          {draft.awards.map((award, i) => (
            <div key={i} className="flex items-start gap-2">
              <input
                className={inputCls}
                placeholder="Achievement / award line"
                value={award.text}
                onChange={(e) => {
                  const awards = [...draft.awards];
                  awards[i] = { text: e.target.value };
                  update({ awards });
                }}
              />
              <button
                type="button"
                className={btnDanger}
                disabled={busy}
                onClick={() =>
                  update({
                    awards: draft.awards.filter((_, j) => j !== i),
                  })
                }
              >
                Remove
              </button>
            </div>
          ))}
          <button
            type="button"
            className={btnGhost}
            disabled={busy}
            onClick={() => update({ awards: [...draft.awards, emptyAward()] })}
          >
            Add award
          </button>
        </div>
      </Card>

      <Card title="Publications">
        <div className="space-y-3">
          {draft.publications.map((pub, i) => (
            <div key={i} className="flex items-start gap-2">
              <input
                className={inputCls}
                placeholder="Publication line"
                value={pub.text}
                onChange={(e) => {
                  const publications = [...draft.publications];
                  publications[i] = { text: e.target.value };
                  update({ publications });
                }}
              />
              <button
                type="button"
                className={btnDanger}
                disabled={busy}
                onClick={() =>
                  update({
                    publications: draft.publications.filter((_, j) => j !== i),
                  })
                }
              >
                Remove
              </button>
            </div>
          ))}
          <button
            type="button"
            className={btnGhost}
            disabled={busy}
            onClick={() =>
              update({
                publications: [...draft.publications, emptyPublication()],
              })
            }
          >
            Add publication
          </button>
        </div>
      </Card>

      <Card title="Languages">
        <div className="space-y-3">
          {draft.languages.map((lang, i) => (
            <div key={i} className="grid gap-2 sm:grid-cols-[1fr_1fr_auto]">
              <input
                className={inputCls}
                placeholder="Language"
                value={lang.language}
                onChange={(e) => {
                  const languages = [...draft.languages];
                  languages[i] = { ...lang, language: e.target.value };
                  update({ languages });
                }}
              />
              <input
                className={inputCls}
                placeholder="Proficiency"
                value={lang.proficiency ?? ""}
                onChange={(e) => {
                  const languages = [...draft.languages];
                  languages[i] = {
                    ...lang,
                    proficiency: e.target.value || null,
                  };
                  update({ languages });
                }}
              />
              <button
                type="button"
                className={btnDanger}
                disabled={busy}
                onClick={() =>
                  update({
                    languages: draft.languages.filter((_, j) => j !== i),
                  })
                }
              >
                Remove
              </button>
            </div>
          ))}
          <button
            type="button"
            className={btnGhost}
            disabled={busy}
            onClick={() =>
              update({ languages: [...draft.languages, emptyLanguage()] })
            }
          >
            Add language
          </button>
        </div>
      </Card>

      {draft.other_sections.length > 0 && (
        <Card title="Other sections">
          <div className="space-y-4">
            {draft.other_sections.map((section, i) => (
              <div key={i}>
                <p className="mb-2 text-sm font-medium text-slate-200">
                  {section.heading_raw}
                </p>
                <textarea
                  className={`${inputCls} min-h-16 resize-y`}
                  value={section.lines.join("\n")}
                  onChange={(e) => {
                    const other_sections = [...draft.other_sections];
                    other_sections[i] = {
                      ...section,
                      lines: e.target.value.split("\n"),
                    };
                    update({ other_sections });
                  }}
                />
              </div>
            ))}
          </div>
        </Card>
      )}

      <div className="flex items-center justify-between gap-4">
        <button
          onClick={onBack}
          disabled={busy}
          className="rounded-xl border border-slate-700 px-5 py-3 text-sm font-medium text-slate-300 transition hover:border-slate-500 disabled:opacity-50"
        >
          Back
        </button>
        <button
          onClick={submit}
          disabled={busy}
          className="rounded-xl bg-indigo-500 px-6 py-3 font-semibold text-white transition hover:bg-indigo-400 disabled:cursor-not-allowed disabled:bg-slate-700 disabled:text-slate-400"
        >
          {loading === "tailoring" ? (
            <span className="inline-flex items-center gap-2">
              <Spinner /> Rewriting with AI…
            </span>
          ) : loading === "rendering" ? (
            <span className="inline-flex items-center gap-2">
              <Spinner /> Rendering PDF…
            </span>
          ) : (
            "Tailor my resume"
          )}
        </button>
      </div>
    </div>
  );
}
