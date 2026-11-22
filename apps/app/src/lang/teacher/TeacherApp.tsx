import { lazy, Suspense, useEffect } from "react";
import { Navigate, Route, Routes } from "react-router-dom";
import { CourseChat } from "./CourseChat";
import { TeacherHome } from "./Home";
import { TeacherLive } from "./live";

// the labels and review screens pull in the chicken pictures, Markdown + KaTeX and the student quiz view: they load on demand
const Labels = lazy(() => import("./LabelsScreen"));
const Review = lazy(() => import("./Review"));
const boot = <div className="boot" />;

/**
 * Everything a signed-in teacher sees (gv-01..04): home (drop zone + courses), a course's outline, its labels, and the review.
 * Routes: `/`, `/khoa/:id`, `/khoa/:id/nhan?v=`, `/khoa/:id/duyet?v=`.
 */
export default function TeacherApp() {
  // the warm dark palette of teacher.css applies to the teacher screens only
  useEffect(() => {
    document.documentElement.dataset.teacher = "1";
    return () => {
      delete document.documentElement.dataset.teacher;
    };
  }, []);
  return (
    <TeacherLive>
      <Routes>
        <Route path="/" element={<TeacherHome />} />
        <Route path="/khoa/:id" element={<CourseChat />} />
        <Route
          path="/khoa/:id/nhan"
          element={
            <Suspense fallback={boot}>
              <Labels />
            </Suspense>
          }
        />
        <Route
          path="/khoa/:id/duyet"
          element={
            <Suspense fallback={boot}>
              <Review />
            </Suspense>
          }
        />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </TeacherLive>
  );
}
