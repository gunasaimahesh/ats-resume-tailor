"""Curated skills dictionary with synonym groups (pipeline step 2).

Maps a canonical skill name to every surface form we accept for it. Matching
is case-insensitive except for the short, ambiguous aliases listed in
CASE_SENSITIVE_ALIASES (e.g. "Go", "R", "REST"), which would otherwise match
ordinary English words.
"""

SKILL_SYNONYMS: dict[str, list[str]] = {
    # Languages
    "Python": ["Python", "Python3"],
    "JavaScript": ["JavaScript", "JS", "ECMAScript"],
    "TypeScript": ["TypeScript", "TS"],
    "Java": ["Java"],
    "C++": ["C++", "CPP"],
    "C#": ["C#", "C-sharp", "CSharp"],
    "Go": ["Golang", "Go"],
    "Ruby": ["Ruby"],
    "PHP": ["PHP"],
    "Swift": ["Swift"],
    "Kotlin": ["Kotlin"],
    "Rust": ["Rust"],
    "Scala": ["Scala"],
    "R": ["R"],
    "SQL": ["SQL"],
    "Bash": ["Bash", "Shell scripting", "Shell"],
    # Frontend
    "React": ["React", "React.js", "ReactJS"],
    "Angular": ["Angular", "AngularJS"],
    "Vue": ["Vue", "Vue.js", "VueJS"],
    "Next.js": ["Next.js", "NextJS", "Next js"],
    "Redux": ["Redux"],
    "HTML": ["HTML", "HTML5"],
    "CSS": ["CSS", "CSS3"],
    "Tailwind CSS": ["Tailwind", "Tailwind CSS", "TailwindCSS"],
    # Backend / frameworks
    "Node.js": ["Node.js", "NodeJS", "Node js", "Node"],
    "Django": ["Django"],
    "Flask": ["Flask"],
    "FastAPI": ["FastAPI", "Fast API"],
    "Spring Boot": ["Spring Boot", "Spring"],
    "Express": ["Express.js", "ExpressJS", "Express"],
    "Ruby on Rails": ["Ruby on Rails", "Rails"],
    ".NET": [".NET", "dotnet", "ASP.NET"],
    "GraphQL": ["GraphQL"],
    "REST APIs": ["REST API", "REST APIs", "RESTful", "RESTful API", "REST"],
    "gRPC": ["gRPC"],
    "Microservices": ["Microservices", "Micro-services", "Microservice"],
    "WebSockets": ["WebSockets", "WebSocket"],
    # Data / ML
    "Machine Learning": ["Machine Learning", "ML"],
    "Deep Learning": ["Deep Learning", "DL"],
    "NLP": ["NLP", "Natural Language Processing"],
    "Computer Vision": ["Computer Vision"],
    "LLMs": ["LLM", "LLMs", "Large Language Models", "Large Language Model"],
    "Generative AI": ["Generative AI", "GenAI", "Gen AI"],
    "PyTorch": ["PyTorch", "Torch"],
    "TensorFlow": ["TensorFlow", "Tensor Flow"],
    "scikit-learn": ["scikit-learn", "sklearn", "scikit learn"],
    "Pandas": ["Pandas"],
    "NumPy": ["NumPy"],
    "Spark": ["Apache Spark", "PySpark", "Spark"],
    "Hadoop": ["Hadoop"],
    "Kafka": ["Apache Kafka", "Kafka"],
    "Airflow": ["Apache Airflow", "Airflow"],
    "dbt": ["dbt"],
    "ETL": ["ETL", "ELT", "ETL pipelines"],
    "Data Warehousing": ["Data Warehouse", "Data Warehousing"],
    "Snowflake": ["Snowflake"],
    "Databricks": ["Databricks"],
    "Tableau": ["Tableau"],
    "Power BI": ["Power BI", "PowerBI"],
    "MLOps": ["MLOps", "ML Ops"],
    "A/B Testing": ["A/B Testing", "AB Testing", "A/B Tests"],
    # Cloud / DevOps
    "AWS": ["AWS", "Amazon Web Services"],
    # Drop bare "Google Cloud" — usually employer/product branding, not a skill ask.
    "GCP": ["GCP", "Google Cloud Platform"],
    "Azure": ["Azure", "Microsoft Azure"],
    "Docker": ["Docker", "Containers", "Containerization"],
    "Kubernetes": ["Kubernetes", "K8s", "K8S"],
    "Terraform": ["Terraform"],
    "Ansible": ["Ansible"],
    "Jenkins": ["Jenkins"],
    "GitHub Actions": ["GitHub Actions"],
    "CI/CD": ["CI/CD", "CICD", "Continuous Integration", "Continuous Delivery", "Continuous Deployment"],
    "Git": ["Git"],
    "Linux": ["Linux", "Unix"],
    "Serverless": ["Serverless", "AWS Lambda", "Lambda"],
    "Nginx": ["Nginx"],
    # Databases
    "PostgreSQL": ["PostgreSQL", "Postgres", "PostgresQL"],
    "MySQL": ["MySQL"],
    "MongoDB": ["MongoDB", "Mongo"],
    "Redis": ["Redis"],
    "Elasticsearch": ["Elasticsearch", "Elastic Search", "OpenSearch"],
    "DynamoDB": ["DynamoDB"],
    "Cassandra": ["Cassandra"],
    "SQLite": ["SQLite"],
    "Oracle": ["Oracle"],
    # Observability
    "Prometheus": ["Prometheus"],
    "Grafana": ["Grafana"],
    "Datadog": ["Datadog"],
    "Monitoring": ["Monitoring", "Observability"],
    # Practices / concepts
    "Agile": ["Agile", "Agile methodologies"],
    "Scrum": ["Scrum"],
    "TDD": ["TDD", "Test-Driven Development", "Test Driven Development"],
    "Unit Testing": ["Unit Testing", "Unit Tests"],
    "OOP": ["OOP", "Object-Oriented Programming", "Object Oriented Programming"],
    "Design Patterns": ["Design Patterns"],
    "Distributed Systems": ["Distributed Systems"],
    "System Design": ["System Design"],
    "Data Structures": ["Data Structures"],
    "Algorithms": ["Algorithms", "DSA"],
    # Bare "Security" matches English laundry lists; keep concrete forms only.
    "Security": [
        "Application Security",
        "AppSec",
        "Security Engineering",
        "Cybersecurity",
    ],
    # Tools
    "JIRA": ["JIRA"],
    "Figma": ["Figma"],
}

