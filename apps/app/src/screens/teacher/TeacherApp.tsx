import { lazy, Suspense } from "react";
import { Navigate, Route, Routes } from "react-router-dom";
import { CourseChat } from "./CourseChat";
import { TeacherHome } from "./Home";
import { TeacherLive } from "./live";

// the review screen pulls in Markdown + KaTeX and the student quiz view, so it loads on demand
const Review = lazy(() => import("./Review"));

/** Everything a signed-in teacher sees: home (drop zone + courses), a course's structure chat, and the review. */
export default function TeacherApp() {
  return (
    <TeacherLive>
      <Routes>
        <Route path="/" element={<TeacherHome />} />
        <Route path="/khoa/:id" element={<CourseChat />} />
        <Route
          path="/khoa/:id/duyet"
          element={
            <Suspense fallback={<div className="boot" />}>
              <Review />
            </Suspense>
          }
        />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </TeacherLive>
  );
}
