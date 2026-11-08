import { Link } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { useAuth } from "../state/auth";
import { Settings } from "../components/Settings";
import { Icon } from "../components/Icon";
import { speak } from "../lib/speak";
import { pickLang, useToday } from "../lib/today";
import khoaHoc from "../assets/hub/khoa-hoc.jpg";
import luyenTap from "../assets/hub/luyen-tap.jpg";
import hoiDap from "../assets/hub/hoi-dap.jpg";
import tienDo from "../assets/hub/tien-do.jpg";
import nghienCuu from "../assets/hub/nghien-cuu.jpg";

export const FEATURES = [
  { id: "courses", path: "/khoa-hoc", img: khoaHoc },
  { id: "practice", path: "/luyen-tap", img: luyenTap },
  { id: "ask", path: "/hoi-dap", img: hoiDap },
  { id: "progress", path: "/tien-do", img: tienDo },
] as const;

/** The fifth square, university band only. */
export const RESEARCH = { id: "research", path: "/nghien-cuu", img: nghienCuu } as const;
type TileId = (typeof FEATURES)[number]["id"] | typeof RESEARCH.id;

function tilt(e: React.PointerEvent<HTMLElement>) {
  if (e.pointerType !== "mouse" || window.matchMedia("(prefers-reduced-motion: reduce)").matches) return;
  const el = e.currentTarget;
  const r = el.getBoundingClientRect();
  el.style.setProperty("--ry", ((e.clientX - r.left) / r.width - 0.5) * 8 + "deg");
  el.style.setProperty("--rx", -((e.clientY - r.top) / r.height - 0.5) * 8 + "deg");
}
function untilt(e: React.PointerEvent<HTMLElement>) {
  e.currentTarget.style.setProperty("--rx", "0deg");
  e.currentTarget.style.setProperty("--ry", "0deg");
}

export function Hub() {
  const { t, i18n } = useTranslation();
  const { user } = useAuth();
  const { today } = useToday();
  const tiles = user?.age_band === "uni" ? [...FEATURES, RESEARCH] : FEATURES;

  /* One live line per square, written by the planner (GET /today); a plain invitation until it has answered. */
  const live = (id: TileId) => {
    const hubLine = today?.hub[id];
    const line = hubLine ? pickLang(hubLine, "line", i18n.language) : "";
    const text = line || t(`hub.live.${id}`);
    return id === "courses" ? (
      <span className="now">
        <Icon name="play" />
        <span>{text}</span>
      </span>
    ) : (
      <p>{text}</p>
    );
  };

  return (
    <div className="app">
      <header className="topbar">
        <span className="logo">
          <span className="logo-mark">M</span>
          <span>Mentor</span>
        </span>
        <span className="grow" />
        <Settings />
      </header>
      <main className="main hub-main">
        <h1 className="hello">
          <span className="marker">{t("hub.hello", { name: user?.display_name ?? "" })}</span>
        </h1>
        <div className="grid4">
          {tiles.map((f) => (
            <div className={"cell" + (f.id === "research" ? " fifth" : "")} key={f.id} data-guide={f.id} data-guide-label={t(`hub.${f.id}`)}>
              <Link className="tile" to={f.path} onPointerMove={tilt} onPointerLeave={untilt}>
                <img src={f.img} alt="" />
                <span className="label">
                  <h2>{t(`hub.${f.id}`)}</h2>
                  {live(f.id)}
                </span>
              </Link>
              <button className="speak" type="button" aria-label={t("hub.readAloud", { what: t(`hub.${f.id}`) })} onClick={() => speak(t(`hub.${f.id}`), i18n.language)}>
                <Icon name="volume" />
              </button>
            </div>
          ))}
        </div>
      </main>
    </div>
  );
}
