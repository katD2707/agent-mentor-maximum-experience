"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useId, useRef, useState, useSyncExternalStore } from "react";
import { Icon } from "@/components/Icon";
import { useMe, useSession } from "@/components/session";
import { useTour } from "@/components/Tour";
import { useToast } from "@/components/toast";
import { ConfirmDialog, ErrorBox, Loading, PageHeader, errorText } from "@/components/ui";
import { getApi, getMock, IS_MOCK, isApiError } from "@/lib/api";
import { queueChatIntent } from "@/lib/chatIntent";
import { PERSONA_LABELS, type Persona } from "@/lib/api/mock/seed";
import { useDesktopMode } from "@/lib/desktop";
import { OPEN_SHORTCUTS_EVENT } from "@/lib/conversationNav";
import { formatBytes, localDateStamp } from "@/lib/format";
import { hasRealInboundDomain } from "@/lib/learner";
import { desktopDownloadUrl, desktopDownloadUrlLinux, isLinuxDesktop } from "@/lib/setupGuide";
import { useAsync } from "@/lib/hooks";
import { currentSubscription, disablePush, enablePush, pushSupported } from "@/lib/push";
import { invalidSettingsMessage, learnerToggles } from "@/lib/settings";
import { setSounds, setTextScale, TEXT_SCALE_MAX, TEXT_SCALE_MIN, useUiPref } from "@/lib/uiPrefs";
import type { Language, ProactivityLevel, Settings } from "@/lib/types";

const PROACTIVITY: { value: ProactivityLevel; title: string; desc: string }[] = [
  { value: "off", title: "Tắt", desc: "Chỉ trả lời khi bạn hỏi; không gửi lời nhắc nào." },
  { value: "normal", title: "Vừa (mặc định)", desc: "Tối đa 1 thông báo/ngày, gom việc lại; luôn báo deadline trong 48 giờ." },
  { value: "high", title: "Nhiều", desc: "Nhắc ngay khi có việc mới, việc cần bạn duyệt hoặc đến lịch ôn." },
];

function ToggleRow({ label, checked, onToggle }: { label: string; checked: boolean; onToggle: (enabled: boolean) => void }) {
  const id = useId();
  return (
    <label className="switch" htmlFor={id} style={{ display: "flex", padding: "6px 0" }}>
      <input id={id} type="checkbox" role="switch" checked={checked} aria-checked={checked} onChange={(e) => onToggle(e.target.checked)} />
      <span>{label}</span>
    </label>
  );
}

