import { redirect } from "next/navigation";

/** The activity log is not part of the learner UI any more. */
export default function ActivityRedirect() {
  redirect("/settings");
}
