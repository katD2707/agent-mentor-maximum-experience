import { API_BASE, qs, raw, request } from "./http";
import { getMediaToken, withToken } from "./media";
import { ApiError } from "./types";
import type { CoursePack } from "./course";
import type { ChatMessage, CommentStatus, Outline, TeacherApi, TeacherComment, TeacherCourseDetail, TeacherCourseSummary, UploadProgress } from "./teacher";

const P = "/teacher";
const enc = encodeURIComponent;

/** multipart POST with upload progress (fetch cannot report it). */
function postForm<T>(path: string, token: string, form: FormData, onProgress?: UploadProgress): Promise<T> {
  return new Promise((resolve, reject) => {
    const x = new XMLHttpRequest();
    x.open("POST", API_BASE + path);
    x.setRequestHeader("Authorization", `Bearer ${token}`);
    x.upload.onprogress = (e) => e.lengthComputable && onProgress?.(e.loaded, e.total);
    x.onerror = () => reject(new ApiError(0, "network"));
    x.onload = () => {
      if (x.status < 200 || x.status >= 300) return reject(new ApiError(x.status, x.status === 401 ? "unauthorized" : x.status === 404 ? "not_found" : "unknown"));
      try {
        resolve(JSON.parse(x.responseText) as T);
      } catch {
        reject(new ApiError(x.status, "unknown"));
      }
    };
    x.send(form);
  });
}

function formOf(files: File[], extra: Record<string, string | undefined>): FormData {
  const f = new FormData();
  for (const file of files) f.append("files[]", file, file.name);
  for (const [k, v] of Object.entries(extra)) if (v) f.append(k, v);
  return f;
}

/** The origin of the gateway, for thumb URLs the gateway gives as a path ("/api/teacher/..."). */
const ORIGIN = () => {
  try {
    return new URL(API_BASE).origin;
  } catch {
    return "";
  }
};

export const httpTeacherApi: TeacherApi = {
  upload: (token, files, note, onProgress) => postForm(`${P}/uploads`, token, formOf(files, { note }), onProgress),
  addMaterials: (token, id, files, replace, onProgress) => postForm(`${P}/courses/${enc(id)}/materials`, token, formOf(files, { replace }), onProgress),
  listCourses: (token, since) => request<TeacherCourseSummary[]>("GET", `${P}/courses${qs({ since })}`, { token }),
  getCourse: (token, id) => request<TeacherCourseDetail>("GET", `${P}/courses/${enc(id)}`, { token }),
  chat: (token, id, text) => request<ChatMessage[]>("POST", `${P}/courses/${enc(id)}/chat`, { token, body: { text } }),
  putOutline: (token, id, ops) => request<Outline>("PUT", `${P}/courses/${enc(id)}/outline`, { token, body: { ops } }),
  async build(token, id) {
    await request("POST", `${P}/courses/${enc(id)}/build`, { token });
  },
  async getPack(token, id, v) {
    return (await (await raw(`/courses/${enc(id)}/versions/${v}/pack`, token)).json()) as CoursePack;
  },
  postComment: (token, id, v, c) => request<{ id: string; status: CommentStatus }>("POST", `${P}/courses/${enc(id)}/versions/${v}/comments`, { token, body: c }),
  listComments: (token, id, v) => request<TeacherComment[]>("GET", `${P}/courses/${enc(id)}/versions/${v}/comments`, { token }),
  async publish(token, id, v) {
    await request("POST", `${P}/courses/${enc(id)}/versions/${v}/publish`, { token });
  },
  setLevel: (token, id, v, level) => request<{ version: number; new_version: boolean }>("PUT", `${P}/courses/${enc(id)}/versions/${v}/level`, { token, body: { level } }),
  async newVersion(token, id) {
    const r = await request<{ version?: number; latest_version?: number }>("POST", `${P}/courses/${enc(id)}/versions`, { token });
    return r.version ?? r.latest_version ?? 0;
  },
  thumbSrc(token, url) {
    if (!url) return "";
    if (/^(data|blob):/.test(url)) return url;
    const abs = /^https?:/.test(url) ? url : url.startsWith("/api/") ? ORIGIN() + url : API_BASE + (url.startsWith("/") ? url : `/${url}`);
    return withToken(abs, getMediaToken() ?? token); // the gateway takes only the short-lived media token in `?t=`
  },
};