# Canonical skill -> standard resume category (for grouping on the PDF).
SKILL_CATEGORIES: dict[str, str] = {
    # Languages
    "Python": "Languages",
    "JavaScript": "Languages",
    "TypeScript": "Languages",
    "Java": "Languages",
    "C++": "Languages",
    "C#": "Languages",
    "Go": "Languages",
    "Ruby": "Languages",
    "PHP": "Languages",
    "Swift": "Languages",
    "Kotlin": "Languages",
    "Rust": "Languages",
    "Scala": "Languages",
    "R": "Languages",
    "SQL": "Languages",
    "Bash": "Languages",
    # Frameworks & Libraries (frontend + backend)
    "React": "Frameworks & Libraries",
    "Angular": "Frameworks & Libraries",
    "Vue": "Frameworks & Libraries",
    "Next.js": "Frameworks & Libraries",
    "Redux": "Frameworks & Libraries",
    "HTML": "Frameworks & Libraries",
    "CSS": "Frameworks & Libraries",
    "Tailwind CSS": "Frameworks & Libraries",
    "Node.js": "Frameworks & Libraries",
    "Django": "Frameworks & Libraries",
    "Flask": "Frameworks & Libraries",
    "FastAPI": "Frameworks & Libraries",
    "Spring Boot": "Frameworks & Libraries",
    "Express": "Frameworks & Libraries",
    "Ruby on Rails": "Frameworks & Libraries",
    ".NET": "Frameworks & Libraries",
    "GraphQL": "Frameworks & Libraries",
    "REST APIs": "Frameworks & Libraries",
    "gRPC": "Frameworks & Libraries",
    "Microservices": "Frameworks & Libraries",
    "WebSockets": "Frameworks & Libraries",
    # Data & ML
    "Machine Learning": "Data & ML",
    "Deep Learning": "Data & ML",
    "NLP": "Data & ML",
    "Computer Vision": "Data & ML",
    "LLMs": "Data & ML",
    "Generative AI": "Data & ML",
    "PyTorch": "Data & ML",
    "TensorFlow": "Data & ML",
    "scikit-learn": "Data & ML",
    "Pandas": "Data & ML",
    "NumPy": "Data & ML",
    "Spark": "Data & ML",
    "Hadoop": "Data & ML",
    "Kafka": "Data & ML",
    "Airflow": "Data & ML",
    "dbt": "Data & ML",
    "ETL": "Data & ML",
    "Data Warehousing": "Data & ML",
    "Snowflake": "Data & ML",
    "Databricks": "Data & ML",
    "Tableau": "Data & ML",
    "Power BI": "Data & ML",
    "MLOps": "Data & ML",
    "A/B Testing": "Data & ML",
    # Cloud & DevOps
    "AWS": "Cloud & DevOps",
    "GCP": "Cloud & DevOps",
    "Azure": "Cloud & DevOps",
    "Docker": "Cloud & DevOps",
    "Kubernetes": "Cloud & DevOps",
    "Terraform": "Cloud & DevOps",
    "Ansible": "Cloud & DevOps",
    "Jenkins": "Cloud & DevOps",
    "GitHub Actions": "Cloud & DevOps",
    "CI/CD": "Cloud & DevOps",
    "Git": "Cloud & DevOps",
    "Linux": "Cloud & DevOps",
    "Serverless": "Cloud & DevOps",
    "Nginx": "Cloud & DevOps",
    # Databases
    "PostgreSQL": "Databases",
    "MySQL": "Databases",
    "MongoDB": "Databases",
    "Redis": "Databases",
    "Elasticsearch": "Databases",
    "DynamoDB": "Databases",
    "Cassandra": "Databases",
    "SQLite": "Databases",
    "Oracle": "Databases",
    # Observability
    "Prometheus": "Observability",
    "Grafana": "Observability",
    "Datadog": "Observability",
    "Monitoring": "Observability",
    # Practices
    "Agile": "Practices",
    "Scrum": "Practices",
    "TDD": "Practices",
    "Unit Testing": "Practices",
    "OOP": "Practices",
    "Design Patterns": "Practices",
    "Distributed Systems": "Practices",
    "System Design": "Practices",
    "Data Structures": "Practices",
    "Algorithms": "Practices",
    "Security": "Practices",
    # Tools
    "JIRA": "Tools",
    "Figma": "Tools",
}

