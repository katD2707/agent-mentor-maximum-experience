/* Flat illustrations ported 1:1 from mockups/hs-00 (roles) and mockups/hs-01 (age bands). */
import type { AgeBand } from "../api/types";

export function StudentArt() {
  return (
    <svg viewBox="0 0 140 170" aria-hidden="true">
      <ellipse cx="70" cy="162" rx="40" ry="5" fill="var(--rule-strong)" />
      <rect x="40" y="74" width="20" height="38" rx="7" fill="#2F6FB5" />
      <rect x="55" y="114" width="12" height="44" rx="4" fill="#25305C" />
      <rect x="73" y="114" width="12" height="44" rx="4" fill="#25305C" />
      <rect x="50" y="66" width="40" height="54" rx="11" fill="#fff" stroke="#CFCAEB" strokeWidth="2" />
      <path d="M62 68 L70 80 L78 68" stroke="#CFCAEB" strokeWidth="2" fill="none" />
      <path d="M62 68 L70 84 L78 68 Z" fill="#E5484D" />
      <rect x="80" y="88" width="22" height="28" rx="3" fill="#FFB020" transform="rotate(-8 91 102)" />
      <circle cx="70" cy="46" r="18" fill="#F2C49B" />
      <path d="M52 44 C52 26 88 24 88 44 L84 38 C76 34 62 34 54 40 Z" fill="#2B2321" />
      <circle cx="64" cy="48" r="2.2" fill="#2B2321" />
      <circle cx="76" cy="48" r="2.2" fill="#2B2321" />
      <path d="M65 55 Q70 59 75 55" stroke="#2B2321" strokeWidth="2" fill="none" strokeLinecap="round" />
    </svg>
  );
}

export function TeacherArt() {
  return (
    <svg viewBox="0 0 140 170" aria-hidden="true">
      <ellipse cx="70" cy="162" rx="44" ry="5" fill="var(--rule-strong)" />
      <rect x="84" y="30" width="48" height="36" rx="4" fill="#24453A" stroke="#8A5A2B" strokeWidth="3" />
      <path d="M92 44 h8 M96 40 v8 M106 44 h8 M92 56 q6 -6 12 0 t12 0" stroke="#E9F2EC" strokeWidth="2" fill="none" strokeLinecap="round" />
      <rect x="49" y="112" width="13" height="46" rx="4" fill="#3B3F4A" />
      <rect x="66" y="112" width="13" height="46" rx="4" fill="#3B3F4A" />
      <rect x="40" y="62" width="48" height="58" rx="13" fill="#12825A" />
      <path d="M56 64 L64 80 L72 64" fill="#fff" />
      <rect x="30" y="86" width="26" height="20" rx="3" fill="#4B2EBF" transform="rotate(6 43 96)" />
      <path d="M88 82 L112 62" stroke="#8A5A2B" strokeWidth="3.5" strokeLinecap="round" />
      <circle cx="64" cy="40" r="18" fill="#E2AE85" />
      <path d="M46 40 C44 20 84 18 82 40 C80 30 74 26 64 26 C54 26 48 30 46 40 Z" fill="#4A3A35" />
      <rect x="53" y="38" width="10" height="7" rx="2.5" fill="none" stroke="#2B2321" strokeWidth="1.8" />
      <rect x="66" y="38" width="10" height="7" rx="2.5" fill="none" stroke="#2B2321" strokeWidth="1.8" />
      <path d="M63 41 h3" stroke="#2B2321" strokeWidth="1.8" />
      <path d="M59 51 Q64 55 69 51" stroke="#2B2321" strokeWidth="2" fill="none" strokeLinecap="round" />
    </svg>
  );
}

function Child() {
  return (
    <svg viewBox="0 0 120 170" aria-hidden="true">
      <ellipse cx="60" cy="162" rx="34" ry="5" fill="var(--rule-strong)" />
      <rect x="30" y="92" width="20" height="34" rx="6" fill="#2F6FB5" />
      <rect x="47" y="128" width="10" height="30" rx="4" fill="#25305C" />
      <rect x="63" y="128" width="10" height="30" rx="4" fill="#25305C" />
      <rect x="42" y="88" width="36" height="44" rx="10" fill="#fff" stroke="#CFCAEB" strokeWidth="2" />
      <path d="M50 90 L60 108 L70 90 Z" fill="#E5484D" />
      <circle cx="60" cy="68" r="20" fill="#F4C9A1" />
      <path d="M40 66 C40 48 80 46 80 64 C72 58 52 58 40 66 Z" fill="#2B2321" />
      <circle cx="53" cy="70" r="2.4" fill="#2B2321" />
      <circle cx="67" cy="70" r="2.4" fill="#2B2321" />
      <path d="M54 78 Q60 83 66 78" stroke="#2B2321" strokeWidth="2" fill="none" strokeLinecap="round" />
    </svg>
  );
}

