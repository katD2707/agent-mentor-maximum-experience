/**
 * First-login setup guide: which steps a learner sees and whether each one is done.
 * Pure functions, so the rules are unit-tested without React (setupGuide.test.ts).
 */
import type { GoogleCalendarStatus, Me, ParentLinkState, Role } from "./types";

export type SetupStepId =
  | "parent"
  | "calendar"
  | "email"
  | "papers"
  | "phone"
  | "desktop"
  | "proactivity"
  | "memory"
  | "privacy";

/** done / not yet from the API; null when the API has no status for the step (then "visited" stands in). */
export type StepStatus = "done" | "todo" | null;

export type StepAction =
  | { kind: "link"; href: string; label: string }
  | { kind: "external"; href: string; label: string }
  | { kind: "calendar"; label: string }
  | { kind: "mobile-upload"; label: string };

export interface SetupStep {
  id: SetupStepId;
  title: string;
  body: string;
  /** shown under the body in smaller text */
  hint?: string;
  status: StepStatus;
  action: StepAction | null;
  /** NCS paper search: prompts the learner can click to put into the chat box */
  prompts?: string[];
  /** NCS forwarding address, shown with a copy button */
  address?: string;
}

/** Live data for the statuses; undefined = still loading or not fetched. */
export interface SetupContext {
  role: Role | null;
  /** NEXT_PUBLIC_DESKTOP_DOWNLOAD_URL (Windows installer); the desktop step is hidden without it */
  desktopDownloadUrl?: string | null;
  /** NEXT_PUBLIC_DESKTOP_DOWNLOAD_URL_LINUX (.deb or AppImage); offered instead on Linux desktops */
  desktopDownloadUrlLinux?: string | null;
  /** the browser runs on a Linux desktop (isLinuxDesktop) */
  linuxDesktop?: boolean;
  /** already running inside the desktop pop-up (so the app is installed) */
  inDesktopApp?: boolean;
  parentLink?: ParentLinkState;
  calendar?: Pick<GoogleCalendarStatus, "available" | "connected">;
  inboundEmailAddress?: string | null;
  /** at least one forwarded mail arrived in inbox/email/ */
  emailReceived?: boolean;
}

export const PAPER_PROMPTS = [
  "Tìm giúp mình 5 paper mới nhất về chủ đề luận văn của mình",
  "Những paper nào trích dẫn “Attention Is All You Need” từ năm 2023 trở lại đây?",
  "Tóm tắt các hướng nghiên cứu chính về retrieval-augmented generation trong 2 năm gần đây",
];

function httpUrl(raw: string | undefined): string | null {
  const v = raw?.trim();
  return v && /^https?:\/\//i.test(v) ? v : null;
}

// Each NEXT_PUBLIC_* is read by its literal name: Next inlines only those into the client bundle.
export function desktopDownloadUrl(): string | null {
  return httpUrl(process.env.NEXT_PUBLIC_DESKTOP_DOWNLOAD_URL);
}

export function desktopDownloadUrlLinux(): string | null {
  return httpUrl(process.env.NEXT_PUBLIC_DESKTOP_DOWNLOAD_URL_LINUX);
}

/** A Linux desktop browser; Android and ChromeOS also say "Linux" but cannot install the packages. */
export function isLinuxDesktop(userAgent: string): boolean {
  return /\b(Linux|X11)\b/i.test(userAgent) && !/Android|CrOS/i.test(userAgent);
}

/** Open the guide by itself only once: onboarding is active and the gateway reports it was never closed. */
export function shouldAutoOpen(me: Pick<Me, "onboarding_state" | "setup_guide_dismissed_at">): boolean {
  // undefined = a gateway without the flag: never auto-open, or it would come back on every visit.
  return me.onboarding_state === "active" && me.setup_guide_dismissed_at === null;
}

function flag(v: boolean | undefined): StepStatus {
  return v === undefined ? null : v ? "done" : "todo";
}