/** Settings save by themselves half a second after the last change. */
function SettingsForm({ initial }: { initial: Settings }) {
  const toast = useToast();
  const { refresh } = useSession();
  const [s, setS] = useState<Settings>(initial);
  const [invalid, setInvalid] = useState<string | null>(null);
  const [state, setState] = useState<"idle" | "saving" | "saved">("idle");
  const saved = useRef<Settings>(initial);
  const qhStart = useId();
  const qhEnd = useId();
  const lang = useId();

  useEffect(() => {
    if (JSON.stringify(s) === JSON.stringify(saved.current)) return;
    const timer = window.setTimeout(async () => {
      setState("saving");
      setInvalid(null);
      try {
        const r = await getApi().putSettings(s);
        const languageChanged = r.language !== saved.current.language;
        saved.current = r;
        setState("saved");
        if (languageChanged) void refresh();
      } catch (err) {
        setState("idle");
        if (isApiError(err, 422)) {
          const msg = invalidSettingsMessage(err.body, saved.current);
          setInvalid(msg);
          toast(msg, "error");
        } else toast(errorText(err), "error");
      }
    }, 500);
    return () => window.clearTimeout(timer);
  }, [s, refresh, toast]);

  const toggles = learnerToggles(s.routines);

  return (
    <div>
      {invalid && (
        <div className="alert alert-error" role="alert">
          <div className="row">
            <span className="spacer">{invalid}</span>
            <button
              type="button"
              className="btn btn-sm"
              onClick={() => {
                setS(saved.current);
                setInvalid(null);
              }}
            >
              Khôi phục cài đặt đã lưu
            </button>
          </div>
        </div>
      )}
      <section className="card" aria-labelledby="pro-h">
        <h2 id="pro-h">Mức độ chủ động</h2>
        <fieldset>
          <legend className="sr-only">Mức độ chủ động của mentor</legend>
          <div className="choice-grid">
            {PROACTIVITY.map((p) => (
              <label key={p.value} className="choice">
                <input type="radio" name="proactivity" value={p.value} checked={s.proactivity === p.value} onChange={() => setS({ ...s, proactivity: p.value })} />
                <span>
                  <span className="choice-title">{p.title}</span>
                  <br />
                  <span className="choice-desc">{p.desc}</span>
                </span>
              </label>
            ))}
          </div>
        </fieldset>
        <fieldset>
          <legend>Giờ yên lặng</legend>
          <p className="hint" style={{ marginTop: 0 }}>
            Mentor không gửi thông báo trong khoảng này (trừ cảnh báo an toàn).
          </p>
          <div className="row">
            <label htmlFor={qhStart}>Từ</label>
            <input
              id={qhStart}
              className="input"
              type="time"
              style={{ width: 130 }}
              value={s.quiet_hours[0]}
              onChange={(e) => setS({ ...s, quiet_hours: [e.target.value, s.quiet_hours[1]] })}
              required
            />
            <label htmlFor={qhEnd}>đến</label>
            <input
              id={qhEnd}
              className="input"
              type="time"
              style={{ width: 130 }}
              value={s.quiet_hours[1]}
              onChange={(e) => setS({ ...s, quiet_hours: [s.quiet_hours[0], e.target.value] })}
              required
            />
          </div>
        </fieldset>
        <div className="field" style={{ maxWidth: 320 }}>
          <label htmlFor={lang}>Ngôn ngữ mentor dùng</label>
          <select id={lang} className="select" value={s.language} onChange={(e) => setS({ ...s, language: e.target.value as Language })}>
            <option value="vi">Tiếng Việt</option>
            <option value="en">English</option>
          </select>
        </div>
      </section>

      {toggles.length > 0 && (
        <section className="card" aria-labelledby="rt-h">
          <h2 id="rt-h">Mentor nhắc bạn</h2>
          {toggles.map(({ label, routine }) => (
            <ToggleRow
              key={routine.id}
              label={label}
              checked={routine.enabled}
              onToggle={(enabled) => setS({ ...s, routines: s.routines.map((x) => (x.id === routine.id ? { ...x, enabled } : x)) })}
            />
          ))}
        </section>
      )}
      <p className="hint" role="status" style={{ marginTop: 8 }}>
        {state === "saving" ? "Đang lưu…" : state === "saved" ? "Đã lưu." : "Thay đổi được lưu tự động."}
      </p>
    </div>
  );
}

