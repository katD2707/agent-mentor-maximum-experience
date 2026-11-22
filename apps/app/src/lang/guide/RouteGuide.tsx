import { useLocation } from "react-router-dom";
import { useAuth } from "../../state/auth";
import { subjectsFor } from "../subjects";
import { ChickenGuide } from "./ChickenGuide";

/** The guide key of a screen (a key of GUIDE_TOURS); null where the screen mounts its own guide (village, login, first run). */
export function guideScreen(pathname: string, teacher: boolean): string | null {
  if (teacher) {
    if (/^\/khoa\/[^/]+\/duyet/.test(pathname)) return "gv-review";
    if (/^\/khoa\/[^/]+\/nhan/.test(pathname)) return "gv-labels";
    if (/^\/khoa\/[^/]+/.test(pathname)) return "gv-course";
    return pathname === "/" ? "gv-home" : null;
  }
  if (/^\/chuong\//.test(pathname)) return "chuong";
  if (/^\/dau-truong/.test(pathname)) return "arena";
  if (/^\/kiem-tra\//.test(pathname)) return "tests";
  if (/^\/phong-tu-hoc/.test(pathname)) return "study";
  if (/^\/tien-do/.test(pathname)) return "progress";
  if (/^\/thu-vien/.test(pathname)) return "library";
  if (/^\/khoa-hoc\/[^/]+\/hoc/.test(pathname)) return "lesson";
  if (/^\/luyen-tap\/[^/]+\/(ket-qua|xem-lai)/.test(pathname)) return null;
  if (/^\/luyen-tap\/[^/]+/.test(pathname)) return "run";
  return null;
}

/** One chicken guide for every screen but the village, login and first run: it replaces the old Mực everywhere, teachers included. */
export function RouteGuide() {
  const { pathname } = useLocation();
  const { user } = useAuth();
  if (!user) return null;
  const teacher = user.role === "teacher";
  const screen = guideScreen(pathname, teacher);
  if (!screen) return null;
  const onChuong = /^\/chuong\/([^/]+)/.exec(pathname)?.[1];
  const chicken = onChuong ? decodeURIComponent(onChuong) : (subjectsFor(user.age_band)[0]?.id ?? "toan");
  return <ChickenGuide key={screen + chicken} screen={screen} chicken={chicken} />;
}