export function buildSetupSteps(ctx: SetupContext): SetupStep[] {
  const steps: SetupStep[] = [];
  const ncs = ctx.role === "ncs";

  if (ctx.role === "thpt") {
    steps.push({
      id: "parent",
      title: "Liên kết phụ huynh qua Zalo",
      body:
        "Phụ huynh nhận báo cáo học tập 2 tuần một lần và cảnh báo an toàn khi cần. Báo cáo không có nội dung trò chuyện hay những gì em kể riêng với Mentor.",
      status: ctx.parentLink === undefined ? null : ctx.parentLink === "verified" ? "done" : "todo",
      action: ctx.parentLink === "verified" ? { kind: "link", href: "/reports", label: "Xem báo cáo phụ huynh" } : { kind: "link", href: "/onboarding", label: "Liên kết" },
    });
  }

  if (ncs && ctx.calendar?.available) {
    steps.push({
      id: "calendar",
      title: "Kết nối Google Calendar",
      body:
        "Mentor xem lịch để lên kế hoạch tuần. Mentor chỉ thêm, sửa, xoá sự kiện sau khi bạn bấm Đồng ý trong trò chuyện, và chỉ sửa, xoá sự kiện do Mentor tạo.",
      status: flag(ctx.calendar.connected),
      action: ctx.calendar.connected ? { kind: "link", href: "/settings", label: "Xem trong Cài đặt" } : { kind: "calendar", label: "Kết nối" },
    });
  }

  if (ncs && ctx.inboundEmailAddress) {
    steps.push({
      id: "email",
      title: "Email chuyển tiếp",
      body:
        "Chuyển thư từ trường, giáo viên hướng dẫn hay ban tổ chức hội nghị tới địa chỉ này. Mentor đọc thư và ghi lại deadline.",
      hint: "Chỉ chuyển thư liên quan đến việc học, không chuyển cả hộp thư.",
      address: ctx.inboundEmailAddress,
      status: ctx.emailReceived === undefined ? null : ctx.emailReceived ? "done" : "todo",
      action: { kind: "link", href: "/settings#email-forward", label: "Cách tự động chuyển tiếp" },
    });
  }

  if (ncs) {
    steps.push({
      id: "papers",
      title: "Tìm paper",
      body:
        "Nhờ Mentor tìm paper theo chủ đề (arXiv, Semantic Scholar). Mỗi sáng thứ Hai, Mentor tự thêm tối đa 5 paper mới vào Hàng đợi đọc ở mục Nghiên cứu. Bấm một câu để đưa vào khung chat:",
      status: null,
      action: null,
      prompts: PAPER_PROMPTS,
    });
  }

  if (ctx.role === "thpt") {
    steps.push({
      id: "phone",
      title: "Gửi ảnh bài kiểm tra từ điện thoại",
      body:
        "Bài kiểm tra Toán đã được giáo viên chấm: quét mã QR bằng camera điện thoại, chụp rõ cả bài rồi gửi. Mentor giữ nguyên điểm giáo viên chấm và tìm lỗi em hay lặp lại.",
      status: null,
      action: { kind: "mobile-upload", label: "Mở mã QR" },
    });
  }

  // Linux desktops get the Linux package when the server offers one (or are already in the app);
  // everyone else, Linux without a Linux package included, gets the Windows step as before.
  const linux = !!ctx.linuxDesktop && (!!ctx.desktopDownloadUrlLinux || !!ctx.inDesktopApp);
  const dl = linux ? (ctx.desktopDownloadUrlLinux ?? null) : ctx.desktopDownloadUrl;
  if (dl || ctx.inDesktopApp) {
    steps.push({
      id: "desktop",
      title: "Cài app máy tính",
      body: linux
        ? // Ctrl+Alt+M is left out: on Wayland sessions (Ubuntu's default) it rarely reaches the app.
          "Bong bóng chữ M ở góc màn hình: bấm vào để mở khung chat nhỏ, không cần mở trình duyệt. Biểu tượng Mentor trên thanh trên cùng cũng mở được khung chat. Đăng nhập trong app bằng mã 6 số trong email."
        : "Bong bóng chữ M ở góc màn hình: bấm vào hoặc nhấn Ctrl+Alt+M để mở khung chat nhỏ, không cần mở trình duyệt. Đăng nhập trong app bằng mã 6 số trong email.",
      hint: linux
        ? "Cho Ubuntu 22.04 trở lên. Cách cài file .deb hoặc AppImage: Hướng dẫn sử dụng, mục “Cài trên Linux”."
        : `${ctx.desktopDownloadUrlLinux ? "Cho Windows 10, 11 (có cả bản Linux: mở trang này trên máy Linux để tải)." : "Chỉ có cho Windows 10, 11."} Nếu Windows báo “Windows đã bảo vệ PC của bạn”, bấm Thông tin thêm rồi Vẫn chạy.`,
      status: ctx.inDesktopApp ? "done" : null,
      action: dl && !ctx.inDesktopApp ? { kind: "external", href: dl, label: linux ? "Tải app (Linux)" : "Tải app (Windows)" } : null,
    });
  }

  if (ctx.role) {
    steps.push(
      {
        id: "proactivity",
        title: "Mức độ chủ động và giờ yên lặng",
        body:
          "Chọn Mentor nhắc nhiều hay ít (mặc định Vừa: tối đa 1 thông báo mỗi ngày, luôn báo deadline trong 48 giờ tới) và giờ Mentor không gửi thông báo (mặc định 22:00 đến 07:00).",
        status: null,
        action: { kind: "link", href: "/settings", label: "Mở Cài đặt" },
      },
      {
        id: "memory",
        title: "Mentor nhớ gì về bạn",
        body:
          "Xem hồ sơ, việc hiện tại, sở thích học mà Mentor đã ghi. Dòng ghi Suy luận là điều Mentor tự đoán; đoán sai thì sửa hoặc bấm Quên mục này.",
        status: null,
        action: { kind: "link", href: "/memory", label: "Xem trí nhớ" },
      },
      {
        id: "privacy",
        title: "Quyền riêng tư: tải về và xoá dữ liệu",
        body: "Ở Cài đặt, mục Dữ liệu và tài khoản: Tải dữ liệu (.zip) để lấy toàn bộ dữ liệu, hoặc Xoá tài khoản để xoá vĩnh viễn.",
        status: null,
        action: { kind: "link", href: "/settings", label: "Mở Cài đặt" },
      },
    );
  }

  return steps;
}

/** A step counts as done when the API says so or, without an API status, after the learner opened it. */
export function isStepDone(step: SetupStep, visited: ReadonlySet<SetupStepId>): boolean {
  return step.status === "done" || (step.status === null && visited.has(step.id));
}

// ---- "visited" marks for steps without an API status (per browser, per learner) ----

const VISITED_KEY = "mentor-setup-guide-visited:";

export function loadVisited(userId: string, storage: Pick<Storage, "getItem"> | null): Set<SetupStepId> {
  try {
    const raw = storage?.getItem(VISITED_KEY + userId);
    const arr = raw ? (JSON.parse(raw) as unknown) : [];
    return new Set(Array.isArray(arr) ? (arr.filter((x) => typeof x === "string") as SetupStepId[]) : []);
  } catch {
    return new Set();
  }
}

export function saveVisited(userId: string, visited: ReadonlySet<SetupStepId>, storage: Pick<Storage, "setItem"> | null): void {
  try {
    storage?.setItem(VISITED_KEY + userId, JSON.stringify([...visited]));
  } catch {
    // storage unavailable: the marks last for this page only
  }
}