function InboundEmail() {
  const me = useMe();
  const toast = useToast();
  const addr = me.inbound_email_address;
  // A `.local` address is the dev placeholder: the mail domain is not set up, so there is nothing to offer.
  if (!hasRealInboundDomain(addr)) return null;

  async function copy() {
    if (!addr) return;
    try {
      await navigator.clipboard.writeText(addr);
      toast("Đã sao chép địa chỉ.", "ok");
    } catch {
      toast("Không sao chép được. Hãy chọn và sao chép thủ công.", "error");
    }
  }

  return (
    <section className="card" id="email-forward" aria-labelledby="mail-h" style={{ marginTop: 16 }}>
      <h2 id="mail-h">Email chuyển tiếp</h2>
      {addr ? (
        <>
          <p className="muted">
            Thư gửi tới địa chỉ này được đưa vào hộp thư đến của mentor. Mentor chỉ thấy những thư bạn chọn chuyển tiếp.
          </p>
          <div className="row" style={{ flexWrap: "nowrap" }}>
            <code className="input" style={{ display: "flex", alignItems: "center", overflowX: "auto", whiteSpace: "nowrap" }} aria-label="Địa chỉ email chuyển tiếp">
              {addr}
            </code>
            <button type="button" className="btn" onClick={() => void copy()}>
              <Icon name="copy" size={16} /> Sao chép
            </button>
          </div>
          <details style={{ marginTop: 12 }}>
            <summary>Cách tự động chuyển tiếp thư (Gmail, Outlook)</summary>
            <div className="md" style={{ marginTop: 8 }}>
              <p>
                <strong>Gmail:</strong>
              </p>
              <ol>
                <li>Cài đặt → Xem tất cả chế độ cài đặt → Chuyển tiếp và POP/IMAP → Thêm địa chỉ chuyển tiếp, dán địa chỉ trên.</li>
                <li>Gmail gửi thư xác nhận tới địa chỉ này. Hãy nhờ mentor trong trò chuyện đọc mã xác nhận cho bạn, rồi nhập vào Gmail.</li>
                <li>
                  Tạo bộ lọc: ô tìm kiếm → Hiện tuỳ chọn tìm kiếm → điền “Từ” (ví dụ email GVHD, phòng đào tạo, hội nghị) → Tạo bộ lọc →
                  chọn “Chuyển tiếp tới” địa chỉ trên.
                </li>
              </ol>
              <p>
                <strong>Outlook:</strong> Cài đặt → Thư → Quy tắc → Thêm quy tắc mới → điều kiện “Từ” → hành động “Chuyển tiếp tới”
                địa chỉ trên.
              </p>
              <p className="hint">
                Chỉ chuyển tiếp thư liên quan đến việc học. Không nên chuyển tiếp toàn bộ hộp thư. Bạn cũng có thể chuyển tay từng
                thư.
              </p>
            </div>
          </details>
        </>
      ) : (
        <p className="muted">Tài khoản của bạn chưa có địa chỉ chuyển tiếp.</p>
      )}
    </section>
  );
}

const CALENDAR_ERRORS: Record<string, string> = {
  denied: "Bạn đã không cho phép truy cập Google Calendar.",
  scope: "Bạn chưa chọn quyền xem và sửa sự kiện lịch. Hãy kết nối lại và tick quyền đó.",
  state: "Phiên kết nối đã hết hạn (quá 10 phút) hoặc không hợp lệ. Hãy thử lại.",
  session: "Phiên đăng nhập đã thay đổi trong lúc kết nối. Hãy thử lại.",
};

function GoogleCalendarCard() {
  const toast = useToast();
  const q = useAsync(() => getApi().getGoogleCalendar(), []);
  const [busy, setBusy] = useState(false);
  const [confirming, setConfirming] = useState(false);

  // Back from Google: /settings?calendar=connected|error&reason=...
  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    const outcome = params.get("calendar");
    if (!outcome) return;
    if (outcome === "connected") toast("Đã kết nối Google Calendar.", "ok");
    else toast(CALENDAR_ERRORS[params.get("reason") ?? ""] ?? "Không kết nối được Google Calendar. Hãy thử lại.", "error");
    params.delete("calendar");
    params.delete("reason");
    const rest = params.toString();
    window.history.replaceState(null, "", window.location.pathname + (rest ? `?${rest}` : ""));
  }, [toast]);

  async function connect() {
    setBusy(true);
    try {
      const url = await getApi().connectGoogleCalendar();
      if (url) {
        window.location.assign(url);
        return;
      }
      toast("Đã kết nối Google Calendar.", "ok");
      q.reload();
    } catch (err) {
      toast(errorText(err), "error");
    }
    setBusy(false);
  }

  async function disconnect() {
    setBusy(true);
    try {
      await getApi().disconnectGoogleCalendar();
      toast("Đã ngắt kết nối Google Calendar.", "ok");
      q.reload();
    } catch (err) {
      toast(errorText(err), "error");
    } finally {
      setBusy(false);
      setConfirming(false);
    }
  }

  const s = q.data;
  return (
    <section className="card" aria-labelledby="gcal-h">
      <h2 id="gcal-h">Google Calendar</h2>
      {q.error != null && <ErrorBox error={q.error} onRetry={q.reload} />}
      {q.loading && !s && <Loading />}
      {s && !s.available && <p className="muted">Máy chủ chưa bật tích hợp Google Calendar.</p>}
      {s && s.available && (
        <>
          <p className="muted">
            Mentor xem lịch của bạn để nhắc deadline và lên kế hoạch tuần. Mentor chỉ thêm, sửa hoặc xoá sự kiện sau khi bạn bấm
            Đồng ý trong trò chuyện, và chỉ sửa/xoá sự kiện do Mentor tạo.
          </p>
          {s.connected ? (
            <div className="row">
              <span className="spacer">
                <span className="badge badge-ok">Đã kết nối</span> với <strong>{s.email ?? "tài khoản Google"}</strong>
              </span>
              <button type="button" className="btn" onClick={() => setConfirming(true)} disabled={busy}>
                Ngắt kết nối
              </button>
            </div>
          ) : (
            <button type="button" className="btn btn-primary" onClick={() => void connect()} disabled={busy}>
              {busy ? "Đang chuyển tới Google…" : "Kết nối Google Calendar"}
            </button>
          )}
        </>
      )}
      <ConfirmDialog
        open={confirming}
        title="Ngắt kết nối Google Calendar?"
        confirmLabel="Ngắt kết nối"
        danger
        busy={busy}
        onConfirm={() => void disconnect()}
        onCancel={() => setConfirming(false)}
      >
        Mentor sẽ không xem hay thêm lịch nữa và quyền truy cập bị thu hồi ở Google. Các sự kiện đã tạo vẫn giữ nguyên trong lịch
        của bạn.
      </ConfirmDialog>
    </section>
  );
}