# Display order for skill groups on the resume.
CATEGORY_ORDER: list[str] = [
    "Languages",
    "Frameworks & Libraries",
    "Data & ML",
    "Cloud & DevOps",
    "Databases",
    "Observability",
    "Practices",
    "Tools",
    "Other",
]

# Alias (lower) -> canonical skill name for category lookup.
_ALIAS_TO_CANONICAL: dict[str, str] = {}
for _canonical, _aliases in SKILL_SYNONYMS.items():
    for _alias in _aliases:
        _ALIAS_TO_CANONICAL.setdefault(_alias.lower(), _canonical)


def resolve_canonical_skill(skill: str) -> str | None:
    """Return the dictionary canonical for a skill surface form, if known."""
    return _ALIAS_TO_CANONICAL.get(skill.lower())


def category_for_skill(skill: str) -> str:
    """Standard category for a skill; unknown skills go to 'Other'."""
    canonical = resolve_canonical_skill(skill) or skill
    return SKILL_CATEGORIES.get(canonical, "Other")


# Short aliases that collide with common English words if matched
# case-insensitively ("go to", "rest of", "spring", ...).
CASE_SENSITIVE_ALIASES: set[str] = {"Go", "R", "TS", "REST", "Spring", "Swift", "Express", "Shell", "Node", "Torch", "Mongo"}
