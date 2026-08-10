// Mirrors backend/schema.py

export interface ContactInfo {
  name: string | null;
  email: string | null;
  phone: string | null;
  location: string | null;
  linkedin: string | null;
  github: string | null;
  website: string | null;
  links: string[];
}

export interface Bullet {
  id: string;
  text: string;
}

export interface ExperienceEntry {
  company: string | null;
  title: string | null;
  dates: string | null;
  location: string | null;
  header_raw: string;
  bullets: Bullet[];
}

export interface EducationEntry {
  school: string | null;
  degree: string | null;
  gpa: string | null;
  location: string | null;
  dates: string | null;
  raw_lines: string[];
}

export interface ProjectEntry {
  name: string;
  dates: string | null;
  url: string | null;
  tech: string | null;
  bullets: Bullet[];
}

export interface SkillGroup {
  category: string | null;
  items: string[];
}

export interface CertificationEntry {
  name: string;
  issuer: string | null;
  date: string | null;
  url: string | null;
}

export interface AwardEntry {
  text: string;
}

export interface PublicationEntry {
  text: string;
}

export interface LanguageEntry {
  language: string;
  proficiency: string | null;
}

export interface SectionBlock {
  name: string;
  heading_raw: string;
  lines: string[];
}

export interface ParsedResume {
  contact: ContactInfo;
  headline: string | null;
  summary: string | null;
  skills: string[];
  skill_groups: SkillGroup[];
  experience: ExperienceEntry[];
  education: EducationEntry[];
  projects: ProjectEntry[];
  certifications: CertificationEntry[];
  awards: AwardEntry[];
  publications: PublicationEntry[];
  languages: LanguageEntry[];
  other_sections: SectionBlock[];
  raw_text: string;
  page_count: number | null;
}

export type Importance = "required" | "nice_to_have" | "mentioned";

export interface JDKeyword {
  keyword: string;
  importance: Importance;
  aliases_matched: string[];
  in_dictionary: boolean;
  /** Standard skill category for dictionary skills; null for YAKE extras. */
  category: string | null;
}

export interface PortalInfo {
  family: string;
  display_name: string;
  hint: string;
  force_classic_template: boolean;
}

export interface KeywordMatch {
  keyword: string;
  importance: Importance;
  status: "matched" | "missing";
  match_type: "exact" | "synonym" | "fuzzy" | null;
  matched_text: string | null;
  location: string | null;
}

export type Band = "green" | "yellow" | "red";

export interface ScoreReport {
  score: number;
  required_coverage: number;
  band: Band;
  matches: KeywordMatch[];
}

export interface ParseResponse {
  resume: ParsedResume;
  jd_keywords: JDKeyword[] | null;
  before: ScoreReport | null;
  portal: PortalInfo | null;
}

export interface TailoredBullet {
  id: string;
  original: string;
  text: string;
  changed: boolean;
  reverted: boolean;
  flags: string[];
}

export interface TailoredExperienceEntry {
  company: string | null;
  title: string | null;
  dates: string | null;
  location: string | null;
  header_raw: string;
  bullets: TailoredBullet[];
}

export interface TailoredProjectEntry {
  name: string;
  dates: string | null;
  url: string | null;
  tech: string | null;
  bullets: TailoredBullet[];
}

export interface TailoredResume {
  contact: ContactInfo;
  headline: string | null;
  summary: string | null;
  skills: string[];
  skill_groups: SkillGroup[];
  experience: TailoredExperienceEntry[];
  projects: TailoredProjectEntry[];
  education: EducationEntry[];
  certifications: CertificationEntry[];
  awards: AwardEntry[];
  publications: PublicationEntry[];
  languages: LanguageEntry[];
  other_sections: SectionBlock[];
}

export interface TailorResponse {
  tailored: TailoredResume;
  jd_keywords: JDKeyword[];
  before: ScoreReport;
  keyword_gaps: string[];
  keyword_repairs: string[];
  summary_flags: string[];
  portal: PortalInfo | null;
}

export interface RoundTripCheck {
  passed: boolean;
  issues: string[];
}

export type ResumeTemplate = "classic" | "two_column";

export type DensityStep = "normal" | "compact" | "dense";

export interface FitReport {
  density_step: DensityStep;
  requested_pages: number;
  actual_pages: number;
  template: ResumeTemplate;
}

export interface RenderResponse {
  pdf_base64: string;
  pages: number;
  target_pages: number;
  fit: FitReport;
  roundtrip: RoundTripCheck;
  after: ScoreReport | null;
  keyword_repairs: string[];
}

export type PageChoice = "auto" | "1" | "2" | "same_as_original";

export type LoadingStage =
  | "parsing"
  | "tailoring"
  | "rendering"
  | "downloading"
  | null;