/**
 * Browser notifications (Web Push). Permission is requested only from this switch, never on load; hidden in the
 * desktop pop-up (native toasts there) and when the gateway has no VAPID keys.
 */
function PushCard() {
  const toast = useToast();
  const id = useId();
  const status = useAsync(() => getApi().getVapidPublicKey(), []);
  const [on, setOn] = useState<boolean | null>(null);
  const [busy, setBusy] = useState(false);
  const [denied, setDenied] = useState(() => typeof Notification !== "undefined" && Notification.permission === "denied");

  useEffect(() => {
    let alive = true;
    currentSubscription().then(
      (s) => alive && setOn(!!s),
      () => alive && setOn(false),
    );
    return () => {
      alive = false;
    };
  }, []);

  if (status.error != null || (status.data && !status.data.enabled)) return null;
  const supported = pushSupported();

  async function toggle(next: boolean) {
    setBusy(true);
    try {
      if (next) {
        const r = await enablePush();
        if (r === "enabled") {
          setOn(true);
          toast("Đã bật thông báo trên trình duyệt này.", "ok");
        } else if (r === "denied") {
          setDenied(true);
          setOn(false);
        } else if (r === "unavailable") {
          toast("Máy chủ chưa bật thông báo đẩy.", "error");
          setOn(false);
        } else setOn(false);
      } else {
        await disablePush();
        setOn(false);
        toast("Đã tắt thông báo trên trình duyệt này.", "ok");
      }
    } catch (e) {
      toast(errorText(e), "error");
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="card" aria-labelledby="push-h">
      <h2 id="push-h">Thông báo trên trình duyệt</h2>
      <p className="muted">
        Khi bạn không mở Mentor, lời nhắc (check-in, giờ ôn, hết giờ tập trung) sẽ hiện như thông báo của máy. Nội dung trên màn
        hình khoá luôn ngắn gọn, không lộ chi tiết. Không bao giờ có âm thanh, và giờ yên lặng vẫn được tôn trọng.
      </p>
      {!supported ? (
        <p className="hint">Trình duyệt này không hỗ trợ thông báo đẩy.</p>
      ) : (
        <>
          <label className="switch" htmlFor={id}>
            <input
              id={id}
              type="checkbox"
              role="switch"
              checked={on === true}
              aria-checked={on === true}
              disabled={busy || on === null || (denied && on !== true)}
              onChange={(e) => void toggle(e.target.checked)}
            />
            <span>{busy ? "Đang cập nhật…" : on ? "Đang bật trên trình duyệt này" : "Bật thông báo trên trình duyệt này"}</span>
          </label>
          {denied && on !== true && (
            <p className="hint" role="status" style={{ marginTop: 8 }}>
              Trình duyệt đang chặn thông báo của trang này. Mở biểu tượng ổ khoá cạnh thanh địa chỉ để cho phép, rồi bật lại.
            </p>
          )}
          {status.data?.subscribed_devices ? (
            <p className="hint" style={{ marginTop: 8 }}>
              Đang bật trên {status.data.subscribed_devices} thiết bị.
            </p>
          ) : null}
        </>
      )}
    </section>
  );
}

/** Text size 85-140 %, applied at once to the whole app (and the desktop pop-up, which shares this storage). */
function DisplayCard() {
  const scale = useUiPref("textScale");
  const sounds = useUiPref("sounds");
  const rangeId = useId();
  const soundId = useId();
  const pct = Math.round(scale * 100);
  return (
    <section className="card" aria-labelledby="disp-h">
      <h2 id="disp-h">Hiển thị và âm thanh</h2>
      <div className="field">
        <label htmlFor={rangeId}>
          Cỡ chữ: <strong>{pct}%</strong>
        </label>
        <div className="row" style={{ flexWrap: "nowrap" }}>
          <span aria-hidden="true" style={{ fontSize: "0.85rem" }}>
            A
          </span>
          <input
            id={rangeId}
            type="range"
            min={Math.round(TEXT_SCALE_MIN * 100)}
            max={Math.round(TEXT_SCALE_MAX * 100)}
            step={5}
            value={pct}
            aria-valuetext={`${pct} phần trăm`}
            onChange={(e) => setTextScale(Number(e.target.value) / 100)}
            style={{ flex: 1 }}
          />
          <span aria-hidden="true" style={{ fontSize: "1.4rem" }}>
            A
          </span>
          <button type="button" className="btn btn-sm" onClick={() => setTextScale(1)} disabled={pct === 100}>
            Đặt lại 100%
          </button>
        </div>
        <p className="hint">Áp dụng cho cả ứng dụng và cửa sổ nhỏ trên máy này. Lưu trên thiết bị, không cần bấm lưu.</p>
      </div>
      <label className="switch" htmlFor={soundId}>
        <input id={soundId} type="checkbox" role="switch" checked={sounds} aria-checked={sounds} onChange={(e) => setSounds(e.target.checked)} />
        <span>Âm thanh nhẹ trong phần luyện tập (mặc định tắt)</span>
      </label>
    </section>
  );
}

/** Export, delete account, plus small links to the shortcut list and the replayable tour. */
function DataCard() {
  const me = useMe();
  const { logout } = useSession();
  const router = useRouter();
  const toast = useToast();
  const tour = useTour();
  const confirmId = useId();
  const [open, setOpen] = useState(false);
  const [typed, setTyped] = useState("");
  const [busy, setBusy] = useState(false);
  const [exporting, setExporting] = useState(false);

  async function exportZip() {
    setExporting(true);
    try {
      const blob = await getApi().exportWorkspace();
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `mentor-du-lieu-${localDateStamp()}.zip`;
      document.body.appendChild(a);
      a.click();
      a.remove();
      setTimeout(() => URL.revokeObjectURL(url), 10_000);
      toast(`Đã tải dữ liệu (${formatBytes(blob.size)}).`, "ok");
    } catch (e) {
      toast(errorText(e), "error");
    } finally {
      setExporting(false);
    }
  }

  async function remove() {
    setBusy(true);
    try {
      await getApi().deleteAccount();
      toast("Tài khoản và toàn bộ dữ liệu đã được xoá.", "ok");
      await logout().catch(() => undefined);
      router.replace("/login");
    } catch (e) {
      toast(errorText(e), "error");
      setBusy(false);
    }
  }

  return (
    <section className="card" aria-labelledby="data-h">
      <h2 id="data-h">Dữ liệu và tài khoản</h2>
      <p className="muted">Bạn có thể lấy toàn bộ dữ liệu mentor lưu về mình, hoặc xoá tài khoản bất cứ lúc nào.</p>
      <div className="row">
        <button type="button" className="btn" onClick={() => void exportZip()} disabled={exporting}>
          <Icon name="download" size={16} /> {exporting ? "Đang chuẩn bị…" : "Tải dữ liệu (.zip)"}
        </button>
        <button type="button" className="btn btn-danger" onClick={() => setOpen(true)}>
          <Icon name="trash" size={16} /> Xoá tài khoản
        </button>
      </div>
      <div className="row" style={{ marginTop: 12 }}>
        <button type="button" className="btn btn-ghost btn-sm" onClick={() => window.dispatchEvent(new Event(OPEN_SHORTCUTS_EVENT))}>
          Phím tắt <kbd>F1</kbd>
        </button>
        <button type="button" className="btn btn-ghost btn-sm" onClick={tour.replay}>
          Xem lại hướng dẫn
        </button>
      </div>
      <ConfirmDialog
        open={open}
        title="Xoá tài khoản vĩnh viễn?"
        confirmLabel="Xoá vĩnh viễn"
        danger
        busy={busy}
        confirmDisabled={typed.trim().toUpperCase() !== "XOÁ" && typed.trim().toUpperCase() !== "XOA"}
        onConfirm={() => void remove()}
        onCancel={() => {
          setOpen(false);
          setTyped("");
        }}
      >
        <p>
          Xoá vĩnh viễn tài khoản <strong>{me.email}</strong>, toàn bộ dữ liệu, lịch sử và các bản sao lưu.
          {me.role === "thpt" && " Liên kết với phụ huynh cũng bị huỷ."} Không thể hoàn tác. Nên tải dữ liệu về trước.
        </p>
        <div className="field">
          <label htmlFor={confirmId}>Gõ XOÁ để xác nhận</label>
          <input id={confirmId} className="input" value={typed} onChange={(e) => setTyped(e.target.value)} autoComplete="off" />
        </div>
      </ConfirmDialog>
    </section>
  );
}

function MockPanel() {
  const mock = getMock()!;
  const router = useRouter();
  const { refresh } = useSession();
  useSyncExternalStore(
    (cb) => mock.subscribe(cb),
    () => mock.version,
    () => 0,
  );
  const state = mock.state;
  const [persona, setPersona] = useState<Persona>(state.persona);

  return (
    <section className="card" id="mock" aria-labelledby="mock-h" style={{ borderStyle: "dashed" }}>
      <h2 id="mock-h">Chế độ mock (dành cho phát triển)</h2>
      <p className="hint">Dữ liệu chỉ nằm trong trình duyệt này (localStorage). Trò chuyện là mentor giả lập.</p>
      <fieldset>
        <legend>Dữ liệu mẫu</legend>
        <div className="stack">
          {(Object.keys(PERSONA_LABELS) as Persona[]).map((p) => (
            <label key={p} className="choice">
              <input type="radio" name="mock-persona" checked={persona === p} onChange={() => setPersona(p)} />
              <span>{PERSONA_LABELS[p]}</span>
            </label>
          ))}
        </div>
      </fieldset>
      <div className="row">
        <button
          type="button"
          className="btn"
          onClick={async () => {
            mock.resetPersona(persona, true);
            try {
              sessionStorage.removeItem("mentor-chat-messages");
            } catch {
              // ignore
            }
            const me = await refresh();
            router.replace(me?.onboarding_state === "active" ? "/chat" : "/onboarding");
          }}
        >
          <Icon name="refresh" size={16} /> Nạp lại dữ liệu mẫu
        </button>
        <label className="switch">
          <input type="checkbox" checked={state.autoParentVerify} onChange={(e) => mock.setAutoParentVerify(e.target.checked)} />
          <span>Phụ huynh tự xác nhận sau ~12 giây</span>
        </label>
      </div>
      <p className="hint" style={{ marginTop: 10 }}>
        Mẹo trong trò chuyện: nhắc tới “lịch” để thấy thẻ duyệt, “nhớ …” để mentor ghi vào me/now.md (thử sửa tệp đó cùng lúc để
        thấy xung đột 409), “thông báo” để nhận thông báo, “/loi” để giả lập lỗi. Thẻ tương tác: “/the” (tất cả các thẻ), “thẻ”,
        “hạn chót”, “tập trung 25 phút”, “xong rồi”, “tổng kết tuần”, “check-in”; “/nudge deadline” cho lời nhắc có nút.
      </p>
    </section>
  );
}

/** Things the first-run guide used to list: parent link status, phone photo upload, the desktop app. */
function ConnectCard() {
  const me = useMe();
  const router = useRouter();
  const thpt = me.role === "thpt";
  const parent = useAsync(() => (thpt ? getApi().getParentLink().catch(() => null) : Promise.resolve(null)), [thpt]);
  const [linux] = useState(() => typeof navigator !== "undefined" && isLinuxDesktop(navigator.userAgent));
  const desktop = useDesktopMode();
  const download = linux ? (desktopDownloadUrlLinux() ?? desktopDownloadUrl()) : desktopDownloadUrl();
  if (!thpt && (desktop || !download)) return null;
  const status = parent.data?.status;
  return (
    <section className="card" id="connect" aria-labelledby="connect-h">
      <h2 id="connect-h">Kết nối thêm</h2>
      {thpt && (
        <div className="row" style={{ padding: "6px 0" }}>
          <span className="spacer">
            Phụ huynh qua Zalo:{" "}
            {status === undefined ? "đang kiểm tra…" : status === "verified" ? <span className="badge badge-ok">Đã liên kết</span> : <span className="badge">Chưa liên kết</span>}
          </span>
          {status === "verified" ? (
            <Link href="/reports" className="btn btn-sm">
              Xem báo cáo
            </Link>
          ) : (
            status !== undefined && (
              <Link href="/onboarding" className="btn btn-sm">
                Liên kết
              </Link>
            )
          )}
        </div>
      )}
      {thpt && (
        <div className="row" style={{ padding: "6px 0" }}>
          <span className="spacer">Gửi ảnh bài kiểm tra từ điện thoại (quét mã QR).</span>
          <button
            type="button"
            className="btn btn-sm"
            onClick={() => {
              queueChatIntent({ kind: "mobile-upload" });
              router.push("/chat");
            }}
          >
            <Icon name="phone" size={16} /> Mở mã QR
          </button>
        </div>
      )}
      {!desktop && download && (
        <div className="row" style={{ padding: "6px 0" }}>
          <span className="spacer">App máy tính: bong bóng chat nhỏ ở góc màn hình.</span>
          <a className="btn btn-sm" href={download} target="_blank" rel="noopener noreferrer">
            <Icon name="download" size={16} /> Tải app
          </a>
        </div>
      )}
    </section>
  );
}

export default function SettingsPage() {
  const q = useAsync(() => getApi().getSettings(), []);
  const me = useMe();
  const desktop = useDesktopMode();
  return (
    <div className="page">
      <PageHeader title="Cài đặt" description="Mức độ chủ động, giờ yên lặng, ngôn ngữ, thông báo và dữ liệu của bạn." />
      {q.error != null && <ErrorBox error={q.error} onRetry={q.reload} />}
      {q.loading && !q.data && <Loading />}
      {q.data && <SettingsForm initial={q.data} />}
      {!desktop && (
        <div style={{ marginTop: 16 }}>
          <PushCard />
        </div>
      )}
      <div style={{ marginTop: 16 }}>
        <ConnectCard />
      </div>
      <InboundEmail />
      {me.role === "ncs" && (
        <div style={{ marginTop: 16 }}>
          <GoogleCalendarCard />
        </div>
      )}
      <div style={{ marginTop: 16 }}>
        <DisplayCard />
      </div>
      <div style={{ marginTop: 16 }}>
        <DataCard />
      </div>
      {IS_MOCK && (
        <div style={{ marginTop: 16 }}>
          <MockPanel />
        </div>
      )}
    </div>
  );
}