function MiddleSchool() {
  return (
    <svg viewBox="0 0 120 170" aria-hidden="true">
      <ellipse cx="60" cy="162" rx="34" ry="5" fill="var(--rule-strong)" />
      <rect x="46" y="112" width="12" height="46" rx="4" fill="#25305C" />
      <rect x="62" y="112" width="12" height="46" rx="4" fill="#25305C" />
      <rect x="40" y="64" width="40" height="54" rx="10" fill="#fff" stroke="#CFCAEB" strokeWidth="2" />
      <path d="M52 66 L60 78 L68 66" stroke="#CFCAEB" strokeWidth="2" fill="none" />
      <rect x="70" y="86" width="22" height="28" rx="3" fill="#FFB020" transform="rotate(-8 81 100)" />
      <circle cx="60" cy="44" r="18" fill="#E9B98E" />
      <path d="M42 42 C42 24 78 22 78 42 L74 36 C66 32 52 32 44 38 Z" fill="#2B2321" />
      <circle cx="54" cy="46" r="2.2" fill="#2B2321" />
      <circle cx="66" cy="46" r="2.2" fill="#2B2321" />
      <path d="M55 53 Q60 57 65 53" stroke="#2B2321" strokeWidth="2" fill="none" strokeLinecap="round" />
    </svg>
  );
}

function HighSchool() {
  return (
    <svg viewBox="0 0 120 170" aria-hidden="true">
      <ellipse cx="60" cy="162" rx="34" ry="5" fill="var(--rule-strong)" />
      <path d="M44 100 L40 158 L80 158 L76 100 Z" fill="#F3F1FA" stroke="#CFCAEB" strokeWidth="2" />
      <path d="M44 52 C40 80 40 120 46 150 L74 150 C80 120 80 80 76 52 Z" fill="#fff" stroke="#CFCAEB" strokeWidth="2" />
      <path d="M60 52 L60 150" stroke="#E6E3F4" strokeWidth="2" />
      <path d="M40 34 C38 60 40 84 44 96 L50 60 Z" fill="#2B2321" />
      <path d="M80 34 C82 60 80 84 76 96 L70 60 Z" fill="#2B2321" />
      <circle cx="60" cy="34" r="17" fill="#F2C49B" />
      <path d="M42 34 C42 14 78 14 78 34 C70 26 50 26 42 34 Z" fill="#2B2321" />
      <circle cx="54" cy="36" r="2.2" fill="#2B2321" />
      <circle cx="66" cy="36" r="2.2" fill="#2B2321" />
      <path d="M55 43 Q60 47 65 43" stroke="#2B2321" strokeWidth="2" fill="none" strokeLinecap="round" />
    </svg>
  );
}

function University() {
  return (
    <svg viewBox="0 0 120 170" aria-hidden="true">
      <ellipse cx="60" cy="162" rx="34" ry="5" fill="var(--rule-strong)" />
      <rect x="45" y="106" width="13" height="52" rx="4" fill="#3B3F4A" />
      <rect x="62" y="106" width="13" height="52" rx="4" fill="#3B3F4A" />
      <rect x="36" y="50" width="48" height="62" rx="14" fill="#4B2EBF" />
      <path d="M48 52 Q60 64 72 52" stroke="#3A2299" strokeWidth="3" fill="none" />
      <rect x="30" y="84" width="40" height="26" rx="3" fill="#C9CCD6" />
      <rect x="33" y="87" width="34" height="18" rx="2" fill="#E9EDF5" />
      <circle cx="60" cy="30" r="17" fill="#D9A47C" />
      <path d="M43 28 C44 10 78 10 77 28 L72 22 C64 18 52 19 46 24 Z" fill="#2B2321" />
      <rect x="49" y="28" width="9" height="6" rx="2" fill="none" stroke="#2B2321" strokeWidth="1.6" />
      <rect x="62" y="28" width="9" height="6" rx="2" fill="none" stroke="#2B2321" strokeWidth="1.6" />
      <path d="M58 31 h4" stroke="#2B2321" strokeWidth="1.6" />
      <path d="M55 40 Q60 43 65 40" stroke="#2B2321" strokeWidth="2" fill="none" strokeLinecap="round" />
    </svg>
  );
}

export function AgeArt({ band }: { band: AgeBand }) {
  return { g1_5: <Child />, g6_9: <MiddleSchool />, g10_12: <HighSchool />, uni: <University /> }[band];
}
