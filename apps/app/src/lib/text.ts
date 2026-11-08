/** Lower-case and strip Vietnamese diacritics, for accent-insensitive matching. */
export function fold(s: string): string {
  return s
    .toLowerCase()
    .normalize("NFD")
    .replace(/[̀-ͯ]/g, "")
    .replace(/đ/g, "d");
}

/** Plain text for speech synthesis: drop Markdown and math markup. */
export function plainText(md: string): string {
  return md
    .replace(/\$\$[\s\S]+?\$\$/g, " ")
    .replace(/\$[^$\n]+\$/g, " ")
    .replace(/\\\([\s\S]+?\\\)/g, " ")
    .replace(/[*_`#>]/g, "")
    .replace(/\[([^\]]+)\]\([^)]*\)/g, "$1")
    .replace(/\s+/g, " ")
    .trim();
}
