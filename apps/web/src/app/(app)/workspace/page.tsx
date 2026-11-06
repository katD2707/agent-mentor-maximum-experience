import { redirect } from "next/navigation";

/** The workspace browser is gone: export and account deletion live in Settings. */
export default function WorkspaceRedirect() {
  redirect("/settings");
}
