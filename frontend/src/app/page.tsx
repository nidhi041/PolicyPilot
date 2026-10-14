import type { ReactNode } from "react";
import Link from "next/link";

interface FeatureCardProps {
  icon: string;
  title: string;
  description: string;
}

function FeatureCard({ icon, title, description }: FeatureCardProps): ReactNode {
  return (
    <div className="feature-card group">
      <span className="feature-icon" aria-hidden="true">
        {icon}
      </span>
      <h3 className="feature-title">{title}</h3>
      <p className="feature-desc">{description}</p>
    </div>
  );
}

const FEATURES: FeatureCardProps[] = [
  {
    icon: "🔍",
    title: "Evidence-First Answers",
    description:
      "Every response is grounded in retrieved policy passages — never invented. Citations link to the exact source, version, and page.",
  },
  {
    icon: "🌍",
    title: "Region-Aware Retrieval",
    description:
      "Policies are filtered by the employee's authorised region and publication status, so every answer is applicable to you.",
  },
  {
    icon: "🛡️",
    title: "Safe Abstention",
    description:
      "When evidence is insufficient or ambiguous, PolicyPilot asks for clarification or clearly abstains instead of guessing.",
  },
  {
    icon: "📄",
    title: "Policy Management",
    description:
      "HR teams can upload, review, publish, version, replace, and archive PDF policies from a single control panel.",
  },
  {
    icon: "📊",
    title: "HR Analytics",
    description:
      "Track question trends, feedback, resolution outcomes, and knowledge gaps to continuously improve your policy coverage.",
  },
  {
    icon: "✅",
    title: "Evaluation & Feedback",
    description:
      "Measure retrieval quality, citation correctness, and answer reliability through built-in evaluation tooling.",
  },
];

export default function HomePage(): ReactNode {
  return (
    <div className="page-root">
      {/* ── Navigation ─────────────────────────────────────────── */}
      <header className="nav-bar" role="banner">
        <div className="nav-inner">
          <Link href="/" className="nav-logo" aria-label="PolicyPilot home">
            <span className="logo-mark" aria-hidden="true">✈</span>
            <span className="logo-text">PolicyPilot</span>
          </Link>
          <nav aria-label="Primary navigation">
            <ul className="nav-links" role="list">
              <li>
                <a href="#features" className="nav-link">
                  Features
                </a>
              </li>
              <li>
                <a href="#how-it-works" className="nav-link">
                  How it works
                </a>
              </li>
            </ul>
          </nav>
          <Link href="/chat" className="btn-nav-cta" aria-label="Open PolicyPilot chat">
            Ask a question
          </Link>
        </div>
      </header>

      {/* ── Hero ───────────────────────────────────────────────── */}
      <main id="main-content">
        <section className="hero-section" aria-labelledby="hero-heading">
          <div className="hero-glow" aria-hidden="true" />
          <div className="hero-content">
            <p className="hero-badge">AI-Powered · Region-Aware · Citation-Backed</p>
            <h1 id="hero-heading" className="hero-heading">
              HR Policies, Answered
              <br />
              <span className="hero-heading-accent">Instantly &amp; Accurately</span>
            </h1>
            <p className="hero-subheading">
              PolicyPilot gives employees trustworthy answers to company policy questions —
              grounded in your approved documents, filtered for their region, and always backed by
              a verifiable citation.
            </p>
            <div className="hero-actions">
              <Link href="/chat" id="hero-cta-primary" className="btn-primary">
                Ask your first question
              </Link>
              <a href="#how-it-works" id="hero-cta-secondary" className="btn-secondary">
                See how it works
              </a>
            </div>
          </div>

          {/* Chat preview widget */}
          <div className="chat-preview" aria-label="PolicyPilot chat preview" role="img">
            <div className="chat-header">
              <span className="chat-dot dot-red" />
              <span className="chat-dot dot-yellow" />
              <span className="chat-dot dot-green" />
              <span className="chat-title">PolicyPilot Chat</span>
            </div>
            <div className="chat-body">
              <div className="chat-msg user-msg">
                How many days of annual leave am I entitled to in India?
              </div>
              <div className="chat-msg bot-msg">
                <p>
                  Full-time employees in India are entitled to{" "}
                  <strong>21 calendar days</strong> of earned leave per year,
                  accruing at 1.75 days per month after probation.
                </p>
                <div className="chat-citation">
                  📄 Leave Policy · IN-2024-v3 · §3.2 · Page 7
                </div>
              </div>
            </div>
          </div>
        </section>

        {/* ── Features ───────────────────────────────────────────── */}
        <section id="features" className="features-section" aria-labelledby="features-heading">
          <div className="section-inner">
            <h2 id="features-heading" className="section-heading">
              Everything your team needs
            </h2>
            <p className="section-subheading">
              A complete platform for policy discovery, management, and insight.
            </p>
            <div className="features-grid">
              {FEATURES.map((f) => (
                <FeatureCard key={f.title} {...f} />
              ))}
            </div>
          </div>
        </section>

        {/* ── How it works ───────────────────────────────────────── */}
        <section
          id="how-it-works"
          className="how-section"
          aria-labelledby="how-heading"
        >
          <div className="section-inner">
            <h2 id="how-heading" className="section-heading">
              How PolicyPilot works
            </h2>
            <ol className="steps-list" role="list">
              {[
                {
                  step: "01",
                  title: "Employee asks a question",
                  body: "In natural language — no special syntax needed.",
                },
                {
                  step: "02",
                  title: "Region & role are resolved",
                  body: "Only policies applicable to the employee's authorised scope are considered.",
                },
                {
                  step: "03",
                  title: "Relevant chunks are retrieved",
                  body: "Semantic search finds the most relevant passages from published policy documents.",
                },
                {
                  step: "04",
                  title: "Answer is generated with citations",
                  body: "The LLM produces a grounded answer with source, version, and page references.",
                },
              ].map(({ step, title, body }) => (
                <li key={step} className="step-item">
                  <span className="step-number" aria-hidden="true">
                    {step}
                  </span>
                  <div>
                    <h3 className="step-title">{title}</h3>
                    <p className="step-body">{body}</p>
                  </div>
                </li>
              ))}
            </ol>
          </div>
        </section>

        {/* ── CTA banner ─────────────────────────────────────────── */}
        <section className="cta-section" aria-labelledby="cta-heading">
          <div className="section-inner cta-inner">
            <h2 id="cta-heading" className="cta-heading">
              Ready to eliminate repetitive HR questions?
            </h2>
            <p className="cta-body">
              Give your employees instant, trustworthy answers. Let HR focus on what matters.
            </p>
            <Link href="/chat" id="cta-final" className="btn-primary btn-lg">
              Get started &mdash; it&apos;s free
            </Link>
          </div>
        </section>
      </main>

      {/* ── Footer ─────────────────────────────────────────────── */}
      <footer className="site-footer" role="contentinfo">
        <div className="footer-inner">
          <p className="footer-brand">
            <span aria-hidden="true">✈</span> PolicyPilot AI
          </p>
          <p className="footer-tagline">Trusted Answers. Clear Policies. Better Employee Experiences.</p>
        </div>
      </footer>
    </div>
  );
}
