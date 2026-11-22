import { useEffect, useState } from "react";
import { Navigate, useParams, useSearchParams } from "react-router-dom";
import { useAuth } from "../../../state/auth";
import { getCourseInfo } from "../../../lib/courseInfo";
import { loadEnrollments } from "../../../lib/enrollments";
import { lg } from "../../api";
import { chickenOfCourse } from "../../chickenOf";

/**
 * `/khoa-hoc/:id` (old links: planner, reminders, chat replies, the old catalog) lands in the chicken's coop:
 * a course the student has opens its tree (`?khoa=<id>`); one they have not opens its preview (`?c=<id>`).
 */
export function ToChuong() {
  const { id = "" } = useParams();
  const { token, user } = useAuth();
  const [to, setTo] = useState<string | null>(null);
  useEffect(() => {
    if (!token || !user) return;
    let alive = true;
    (async () => {
      try {
        const [info, { list }] = await Promise.all([getCourseInfo(token, id), loadEnrollments(token, user.id)]);
        const mine = list.some((e) => e.course_id === id);
        if (alive) setTo(`/chuong/${encodeURIComponent(chickenOfCourse(info))}?${mine ? "khoa" : "c"}=${encodeURIComponent(id)}`);
      } catch {
        if (alive) setTo("/");
      }
    })();
    return () => {
      alive = false;
    };
  }, [token, user, id]);
  return to ? <Navigate replace to={to} /> : <div className="boot" />;
}

/** `/khoa-hoc/tim-kiem` is the search of the student's first chicken (the village when they have none yet). */
export function ToFind() {
  const { token } = useAuth();
  const [params] = useSearchParams();
  const [to, setTo] = useState<string | null>(null);
  useEffect(() => {
    if (!token) return;
    let alive = true;
    lg.getVillage(token).then(
      (v) => {
        const first = v.chickens[0]?.id;
        const p = new URLSearchParams({ tim: "1" });
        const q = params.get("q");
        if (q) p.set("q", q);
        if (alive) setTo(first ? `/chuong/${encodeURIComponent(first)}?${p.toString()}` : "/");
      },
      () => alive && setTo("/"),
    );
    return () => {
      alive = false;
    };
  }, [token, params]);
  return to ? <Navigate replace to={to} /> : <div className="boot" />;
}
